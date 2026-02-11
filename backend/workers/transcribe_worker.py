"""
Transcription Worker - Whisper-based audio transcription

This worker uses MLX Whisper to transcribe completed video files.
Only included when BUILD_WITH_AI is enabled.

Improvements:
- Model validation at job time
- Configuration from database
- Provenance tracking
- No automatic retry (manual reset only)
"""
import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from models import File, Job, Event
from models_analytics import FileAnalytics
from workers.base_worker import WorkerBase
from services.ai_config_service import AIConfigService
from services.worker_status_service import worker_status_service
from config.ai_config import get_model_path, ModelValidationError
from utils.language_names import get_language_name
from services.ai_mutex import gpu_lock, shutting_down
import utils.ffmpeg_helper  # Sets FFMPEG_BINARY env var for mlx-whisper

try:
    import mlx_whisper
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    logging.warning("⚠️  mlx-whisper not available - transcription disabled")

logger = logging.getLogger(__name__)

# Dedicated single-thread executor for Whisper to avoid overlapping MLX context usage
_WHISPER_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx_whisper")


class TranscribeWorker(WorkerBase):
    """
    Worker that transcribes video files using Whisper (MLX optimized).
    
    Process:
    1. Validate model availability
    2. Load video file from final output path
    3. Apply transcription settings from database
    4. Run MLX Whisper transcription
    5. Save transcript with provenance metadata
    6. Create ANALYZE job for LLM processing
    
    Retry Policy:
    - No automatic retry
    - Failures require manual status reset via API
    
    Job Flow:
    TRANSCRIBE job (state=QUEUED) → TRANSCRIBING → TRANSCRIBED → create ANALYZE job
    """
    
    def __init__(self, db: Session):
        super().__init__(db)
        self.model = None
        self.config_service = AIConfigService(db)
        
        # Monkey-patch mlx-whisper to use bundled ffmpeg
        utils.ffmpeg_helper.patch_mlx_whisper()

    async def run_once(self):
        """Run a single iteration - check for TRANSCRIBE job and process if found"""
        try:
            # Query for highest priority TRANSCRIBE job
            job = self.db.query(Job).filter(
                Job.kind == 'TRANSCRIBE',
                Job.state == 'QUEUED'
            ).order_by(Job.priority.desc(), Job.created_at).first()


            if not job:
                await asyncio.sleep(1)
                return

            # Process the job
            await self.process_job(job)

        except Exception as e:
            logger.error(f"Error in transcribe worker run_once: {e}", exc_info=True)
            await asyncio.sleep(5)
    async def process_job(self, job: Job) -> None:
        """
        Transcribe a video file using Whisper.
        
        Args:
            job: TRANSCRIBE job with associated file
            
        Raises:
            ModelValidationError: If Whisper model not available
            Exception: If transcription fails
        """
        if not MLX_AVAILABLE:
            raise ModelValidationError("mlx-whisper not installed")
        
        # Validate model at job time
        model_path = Path(get_model_path('whisper'))
        if not model_path.exists():
            raise ModelValidationError(
                f"Whisper model not found at {model_path}. "
                "Run model download script or check app bundle."
            )
        
        file = job.file
        analytics = self._get_or_create_analytics(file)
        
        try:
            # Get transcription settings
            whisper_settings = self.config_service.get_whisper_settings()
            model_version = self.config_service.get_model_versions()['whisper']
            
            # Update state
            analytics.state = 'TRANSCRIBING'
            analytics.transcription_started_at = datetime.utcnow()
            analytics.whisper_model_version = model_version
            analytics.transcription_settings_json = json.dumps(whisper_settings)
            job.is_cancellable = True
            self.db.commit()

            # Update worker status
            await worker_status_service.update_worker_status(
                'transcribe',
                state='ACTIVE',
                job=job,
                file=file,
                detail='Transcribing audio with Whisper',
                wait_reason='MLX inference'
            )

            logger.info(f"🎤 Starting transcription for {file.filename}")
            from services.websocket import manager as websocket_manager
            await websocket_manager.send_analytics_state(file.id, file.filename, 'TRANSCRIBING')
            
            # Check for cancellation before heavy work
            if await self.check_cancellation(job):
                return
            
            # Get the video file path
            video_path = self._get_video_path(file)
            if not video_path.exists():
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            # Run transcription (blocking operation)
            transcription_result = await self._transcribe_file(
                video_path,
                whisper_settings,
                model_version,
                job
            )

            # Extract text and language from result
            if isinstance(transcription_result, dict):
                transcript_text = transcription_result.get('text', '')
                detected_language_code = transcription_result.get('language', 'en')
            else:
                transcript_text = str(transcription_result)
                detected_language_code = 'en'

            # Convert language code to full name
            detected_language = get_language_name(detected_language_code)

            # Save transcript and detected language
            analytics.transcript = transcript_text
            analytics.detected_language = detected_language
            analytics.state = 'TRANSCRIBED'
            analytics.transcription_completed_at = datetime.utcnow()

            # Calculate duration
            if analytics.transcription_started_at:
                duration = (analytics.transcription_completed_at - analytics.transcription_started_at).total_seconds()
                analytics.transcription_duration_seconds = int(duration)

            job.state = 'DONE'
            job.completed_at = datetime.utcnow()
            job.is_cancellable = False
            self.db.commit()

            logger.info(f"✅ Transcription complete for {file.filename} ({len(transcript_text)} chars, {detected_language})")
            from services.websocket import manager as websocket_manager
            await websocket_manager.send_analytics_state(file.id, file.filename, 'TRANSCRIBED', {
                'transcript_length': len(transcript_text),
                'language': detected_language
            })

            # Automatically create ANALYZE job after transcription completes
            self._create_analyze_job(file, analytics)

            # Clear worker status
            await worker_status_service.clear_worker_status('transcribe')

        except ModelValidationError as e:
            logger.error(f"❌ Model validation failed for {file.filename}: {e}")
            self._mark_failed(job, analytics, str(e))
            await worker_status_service.update_worker_status(
                'transcribe',
                state='ERROR',
                error_message=str(e)
            )

        except Exception as e:
            logger.error(f"❌ Transcription failed for {file.filename}: {e}")
            self._mark_failed(job, analytics, str(e))
            await worker_status_service.update_worker_status(
                'transcribe',
                state='ERROR',
                error_message=str(e)
            )
    
    def _get_or_create_analytics(self, file: File) -> FileAnalytics:
        """Get or create FileAnalytics record for file"""
        analytics = self.db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file.id
        ).first()
        
        if not analytics:
            analytics = FileAnalytics(
                file_id=file.id,
                filename=file.filename,
                state='PENDING'
            )
            self.db.add(analytics)
            self.db.commit()
            self.db.refresh(analytics)
        
        return analytics
    
    def _get_video_path(self, file: File) -> Path:
        """
        Get path to audio/video file for transcription.

        Priority:
        1. AI analytics cache MP3 (if external export enabled and path exists)
        2. Final video file (from output_path)

        Using the AI analytics cache avoids issues with OneDrive "Free Up Space"
        deleting video files locally after they're uploaded to SharePoint.
        """
        # Check AI analytics cache first (faster, more reliable for scheduled jobs)
        if file.external_export_path:
            cache_dir = Path(file.external_export_path)
            if cache_dir.exists():
                # Find MP3 file in the UUID folder
                mp3_files = list(cache_dir.glob('*.mp3'))
                if mp3_files:
                    mp3_path = mp3_files[0]  # Use first (should only be one)
                    logger.info(f"Using AI analytics cache audio: {mp3_path}")
                    return mp3_path
                else:
                    logger.warning(f"AI analytics cache directory exists but no MP3 found: {cache_dir}")

        # Fallback to final video file
        if file.path_final:
            video_path = Path(file.path_final)
            logger.info(f"Using final video file: {video_path}")
            return video_path

        # Last resort: construct path from output_path setting
        from models import Setting
        output_root = self.db.query(Setting).filter(
            Setting.key == 'output_path'
        ).first()

        if not output_root or not output_root.value:
            raise ValueError("Output path not configured in settings")

        constructed_path = Path(file.get_final_output_path(output_root.value))
        logger.info(f"Using constructed video path: {constructed_path}")
        return constructed_path
    
    async def _transcribe_file(
        self,
        video_path: Path,
        settings: dict,
        model_version: str,
        job: Job
    ) -> dict:
        """
        Run Whisper transcription on video file.

        Args:
            video_path: Path to video file
            settings: Whisper settings from configuration
            model_version: Model version identifier
            job: Job for cancellation checking

        Returns:
            Dictionary with 'text' and 'language' keys
        """
        logger.debug(f"Transcribing {video_path} with model {model_version}")
        logger.debug(f"Settings: {settings}")

        # Run in thread pool to avoid blocking, but serialize GPU/Metal access with global lock
        loop = asyncio.get_event_loop()
        if gpu_lock.locked():
            logger.warning("⏳ GPU lock busy - waiting before Whisper transcription")
        wait_start = asyncio.get_event_loop().time()
        async with gpu_lock:
            waited_ms = int((asyncio.get_event_loop().time() - wait_start) * 1000)
            if waited_ms > 0:
                logger.warning(f"🔒 Acquired GPU lock for Whisper after {waited_ms}ms")
            else:
                logger.warning("🔒 Acquired GPU lock for Whisper immediately")
            if shutting_down.is_set():
                raise RuntimeError("Shutting down - skipping Whisper transcription")
            result = await loop.run_in_executor(
                _WHISPER_EXECUTOR,
                self._run_whisper_sync,
                str(video_path),
                settings,
                model_version
            )
        logger.warning("🔓 Released GPU lock after Whisper transcription")

        # Ensure result is a dictionary with text and language
        if isinstance(result, dict):
            return result
        elif isinstance(result, str):
            return {'text': result, 'language': 'en'}
        else:
            raise ValueError(f"Unexpected Whisper result type: {type(result)}")
    
    def _run_whisper_sync(
        self,
        audio_path: str,
        settings: dict,
        model_version: str
    ) -> dict:
        """
        Synchronous Whisper transcription (runs in thread pool).
        
        Args:
            audio_path: Path to audio/video file
            settings: Whisper settings
            model_version: Model version
            
        Returns:
            Transcription result dictionary
        """
        try:
            # Use bundled model path
            model_path = get_model_path('whisper')
            
            # Prepare Whisper parameters
            transcribe_params = {
                'path_or_hf_repo': str(model_path),
                'verbose': False,
                'word_timestamps': settings.get('word_timestamps', False),
                'temperature': settings.get('temperature', 0.0),
            }
            
            # Add language if specified
            if settings.get('language'):
                transcribe_params['language'] = settings['language']
            
            # Add translation flag
            if settings.get('translate_to_english', False):
                transcribe_params['task'] = 'translate'
            
            # Add initial_prompt with custom vocabulary/proper nouns
            # This helps Whisper correctly transcribe domain-specific terms
            prompt_words = settings.get('prompt_words', '').strip()
            if prompt_words:
                # Use the prompt_words as initial_prompt to guide transcription
                transcribe_params['initial_prompt'] = prompt_words
                logger.info(f"Using Whisper prompt words: {prompt_words[:100]}...")
            
            # Run transcription
            result = mlx_whisper.transcribe(audio_path, **transcribe_params)
            
            return result
            
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            raise
    
    def _create_analyze_job(self, file: File, analytics: FileAnalytics):
        """Create ANALYZE job for LLM processing"""
        from utils.uuid_helper import generate_uuid

        analyze_job = Job(
            id=generate_uuid(),
            file_id=file.id,
            kind='ANALYZE',
            state='QUEUED',
            priority=200,  # Default AI priority
            max_retries=0,  # No automatic retry
            created_at=datetime.utcnow()
        )
        self.db.add(analyze_job)
        self.db.commit()

        logger.info(f"📊 Created ANALYZE job for {file.filename}")

        asyncio.create_task(self._broadcast_event('job.created', file, {
            'job_id': analyze_job.id,
            'kind': 'ANALYZE'
        }))
    
    def _mark_failed(self, job: Job, analytics: FileAnalytics, error: str):
        """
        Mark job and analytics as failed.
        No automatic retry - requires manual reset.
        """
        job.state = 'FAILED'
        job.error_message = error
        job.is_cancellable = False
        
        analytics.state = 'FAILED'
        analytics.error_message = error
        analytics.retry_count += 1
        
        self.db.commit()
        
        logger.error(f"❌ Marked as FAILED (no auto-retry): {analytics.filename}")
        
        from services.websocket import manager as websocket_manager
        asyncio.create_task(websocket_manager.send_analytics_state(job.file.id, job.file.filename, 'FAILED', {
            'error': error,
            'stage': 'transcription'
        }))
    
    async def _broadcast_event(self, event_type: str, file: File, extra_data: dict = None):
        """Broadcast WebSocket event"""
        from services.websocket import manager as websocket_manager

        data = {
            'type': event_type,
            'file_id': file.id,
            'filename': file.filename
        }

        if extra_data:
            data.update(extra_data)

        await websocket_manager.broadcast(data)
