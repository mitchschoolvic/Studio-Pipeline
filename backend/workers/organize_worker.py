import asyncio
from pathlib import Path
from sqlalchemy.orm import Session
from models import File, Job, Setting, Event
from workers.base_worker import WorkerBase, CancellationRequested
from services.path_validator import path_validator
from config.ai_config import AI_ENABLED
from datetime import datetime
import shutil
import logging
import json

logger = logging.getLogger(__name__)

if AI_ENABLED:
    from services.analytics_service import AnalyticsService


class OrganizeWorker(WorkerBase):
    def __init__(self, db: Session, semaphore: asyncio.Semaphore):
        super().__init__(db)
        self.semaphore = semaphore
        self.running = False
    
    def _get_setting(self, key):
        """Helper to get setting value from DB"""
        setting = self.db.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else None
    
    async def run(self):
        """Main worker loop"""
        self.running = True
        logger.info("Organize worker started")
        
        while self.running:
            try:
                # Respect global pause flag: do not start ORGANIZE jobs when paused
                try:
                    pause_val = self._get_setting('pause_processing')
                    if pause_val and str(pause_val).lower() == 'true':
                        logger.debug('Organize worker paused via settings; sleeping...')
                        await asyncio.sleep(1)
                        continue
                except Exception:
                    logger.debug('Could not read pause_processing setting for organize worker; proceeding')

                job = self.db.query(Job).filter(
                    Job.kind == 'ORGANIZE',
                    Job.state == 'QUEUED'
                ).order_by(Job.priority.desc(), Job.created_at).first()
                
                if not job:
                    await asyncio.sleep(1)
                    continue
                
                async with self.semaphore:
                    await self._execute_organize(job)
            
            except Exception as e:
                logger.error(f"Organize worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def run_once(self):
        """Run a single iteration - check for job and process if found"""
        try:
            # Respect global pause flag
            try:
                pause_val = self._get_setting('pause_processing')
                if pause_val and str(pause_val).lower() == 'true':
                    logger.debug('Organize run_once skipped because processing is paused')
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                logger.debug('Could not read pause_processing setting in organize run_once; proceeding')

            job = self.db.query(Job).filter(
                Job.kind == 'ORGANIZE',
                Job.state == 'QUEUED'
            ).order_by(Job.priority.desc(), Job.created_at).first()
            
            if not job:
                await asyncio.sleep(1)
                return
            
            async with self.semaphore:
                await self._execute_organize(job)
        
        except Exception as e:
            logger.error(f"Organize worker error: {e}", exc_info=True)
            await asyncio.sleep(5)
    
    def stop(self):
        """Stop the worker loop"""
        self.running = False
        logger.info("Organize worker stopping...")
    
    async def _execute_organize(self, job: Job):
        """Move the processed file to the final output path"""
        file = job.file
        session = file.session
        
        try:
            # Mark job as cancellable
            job.is_cancellable = True
            self.db.commit()
            
            job.state = 'RUNNING'
            job.started_at = datetime.utcnow()
            file.state = 'ORGANIZING'
            self.db.commit()
            
            # Check for cancellation before starting
            if await self.check_cancellation(job):
                raise CancellationRequested("Organize cancelled before start")
            
            # Broadcast organizing started event
            event = Event(
                file_id=file.id,
                event_type='file_state_change',
                payload_json=json.dumps({
                    'filename': file.filename,
                    'session_id': str(file.session_id),
                    'state': 'ORGANIZING',
                    'progress_pct': 0
                })
            )
            self.db.add(event)
            self.db.commit()
            
            output_base_path_str = self._get_setting('output_path')
            if not output_base_path_str:
                raise ValueError("output_path setting not found")
            
            # Validate and ensure output path exists
            path_valid, path_error, output_base_path = path_validator.ensure_directory(output_base_path_str)
            if not path_valid:
                raise Exception(f"Output path validation failed: {path_error}")
            
            # Use new get_final_output_path method to calculate destination
            # This preserves directory structure: {output}/{year}/{month}/{day}/{session_folder}/{relative_path}
            # Example: /output/2025/10 - October/30 Thu October/Haileybury Studio 11/Haileybury Studio 01.mp4
            # Example: /output/2025/10 - October/30 Thu October/Haileybury Studio 11/Source Files/CAM 1 01.mp4
            # Note: Any subfolders from FTP are renamed to "Source Files" in output
            final_path = Path(file.get_final_output_path(output_base_path_str))
            
            # Ensure all parent directories exist (including session folder and any subfolders)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Final destination: {final_path}")
            
            # Determine source file path
            if file.is_iso:
                # ISO files: move from temp_processing/{file_id}/{relative_path}
                # They were copied but not processed
                source_path = Path(file.path_local)
                logger.info(f"Moving ISO file from temp storage: {source_path}")
            else:
                # Program output files: move from processing output
                source_path = Path(file.path_processed)
                logger.info(f"Moving processed file: {source_path}")
            
            # Verify source file exists
            source_exists, source_error = path_validator.verify_file_exists(str(source_path))
            if not source_exists:
                raise FileNotFoundError(f"Source file verification failed: {source_error}")
            
            source_size = source_path.stat().st_size
            logger.info(f"Source file verified: {source_path} ({source_size} bytes)")
            
            # Check for cancellation before the move (organize is fast, so one check is sufficient)
            if await self.check_cancellation(job):
                raise CancellationRequested("Organize cancelled before move")
            
            # Move (rename) the file to the final path
            logger.info(f"Moving {source_path} to {final_path}")
            shutil.move(str(source_path), str(final_path))
            
            # Verify the moved file exists and has the expected size
            final_exists, final_error = path_validator.verify_file_exists(
                str(final_path),
                min_size_bytes=source_size - 1024  # Allow 1KB tolerance
            )
            if not final_exists:
                raise Exception(f"Final file verification failed after move: {final_error}")
            
            logger.info(f"Final file verified: {final_path} ({final_path.stat().st_size} bytes)")

            # Copy MP3 to "Source Files" subdirectory (if it exists)
            if file.mp3_temp_path and Path(file.mp3_temp_path).exists():
                mp3_source = Path(file.mp3_temp_path)

                # Determine MP3 destination: always in "Source Files/SessionName" subdirectory
                # For program output (in Day folder): .../Day/Source Files/SessionName/MP3.mp3
                # For ISO files (in SessionName folder): .../Day/Source Files/SessionName/MP3.mp3
                
                if file.is_in_subfolder:
                    # ISO file is already in .../Day/Source Files/SessionName
                    mp3_dest_dir = final_path.parent
                else:
                    # Program file is in .../Day
                    # Need to construct Source Files/SessionName
                    session_folder = file.session_folder or (file.session.name if file.session else None) or 'unknown'
                    mp3_dest_dir = final_path.parent / "Source Files" / session_folder

                # Create directory
                mp3_dest_dir.mkdir(parents=True, exist_ok=True)

                # Place MP3 in destination directory
                mp3_final = mp3_dest_dir / mp3_source.name

                logger.info(f"Copying MP3: {mp3_source} -> {mp3_final}")
                shutil.copy2(str(mp3_source), str(mp3_final))

                # Verify MP3 copy
                if mp3_final.exists():
                    logger.info(f"MP3 exported: {mp3_final} ({mp3_final.stat().st_size} bytes)")
                else:
                    logger.warning(f"MP3 copy verification failed: {mp3_final}")

                # Clean up temp MP3
                try:
                    mp3_source.unlink()
                    logger.debug(f"Deleted temp MP3: {mp3_source}")
                except Exception as e:
                    logger.warning(f"Could not delete temp MP3: {e}")

                # Export Audio for External Use feature
                # If enabled, copy MP3 and thumbnail to external path with parent folder structure
                external_audio_enabled = self._get_setting('external_audio_export_enabled')
                external_audio_path = self._get_setting('external_audio_export_path')

                if external_audio_enabled and str(external_audio_enabled).lower() == 'true' and external_audio_path:
                    try:
                        # Validate external path
                        ext_path_valid, ext_path_error, ext_base_path = path_validator.ensure_directory(str(external_audio_path))
                        if ext_path_valid:
                            # Get session name (without .mp3 extension)
                            session_name = mp3_final.stem  # filename without extension

                            # Create UUID-based folder for AI analytics
                            # This ensures reliable access for transcription even when OneDrive "Free Up Space" deletes local files
                            external_file_dir = Path(ext_base_path) / file.id
                            external_file_dir.mkdir(parents=True, exist_ok=True)

                            # Copy MP3 to external location with human-readable filename
                            external_mp3_path = external_file_dir / mp3_final.name

                            logger.info(f"Exporting MP3 to AI analytics cache: {external_mp3_path}")
                            shutil.copy2(str(mp3_final), str(external_mp3_path))

                            # Verify external copy
                            if external_mp3_path.exists():
                                logger.info(f"AI analytics MP3 export successful: {external_mp3_path} ({external_mp3_path.stat().st_size} bytes)")
                                # Track the UUID folder path for AI workers to use
                                file.external_export_path = str(external_file_dir)
                            else:
                                logger.warning(f"AI analytics MP3 export verification failed: {external_mp3_path}")

                            # Copy thumbnail to external location (if available)
                            if file.thumbnail_path and Path(file.thumbnail_path).exists():
                                thumbnail_source = Path(file.thumbnail_path)
                                # Use session name as thumbnail filename for readability
                                thumbnail_ext = thumbnail_source.suffix  # .jpg or .png
                                external_thumbnail_path = external_file_dir / f"{session_name}{thumbnail_ext}"

                                logger.info(f"Exporting thumbnail to AI analytics cache: {external_thumbnail_path}")
                                shutil.copy2(str(thumbnail_source), str(external_thumbnail_path))

                                # Verify thumbnail copy
                                if external_thumbnail_path.exists():
                                    logger.info(f"AI analytics thumbnail export successful: {external_thumbnail_path} ({external_thumbnail_path.stat().st_size} bytes)")
                                else:
                                    logger.warning(f"AI analytics thumbnail export verification failed: {external_thumbnail_path}")
                            else:
                                logger.debug(f"No thumbnail available for AI analytics export: {file.filename}")

                        else:
                            logger.warning(f"AI analytics cache path validation failed: {ext_path_error}")
                    except Exception as e:
                        logger.error(f"Failed to export to AI analytics cache: {e}", exc_info=True)
                        # Don't fail the job if external export fails - it's an optional feature

            # Update records
            file.path_final = str(final_path)
            file.state = 'COMPLETED'
            job.state = 'DONE'
            job.progress_pct = 100
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
                    'state': 'COMPLETED',
                    'progress_pct': 100,
                    'path_final': str(final_path)
                })
            )
            self.db.add(event)
            self.db.commit()

            logger.info(f"Organized: {final_path}")

            # Trigger waveform generation from the permanent final file
            # Must happen BEFORE temp directory cleanup below
            if file.is_program_output and file.waveform_state in ('PENDING', 'FAILED'):
                try:
                    asyncio.create_task(self._generate_waveform_async(
                        file_id=file.id,
                        audio_path=str(final_path),
                    ))
                    logger.info(f"Queued waveform generation for {file.filename}")
                except Exception as e:
                    logger.warning(f"Failed to queue waveform generation: {e}")

            # Queue analytics if enabled
            if AI_ENABLED:
                try:
                    logger.info(f"🤖 AI_ENABLED=True, attempting to queue analytics for {file.filename}")
                    analytics_service = AnalyticsService(self.db)
                    result = analytics_service.queue_analytics_for_file(file)
                    if result:
                        logger.info(f"✅ Successfully queued analytics for {file.filename}")
                    else:
                        logger.info(f"ℹ️  Analytics not queued for {file.filename} (already exists or ineligible)")
                except Exception as e:
                    logger.error(f"❌ Failed to queue analytics for {file.filename}: {e}", exc_info=True)

            # Clean up temp directories
            # 1. Processing directory (for non-ISO files): /tmp/pipeline/{file_id}/
            if file.path_processed and not file.is_iso:
                temp_processing_dir = Path(file.path_processed).parent
                if temp_processing_dir.exists() and '/tmp/pipeline/' in str(temp_processing_dir):
                    shutil.rmtree(temp_processing_dir, ignore_errors=True)
                    logger.info(f"Cleaned up processing directory: {temp_processing_dir}")
            
            # 2. Download directory: /temp_processing/{file_id}/
            if file.path_local:
                local_path = Path(file.path_local)
                
                # Find the file_id directory (go up to parent if in subfolder)
                file_id_dir = local_path.parent
                if file.is_in_subfolder:
                    file_id_dir = file_id_dir.parent
                
                # Safety check: directory name should be the file_id (UUID)
                if file_id_dir.exists() and file_id_dir.name == file.id:
                    shutil.rmtree(file_id_dir, ignore_errors=True)
                    logger.info(f"Cleaned up download directory: {file_id_dir}")
                
                # Clear path_local
                file.path_local = None
                self.db.commit()
        
        except CancellationRequested:
            # Cancellation already handled by WorkerBase
            logger.info(f"Organize cancelled for {file.filename}")
        
        except Exception as e:
            # Use WorkerBase retry-with-reset logic
            await self.handle_failure_with_reset(job, e)
        
        finally:
            # Mark job as no longer cancellable
            job.is_cancellable = False
            self.db.commit()

    async def _generate_waveform_async(self, file_id: str, audio_path: str):
        """
        Generate waveform in background thread, non-blocking.
        Uses the permanent final file path (not temp files).
        """
        from services.waveform_generator import WaveformGenerator
        from services.websocket import manager
        from database import SessionLocal

        try:
            waveform_dir = Path.home() / "Library/Application Support/StudioPipeline/waveforms"
            waveform_dir.mkdir(parents=True, exist_ok=True)

            generator = WaveformGenerator(str(waveform_dir))

            await manager.send_waveform_update(file_id, 'GENERATING')

            waveform_db = SessionLocal()
            try:
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
                logger.info(f"Waveform generated for file {file_id}")
            else:
                await manager.send_waveform_update(file_id, 'FAILED')
                logger.warning(f"Waveform generation failed for file {file_id}")

        except Exception as e:
            logger.error(f"Waveform async generation error: {e}")
            try:
                await manager.send_waveform_update(file_id, 'FAILED', str(e))
            except Exception:
                pass
