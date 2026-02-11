import asyncio
from pathlib import Path
from sqlalchemy.orm import Session
from models import File, Job, Event, Setting
from workers.swift_runner import SwiftToolRunner
from workers.base_worker import WorkerBase, CancellationRequested
from services.path_validator import path_validator
from services.worker_status_service import worker_status_service
from services.job_integrity_service import job_integrity_service
from datetime import datetime
import shutil
import logging
import numpy as np
import soundfile as sf
import onnxruntime as ort
import json

logger = logging.getLogger(__name__)

# Module-level ONNX session cache — survives ProcessWorker re-creation
# (WorkerPool creates a new ProcessWorker every loop iteration)
_shared_onnx_session = None
_shared_onnx_model_path = None


class ProcessWorker(WorkerBase):
    def __init__(self, db: Session, swift_tools_dir: Path, semaphore: asyncio.Semaphore):
        super().__init__(db)
        self.swift = SwiftToolRunner(swift_tools_dir)
        self.semaphore = semaphore
        self.running = False
        self.onnx_session = None
        
        # Model path
        model_dir = swift_tools_dir.parent / "models"
        self.model_path = model_dir / "denoiser_model.onnx"
        
        if not self.model_path.exists():
            logger.warning(f"Denoiser model not found at {self.model_path}")
    
    def _init_onnx_model(self):
        """Initialize ONNX Runtime inference session, reusing cached session if available."""
        global _shared_onnx_session, _shared_onnx_model_path

        if self.onnx_session is not None:
            return  # Already initialized on this instance
        
        # Reuse cached session if model path matches
        if _shared_onnx_session is not None and _shared_onnx_model_path == str(self.model_path):
            self.onnx_session = _shared_onnx_session
            return
        
        if not self.model_path.exists():
            raise FileNotFoundError(f"Denoiser model not found at {self.model_path}")
        
        logger.info(f"Initializing ONNX Runtime session with model: {self.model_path}")
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        self.onnx_session = ort.InferenceSession(str(self.model_path), sess_options)
        _shared_onnx_session = self.onnx_session
        _shared_onnx_model_path = str(self.model_path)
        logger.info("ONNX Runtime session initialized (cached for reuse)")
    
    def _denoise_audio(self, input_wav: Path, output_wav: Path, progress_callback=None) -> bool:
        """
        Denoise audio using ONNX denoiser model (frame-by-frame stateful processing)
        
        Args:
            input_wav: Input WAV file path
            output_wav: Output WAV file path
            progress_callback: Optional async callback for progress updates
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self._init_onnx_model()
            
            logger.info(f"Denoising audio: {input_wav} -> {output_wav}")
            
            # Load audio
            waveform, sample_rate = sf.read(str(input_wav))
            
            logger.info(f"Loaded audio: shape={waveform.shape}, sr={sample_rate}, dtype={waveform.dtype}")
            
            # Handle stereo/mono
            # soundfile returns (samples,) for mono or (samples, channels) for stereo
            if waveform.ndim == 2:
                # Stereo: (samples, channels) - convert to mono by averaging channels
                audio_mono = np.mean(waveform, axis=1)
                was_stereo = True
                num_channels = waveform.shape[1]
            else:
                # Already mono
                audio_mono = waveform
                was_stereo = False
                num_channels = 1
            
            # Resample to 48kHz if needed (most denoisers expect 48kHz)
            original_sr = sample_rate
            if sample_rate != 48000:
                logger.info(f"Resampling from {sample_rate}Hz to 48000Hz for denoising")
                import librosa
                audio_mono = librosa.resample(audio_mono, orig_sr=sample_rate, target_sr=48000)
                sample_rate = 48000
            
            # Ensure float32
            audio_mono = audio_mono.astype(np.float32)
            
            # Frame-by-frame processing
            frame_size = 480  # Model expects 480 samples per frame (10ms at 48kHz)
            
            n_samples = len(audio_mono)
            n_frames = int(np.ceil(n_samples / frame_size))
            
            # Pad to multiple of frame_size
            padded_length = n_frames * frame_size
            if padded_length > n_samples:
                audio_mono = np.pad(audio_mono, (0, padded_length - n_samples), mode='constant')
            
            logger.info(f"Processing {n_frames} frames ({n_samples} samples at {sample_rate}Hz)")
            
            # Get model info
            input_names = [inp.name for inp in self.onnx_session.get_inputs()]
            output_names = [out.name for out in self.onnx_session.get_outputs()]
            
            # Initialize state (zeros for first frame)
            states = np.zeros(45304, dtype=np.float32)  # Model expects state size of 45304
            atten_lim_db = np.array(100.0, dtype=np.float32)  # Attenuation limit in dB
            
            # Process frame by frame
            enhanced_frames = []
            
            for i in range(n_frames):
                start = i * frame_size
                end = start + frame_size
                frame = audio_mono[start:end].astype(np.float32)
                
                # Prepare inputs
                inputs = {
                    'input_frame': frame,
                    'states': states,
                    'atten_lim_db': atten_lim_db
                }
                
                # Run inference on this frame
                outputs = self.onnx_session.run(output_names, inputs)
                enhanced_frame = outputs[0]  # enhanced_audio_frame
                states = outputs[1]  # new_states for next frame
                
                enhanced_frames.append(enhanced_frame)
                
                # Update progress every 100 frames (or 2% of total frames, whichever is less)
                report_interval = min(100, max(1, n_frames // 50))
                if i % report_interval == 0 and progress_callback:
                    progress_pct = i / n_frames
                    # Call the progress callback directly (it's now synchronous wrapper)
                    progress_callback({
                        'stage': 'denoise',
                        'progress': progress_pct
                    })
            
            # Final progress update
            if progress_callback:
                progress_callback({
                    'stage': 'denoise',
                    'progress': 1.0
                })
            
            # Concatenate all frames
            enhanced = np.concatenate(enhanced_frames)
            
            # Remove padding
            enhanced = enhanced[:n_samples]
            
            # Resample back to original sample rate if needed
            if original_sr != 48000:
                logger.info(f"Resampling back from 48000Hz to {original_sr}Hz")
                import librosa
                enhanced = librosa.resample(enhanced, orig_sr=48000, target_sr=original_sr)
            
            # Restore stereo if needed
            if was_stereo:
                # Duplicate mono enhanced audio to stereo: (samples, channels)
                enhanced = np.stack([enhanced, enhanced], axis=1)
            
            logger.info(f"Writing denoised audio: shape={enhanced.shape}, sr={original_sr}")
            
            # Write output
            sf.write(str(output_wav), enhanced, original_sr)
            logger.info(f"Denoised audio saved to {output_wav}")
            
            # Verify output file
            if output_wav.exists():
                output_size = output_wav.stat().st_size
                logger.info(f"Output file size: {output_size:,} bytes")
            
            return True
            
        except Exception as e:
            logger.error(f"Denoising failed: {e}", exc_info=True)
            return False
    
    async def _generate_waveform_async(self, file_id: str, audio_path: str):
        """
        Generate waveform in background thread, non-blocking.
        
        This runs parallel to the convert/remux stages for zero latency impact.
        Broadcasts waveform_update WebSocket event when complete.
        
        Uses its own database session to avoid SQLite lock contention
        with the main processing loop.
        """
        from services.waveform_generator import WaveformGenerator
        from services.websocket import manager
        from database import SessionLocal
        from pathlib import Path
        
        try:
            # Store waveforms in persistent app support directory
            waveform_dir = Path.home() / "Library/Application Support/StudioPipeline/waveforms"
            waveform_dir.mkdir(parents=True, exist_ok=True)
            
            generator = WaveformGenerator(str(waveform_dir))
            
            # Broadcast generating state
            await manager.send_waveform_update(file_id, 'GENERATING')
            
            # Use a separate DB session to avoid locking the main processing session
            waveform_db = SessionLocal()
            try:
                # Run in thread pool (FFmpeg I/O bound)
                loop = asyncio.get_event_loop()
                success = await loop.run_in_executor(
                    None,
                    generator.generate_waveform,
                    file_id,
                    audio_path,
                    waveform_db
                )
            finally:
                waveform_db.close()
            
            if success:
                await manager.send_waveform_update(file_id, 'READY')
                logger.info(f"✅ Waveform generated for file {file_id}")
            else:
                await manager.send_waveform_update(file_id, 'FAILED')
                logger.warning(f"Waveform generation failed for file {file_id}")
                
        except Exception as e:
            logger.error(f"Waveform async generation error: {e}")
            try:
                await manager.send_waveform_update(file_id, 'FAILED', str(e))
            except:
                pass
    
    async def run(self):
        """Main worker loop"""
        self.running = True
        logger.info("Process worker started")
        
        while self.running:
            try:
                # Respect global pause flag: when pause_processing == 'true', do not start new jobs
                try:
                    pause_setting = self.db.query(Setting).filter(Setting.key == 'pause_processing').first()
                    if pause_setting and str(pause_setting.value).lower() == 'true':
                        logger.debug("Processing is paused via settings; sleeping...")
                        await asyncio.sleep(1)
                        continue
                except Exception:
                    # If settings can't be read, proceed normally (defensive)
                    logger.debug("Could not read pause_processing setting; proceeding")

                job = self.db.query(Job).filter(
                    Job.kind == 'PROCESS',
                    Job.state == 'QUEUED'
                ).order_by(Job.priority.desc(), Job.created_at).first()
                
                if not job:
                    await asyncio.sleep(1)
                    continue
                
                async with self.semaphore:
                    await self._execute_process(job)
            
            except Exception as e:
                logger.error(f"Process worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def run_once(self):
        """Run a single iteration - check for job and process if found"""
        try:
            # Respect global pause flag
            try:
                pause_setting = self.db.query(Setting).filter(Setting.key == 'pause_processing').first()
                if pause_setting and str(pause_setting.value).lower() == 'true':
                    logger.debug("Run-once skipped because processing is paused")
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                logger.debug("Could not read pause_processing setting in run_once; proceeding")

            job = self.db.query(Job).filter(
                Job.kind == 'PROCESS',
                Job.state == 'QUEUED'
            ).order_by(Job.priority.desc(), Job.created_at).first()
            
            if not job:
                await asyncio.sleep(1)
                return
            
            async with self.semaphore:
                await self._execute_process(job)
        
        except Exception as e:
            logger.error(f"Process worker error: {e}", exc_info=True)
            await asyncio.sleep(5)
    
    def stop(self):
        """Stop the worker loop"""
        self.running = False
        logger.info("Process worker stopping...")
    
    async def _execute_process(self, job: Job):
        """Execute full audio enhancement pipeline
        
        Pipeline stages:
        1. Extract - Extract audio from video (.m4a)
        2. Boost - Normalize audio levels (.wav)
        3. Convert - Re-encode to AAC (.m4a)
        4. Remux - Merge enhanced audio with original video (.mp4)
        
        Note: ISO files (camera feeds) are skipped - only program output is processed
        """
        file = job.file
        
        # Skip ISO files - they don't get processed, only copied and organized
        if file.is_iso:
            # Check file size threshold
            min_size_mb = float(self._get_setting('iso_min_size_mb', '50'))
            min_size_bytes = int(min_size_mb * 1024 * 1024)
            file_size_mb = file.size / 1024 / 1024
            
            if file.size < min_size_bytes:
                # Small ISO file - skip entirely (don't organize)
                logger.info(
                    f"⏭️ Skipping small ISO file: {file.filename} "
                    f"({file_size_mb:.1f} MB < {min_size_mb:.0f} MB threshold)"
                )
                file.state = 'SKIPPED'
                job.state = 'DONE'
                job.progress_pct = 100
                job.completed_at = datetime.utcnow()
                self.db.commit()
                
                # Broadcast skip event
                event = Event(
                    file_id=file.id,
                    event_type='file_state_change',
                    payload_json=json.dumps({
                        'filename': file.filename,
                        'session_id': str(file.session_id),
                        'state': 'SKIPPED',
                        'progress_pct': 100,
                        'progress_stage': 'Skipped (below size threshold)',
                        'file_size_mb': round(file_size_mb, 1),
                        'threshold_mb': min_size_mb
                    })
                )
                self.db.add(event)
                self.db.commit()
                
                logger.info(f"Marked {file.filename} as SKIPPED (will not be organized)")
                return
            else:
                # Valid ISO file - mark as processed and queue for organizing
                logger.info(
                    f"✅ ISO file ready for organize: {file.filename} "
                    f"({file_size_mb:.1f} MB)"
                )
                file.state = 'PROCESSED'
                job.state = 'DONE'
                job.progress_pct = 100
                job.completed_at = datetime.utcnow()
                self.db.commit()
                
                # Broadcast event
                event = Event(
                    file_id=file.id,
                    event_type='file_state_change',
                    payload_json=json.dumps({
                        'filename': file.filename,
                        'session_id': str(file.session_id),
                        'state': 'PROCESSED',
                        'progress_pct': 100,
                        'progress_stage': 'Skipped processing (ISO file)',
                        'file_size_mb': round(file_size_mb, 1)
                    })
                )
                self.db.add(event)
                self.db.commit()
                
                # Queue for organizing (with deduplication)
                organize_job, created = job_integrity_service.get_or_create_job(
                    self.db,
                    file_id=file.id,
                    kind='ORGANIZE',
                    priority=job.priority
                )
                if created:
                    self.db.commit()
                logger.info(f"Queued ISO file for organizing: {file.filename}")
                return
        
        working_dir = Path(f"/tmp/pipeline/{file.id}")
        
        try:
            # Mark job as cancellable
            job.is_cancellable = True
            self.db.commit()
            
            # Validate temp path before starting
            temp_path = str(working_dir.parent)
            path_valid, path_error, _ = path_validator.ensure_directory(temp_path)
            if not path_valid:
                raise Exception(f"Temp path validation failed: {path_error}")
            
            # Clean and create working directory
            if working_dir.exists():
                shutil.rmtree(working_dir, ignore_errors=True)
            working_dir.mkdir(parents=True, exist_ok=True)
            
            # Update state
            job.state = 'RUNNING'
            job.started_at = datetime.utcnow()
            file.state = 'PROCESSING'
            self.db.commit()

            # Update worker status
            await worker_status_service.update_worker_status(
                'process',
                state='ACTIVE',
                job=job,
                file=file,
                stage='processing',
                substep='Starting enhancement pipeline'
            )

            # Check for cancellation before starting
            if await self.check_cancellation(job):
                raise CancellationRequested("Processing cancelled before start")
            
            # Broadcast processing started event
            event = Event(
                file_id=file.id,
                event_type='file_state_change',
                payload_json=json.dumps({
                    'filename': file.filename,
                    'session_id': str(file.session_id),
                    'state': 'PROCESSING',
                    'progress_pct': 0,
                    'progress_stage': 'Starting enhancement pipeline'
                })
            )
            self.db.add(event)
            self.db.commit()
            
            input_path = Path(file.path_local)
            
            # Verify input file exists
            file_exists, verify_error = path_validator.verify_file_exists(str(input_path))
            if not file_exists:
                raise FileNotFoundError(f"Input file verification failed: {verify_error}")
            
            logger.info(f"Starting processing: {file.filename}")
            
            # Define progress callback
            async def update_progress(data: dict):
                """Update job progress in database and broadcast event"""
                try:
                    # Refresh job to avoid stale state
                    self.db.expire(job)
                    current_job = self.db.query(Job).get(job.id)
                    if current_job:
                        stage_name = data.get('stage', 'processing')
                        progress = data.get('progress', 0)
                        
                        current_job.progress_stage = f"{stage_name}: {int(progress * 100)}%"
                        current_job.progress_pct = progress * 100
                        
                        # Update file's processing stage for substep visualization
                        current_file = self.db.query(File).get(file.id)
                        if current_file:
                            current_file.processing_stage = stage_name
                            current_file.processing_stage_progress = int(progress * 100)
                            # Create human-readable detail based on stage
                            stage_details = {
                                'extract': 'Extracting audio tracks from video',
                                'boost': 'Normalizing audio levels',
                                'denoise': 'Applying noise reduction',
                                'mp3export': 'Exporting MP3 audio',
                                'convert': 'Converting to high-quality AAC',
                                'remux': 'Merging enhanced audio with video',
                                'quadsplit': 'Creating quad-split view'
                            }
                            current_file.processing_detail = stage_details.get(stage_name, f'Processing: {stage_name}')
                        
                        self.db.commit()
                        
                        # Broadcast substep progress via WebSocket
                        from services.websocket import manager
                        await manager.send_processing_substep_update(
                            file_id=str(file.id),
                            substep=stage_name,
                            substep_progress=int(progress * 100),
                            session_id=str(file.session_id),
                            detail=current_file.processing_detail if current_file else None
                        )
                        
                        # Broadcast progress event (every 20% to avoid spam)
                        if int(progress * 100) % 20 == 0:
                            event = Event(
                                file_id=file.id,
                                event_type='file_state_change',
                                payload_json=json.dumps({
                                    'filename': file.filename,
                                    'session_id': str(file.session_id),
                                    'state': 'PROCESSING',
                                    'progress_pct': progress * 100,
                                    'progress_stage': current_job.progress_stage
                                })
                            )
                            self.db.add(event)
                            self.db.commit()
                        
                        logger.debug(f"Progress update: {stage_name} - {progress * 100:.1f}%")
                except Exception as e:
                    logger.warning(f"Failed to update progress: {e}")
            
            # Define pipeline stages
            # Pipeline: extract audio → boost levels → denoise (ONNX) → export MP3 → convert to AAC → remux with video
            # Get session name for MP3 filename
            session_name = file.session.name if file.session else "output"
            mp3_filename = f"{session_name}.mp3"

            stages = [
                ('extract', [
                    str(input_path),
                    str(working_dir / 'audio.m4a')
                ]),
                ('boost', [
                    str(working_dir / 'audio.m4a'),
                    str(working_dir / 'audio_boosted.wav')
                ]),
                # Denoise step (Python ONNX processing)
                ('denoise', [
                    str(working_dir / 'audio_boosted.wav'),
                    str(working_dir / 'audio_denoised.wav')
                ]),
                # NEW: Export denoised audio to MP3
                ('mp3export', [
                    str(working_dir / 'audio_denoised.wav'),
                    str(working_dir / mp3_filename)
                ]),
                ('convert', [
                    str(working_dir / 'audio_denoised.wav'),
                    str(working_dir / 'audio_final.m4a')
                ]),
                ('remux', [
                    str(input_path),
                    str(working_dir / 'audio_final.m4a'),
                    str(working_dir / 'remuxed.mp4')
                ]),
                # Gesture trim - detect closed fist and trim video (lossless)
                ('gesturetrim', [
                    str(working_dir / 'remuxed.mp4'),
                    str(working_dir / 'trimmed.mp4')
                ]),
                # Faststart - move moov atom to beginning for streaming
                ('faststart', [
                    str(working_dir / 'trimmed.mp4'),
                    str(working_dir / 'final.mp4')
                ])
            ]
            
            # Execute pipeline
            for stage_name, args in stages:
                # Check for cancellation between stages
                if await self.check_cancellation(job):
                    raise CancellationRequested(f"Processing cancelled before {stage_name} stage")
                
                logger.info(f"Running stage: {stage_name}")
                
                # Update processing stage at the start of each stage
                file.processing_stage = stage_name
                file.processing_stage_progress = 0
                stage_details = {
                    'extract': 'Extracting audio tracks from video',
                    'boost': 'Normalizing audio levels',
                    'denoise': 'Applying noise reduction',
                    'mp3export': 'Exporting MP3 audio',
                    'convert': 'Converting to high-quality AAC',
                    'remux': 'Merging enhanced audio with video',
                    'gesturetrim': 'Detecting gesture and trimming video',
                    'faststart': 'Optimizing for streaming',
                    'quadsplit': 'Creating quad-split view'
                }
                file.processing_detail = stage_details.get(stage_name, f'Processing: {stage_name}')
                self.db.commit()
                
                # Broadcast stage start via WebSocket
                from services.websocket import manager
                await manager.send_processing_substep_update(
                    file_id=file.id,
                    substep=stage_name,
                    substep_progress=0,
                    detail=file.processing_detail
                )

                # Update worker status with current substep
                await worker_status_service.update_worker_status(
                    'process',
                    substep=stage_name,
                    substep_progress=0,
                    detail=file.processing_detail
                )
                
                if stage_name == 'denoise':
                    # Use Python ONNX denoiser (run in thread pool since it's CPU-intensive)
                    loop = asyncio.get_event_loop()

                    # Create a synchronous progress wrapper for the thread pool
                    def sync_progress_wrapper(data: dict):
                        """Synchronous wrapper to schedule async progress update"""
                        try:
                            # Schedule the coroutine on the event loop
                            asyncio.run_coroutine_threadsafe(update_progress(data), loop)
                        except Exception as e:
                            logger.warning(f"Failed to schedule progress update: {e}")

                    success = await loop.run_in_executor(
                        None,  # Use default thread pool
                        self._denoise_audio,
                        Path(args[0]),
                        Path(args[1]),
                        sync_progress_wrapper  # Pass wrapped progress callback
                    )
                    if not success:
                        raise Exception(f"Denoise stage failed")
                    
                    # Waveform generation moved to organize_worker (after permanent file is on disk)
                    # The denoise temp file is unreliable — it gets cleaned up before generation completes
                elif stage_name == 'mp3export':
                    # Export MP3 using Swift tool (runs fast, no progress updates needed)
                    await self.swift.run_tool(
                        'mp3converter',
                        args,
                        progress_callback=None  # MP3 export is fast, no need for progress updates
                    )

                    # Store MP3 temp path for later copying to output
                    mp3_temp_path = Path(args[1])
                    file.mp3_temp_path = str(mp3_temp_path)
                    self.db.commit()
                    logger.info(f"MP3 exported to: {mp3_temp_path}")
                elif stage_name == 'gesturetrim':
                    # Gesture detection and lossless video trim
                    from utils.gesture_detector import GestureDetector, detect_gesture_trim_point
                    
                    input_video = Path(args[0])
                    output_video = Path(args[1])
                    
                    # Step 1: Detect gesture (run in thread pool - CPU intensive)
                    loop = asyncio.get_event_loop()
                    
                    try:
                        trim_timestamp = await loop.run_in_executor(
                            None,
                            detect_gesture_trim_point,
                            str(input_video)
                        )
                    except Exception as e:
                        logger.warning(f"Gesture detection failed: {e}, skipping trim")
                        trim_timestamp = None
                    
                    if trim_timestamp is None:
                        # No gesture detected - copy input to output unchanged
                        logger.info(f"No closed fist gesture detected - video unchanged")
                        shutil.copy(str(input_video), str(output_video))
                        file.gesture_trimmed = False
                        file.gesture_trim_skipped = True
                        self.db.commit()
                        
                        # Broadcast skipped status
                        await manager.send_processing_substep_update(
                            file_id=file.id,
                            substep='gesturetrim',
                            substep_progress=100,
                            detail='Gesture trim skipped - no gesture detected'
                        )
                    else:
                        # Step 2: Swift lossless trim
                        logger.info(f"Gesture detected at {trim_timestamp:.2f}s - trimming video")
                        await self.swift.run_tool(
                            'gesturetrim',
                            [str(input_video), str(output_video), str(trim_timestamp)],
                            progress_callback=update_progress
                        )
                        file.gesture_trimmed = True
                        file.gesture_trim_skipped = False
                        file.gesture_trim_point = trim_timestamp
                        self.db.commit()
                        logger.info(f"Video trimmed at {trim_timestamp:.2f}s")
                elif stage_name == 'faststart':
                    # Use ffmpeg to move moov atom for streaming optimization
                    from utils.ffmpeg_helper import get_ffmpeg_path
                    import subprocess
                    
                    input_video = Path(args[0])
                    output_video = Path(args[1])
                    
                    ffmpeg_path = get_ffmpeg_path()
                    cmd = [
                        ffmpeg_path,
                        '-i', str(input_video),
                        '-c', 'copy',  # No re-encoding, just copy streams
                        '-movflags', '+faststart',  # Move moov atom to start
                        '-y',  # Overwrite output
                        str(output_video)
                    ]
                    
                    logger.info(f"Running faststart: {' '.join(cmd)}")
                    
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: subprocess.run(cmd, capture_output=True, text=True)
                    )
                    
                    if result.returncode != 0:
                        logger.error(f"Faststart failed: {result.stderr}")
                        raise RuntimeError(f"Faststart failed: {result.stderr}")
                    
                    logger.info(f"Faststart complete: moov atom moved to beginning for streaming")
                else:
                    # Use Swift CLI tool
                    await self.swift.run_tool(
                        stage_name,
                        args,
                        progress_callback=update_progress
                    )
                
                # Verify output file was created after each stage
                # Resolve path to handle macOS /tmp -> /private/tmp symlink
                output_file = Path(args[-1]).resolve()
                file_exists, verify_error = path_validator.verify_file_exists(
                    str(output_file),
                    min_size_bytes=100  # At least 100 bytes
                )
                if not file_exists:
                    raise FileNotFoundError(f"Stage {stage_name} output verification failed: {verify_error}")
                
                logger.debug(f"Stage {stage_name} output verified: {output_file}")
                
                # Broadcast stage completion via WebSocket
                file.processing_stage_progress = 100
                self.db.commit()
                await manager.send_processing_substep_update(
                    file_id=file.id,
                    substep=stage_name,
                    substep_progress=100,
                    detail=f"{stage_details.get(stage_name, stage_name)} - Complete"
                )
            
            # Verify final output exists with minimum size
            final_output_path = working_dir / 'final.mp4'
            final_exists, final_error = path_validator.verify_file_exists(
                str(final_output_path),
                min_size_bytes=file.size // 2  # Expect at least half the original size
            )
            if not final_exists:
                raise FileNotFoundError(f"Final output verification failed: {final_error}")
            
            logger.info(f"Final output verified: {final_output_path} ({final_output_path.stat().st_size} bytes)")
            
            # Update records on success
            file.path_processed = str(final_output_path)
            file.state = 'PROCESSED'
            file.processing_stage = None  # Clear substep tracking
            file.processing_stage_progress = 0
            file.processing_detail = None
            job.state = 'DONE'
            job.progress_pct = 100
            job.progress_stage = "Complete"
            job.completed_at = datetime.utcnow()
            self.db.commit()
            
            # Clear any recovery tracking from previous failures
            self.clear_recovery_tracking(file)
            
            # Broadcast completion event
            event = Event(
                file_id=file.id,
                event_type='file_state_change',
                payload_json=json.dumps({
                    'filename': file.filename,
                    'session_id': str(file.session_id),
                    'state': 'PROCESSED',
                    'progress_pct': 100,
                    'path_processed': str(final_output_path)
                })
            )
            self.db.add(event)
            self.db.commit()
            
            logger.info(f"Processing complete: {file.filename} -> {final_output_path}")
            
            # Queue for organizing (with deduplication)
            # Propagate priority so program files stay ahead throughout the pipeline
            organize_job, created = job_integrity_service.get_or_create_job(
                self.db,
                file_id=file.id,
                kind='ORGANIZE',
                priority=job.priority
            )
            if created:
                self.db.commit()
            logger.info(f"Queued for organizing: {file.filename}")
        
        except CancellationRequested:
            # Cancellation already handled by WorkerBase
            logger.info(f"Processing cancelled for {file.filename}")
            await worker_status_service.clear_worker_status('process')

        except Exception as e:
            # Use WorkerBase retry-with-reset logic
            await self.handle_failure_with_reset(job, e)
            await worker_status_service.update_worker_status(
                'process',
                state='ERROR',
                error_message=str(e)
            )

        finally:
            # Mark job as no longer cancellable
            job.is_cancellable = False
            self.db.commit()

            # Clear worker status
            await worker_status_service.clear_worker_status('process')
