import asyncio
from pathlib import Path
from sqlalchemy.orm import Session
from models import File, Job, Event
from workers.ftp_client import FTPClient
from workers.base_worker import WorkerBase, CancellationRequested
from services.path_validator import path_validator
from services.worker_status_service import worker_status_service
from services.job_integrity_service import job_integrity_service
from datetime import datetime
import logging
import json

logger = logging.getLogger(__name__)


class CopyWorker(WorkerBase):
    def __init__(self, db: Session, ftp_config: dict, semaphore: asyncio.Semaphore, shared_ftp: FTPClient = None):
        super().__init__(db)  # Initialize WorkerBase
        self.ftp_config = ftp_config
        self.semaphore = semaphore
        self.ftp = None
        self._shared_ftp = shared_ftp  # Reusable FTP connection from worker pool
        self._owns_ftp = False  # Track whether we created the FTP connection
        self.running = False
    
    async def run(self):
        """Main worker loop"""
        self.running = True
        logger.info("Copy worker started")
        
        while self.running:
            try:
                # Get next COPY job
                job = self.db.query(Job).filter(
                    Job.kind == 'COPY',
                    Job.state == 'QUEUED'
                ).order_by(Job.priority.desc(), Job.created_at).first()
                
                if not job:
                    await asyncio.sleep(1)
                    continue
                
                async with self.semaphore:
                    await self._execute_copy(job)
            
            except Exception as e:
                logger.error(f"Copy worker error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def run_once(self):
        """Run a single iteration - check for job and process if found"""
        try:
            # Get next COPY job
            job = self.db.query(Job).filter(
                Job.kind == 'COPY',
                Job.state == 'QUEUED'
            ).order_by(Job.priority.desc(), Job.created_at).first()
            
            if not job:
                await asyncio.sleep(1)
                return
            
            async with self.semaphore:
                await self._execute_copy(job)
        
        except Exception as e:
            logger.error(f"Copy worker error: {e}", exc_info=True)
            await asyncio.sleep(5)
    
    def stop(self):
        """Stop the worker loop"""
        self.running = False
        logger.info("Copy worker stopping...")
    
    async def _execute_copy(self, job: Job):
        """Execute a single copy operation with cancellation support"""
        file = job.file

        try:
            # Mark job as cancellable
            job.is_cancellable = True
            job.state = 'RUNNING'
            job.started_at = datetime.utcnow()
            self.db.commit()

            # Update file state
            file.state = 'COPYING'
            self.db.commit()

            # Update worker status
            await worker_status_service.update_worker_status(
                'copy',
                state='ACTIVE',
                job=job,
                file=file,
                stage='download',
                wait_reason='Network transfer'
            )
            
            # Broadcast state change event
            event = Event(
                file_id=file.id,
                event_type='file_state_change',
                payload_json=json.dumps({
                    'filename': file.filename,
                    'session_id': str(file.session_id),
                    'state': 'COPYING',
                    'progress_pct': 0,
                    'copy_speed_mbps': 0
                })
            )
            self.db.add(event)
            self.db.commit()
            
            logger.info(f"Starting copy: {file.filename}")
            
            # Validate temp path before starting copy
            temp_path = self.ftp_config.get('temp_path', '/tmp/pipeline')
            if not temp_path:
                raise Exception("Temporary storage path is not configured. Please check your settings.")
            
            loop = asyncio.get_event_loop()
            
            # Run path validation in executor
            path_valid, path_error, temp_path_obj = await loop.run_in_executor(
                None, path_validator.ensure_directory, temp_path
            )
            if not path_valid:
                raise Exception(f"Cannot access temporary storage: {path_error}")
            
            # Acquire FTP connection (reuse shared or create new)
            if self._shared_ftp is not None:
                try:
                    await self._shared_ftp.ensure_connected()
                    self.ftp = self._shared_ftp
                    self._owns_ftp = False
                except Exception as e:
                    logger.warning(f"Shared FTP health-check failed, creating new connection: {e}")
                    self._shared_ftp = None
                    self._owns_ftp = True
            
            if self.ftp is None:
                self.ftp = FTPClient(
                    host=self.ftp_config.get('ftp_host', self.ftp_config.get('host', 'localhost')),
                    port=int(self.ftp_config.get('ftp_port', self.ftp_config.get('port', 21))),
                    username=self.ftp_config.get('ftp_username', self.ftp_config.get('username', 'anonymous')),
                    password=self.ftp_config.get('ftp_password', self.ftp_config.get('password', ''))
                )
                await self.ftp.connect()
                self._owns_ftp = True

            # Re-query file size from FTP before download (ATEM write-race fix)
            # ATEM may report pre-allocated sizes during LIST that differ from final size
            try:
                current_size = await self.ftp.get_file_size(file.path_remote)
                if current_size and current_size != file.size:
                    logger.info(f"FTP size changed for {file.filename}: {file.size} -> {current_size} (ATEM write-race)")
                    file.size = current_size
                    self.db.commit()
            except Exception as e:
                logger.debug(f"Could not re-query file size for {file.filename}: {e}")
            
            # Use file_id-based temp directory to prevent collisions
            # Structure: {temp_path}/{file_id}/{relative_path}
            try:
                local_path = Path(file.get_temp_processing_path(str(temp_path_obj)))
            except (TypeError, ValueError) as e:
                raise Exception(f"Cannot determine storage path for file '{file.filename}'. The file may have incomplete information.")
            
            # Ensure parent directories exist (for ISO files in subfolders)
            try:
                await loop.run_in_executor(None, lambda: local_path.parent.mkdir(parents=True, exist_ok=True))
            except Exception as e:
                raise Exception(f"Cannot create storage directory: {str(e)}")
            
            logger.info(f"Downloading to isolated temp directory: {local_path}")
            
            # Track speed calculation
            speed_tracker = {
                'last_update': datetime.utcnow(),
                'last_bytes': 0,
                'last_cancel_check': 0
            }
            
            speed_mbps = 0
            CHECK_INTERVAL_BYTES = 10 * 1024 * 1024  # Check for cancellation every 10 MB

            # Define progress callback with cancellation check
            async def progress(downloaded_bytes):
                nonlocal speed_mbps
                
                # Periodic cancellation check (every 10 MB or more)
                if downloaded_bytes - speed_tracker['last_cancel_check'] >= CHECK_INTERVAL_BYTES:
                    if await self.check_cancellation(job):
                        raise CancellationRequested("Copy cancelled by user")
                    speed_tracker['last_cancel_check'] = downloaded_bytes
                
                # Update heartbeat to indicate worker is alive
                self.update_heartbeat(job)
                
                # Refresh job from DB to avoid stale state
                self.db.expire(job)
                progress_pct = (downloaded_bytes / file.size) * 100 if file.size > 0 else 100
                job.progress_pct = min(progress_pct, 100)
                
                # Calculate speed in MB/s
                now = datetime.utcnow()
                time_delta = (now - speed_tracker['last_update']).total_seconds()
                bytes_delta = downloaded_bytes - speed_tracker['last_bytes']
                
                # Calculate speed (MB/s) and broadcast progress - update every second
                if time_delta >= 1.0:
                    speed_mbps = (bytes_delta / time_delta) / (1024 * 1024) if time_delta > 0 else 0
                    speed_tracker['last_update'] = now
                    speed_tracker['last_bytes'] = downloaded_bytes

                    job.progress_stage = f"Downloading: {downloaded_bytes / (1024**2):.1f} MB @ {speed_mbps:.1f} MB/s"

                    # Update worker status with speed
                    asyncio.create_task(worker_status_service.update_worker_status(
                        'copy',
                        speed_mbps=speed_mbps,
                        progress_pct=progress_pct
                    ))

                    event = Event(
                        file_id=file.id,
                        event_type='file_state_change',
                        payload_json=json.dumps({
                            'filename': file.filename,
                            'session_id': str(file.session_id),
                            'state': 'COPYING',
                            'progress_pct': progress_pct,
                            'progress_stage': job.progress_stage,
                            'copy_speed_mbps': round(speed_mbps, 1)
                        })
                    )
                    self.db.add(event)
                    self.db.commit()
                else:
                    job.progress_stage = f"Downloading: {downloaded_bytes / (1024**2):.1f} MB"
                    self.db.commit()

            # Download file
            try:
                await self.ftp.download_file(
                    file.path_remote,
                    local_path,
                    progress_callback=progress
                )
            except FileNotFoundError:
                raise Exception(f"File no longer exists on FTP server: {file.filename}")
            except PermissionError:
                raise Exception(f"Permission denied accessing file on FTP server: {file.filename}")
            except Exception as e:
                # Provide more context for connection errors
                error_msg = str(e).lower()
                if 'connection' in error_msg or 'timeout' in error_msg:
                    raise Exception(f"Lost connection to FTP server while downloading: {file.filename}")
                elif 'disk' in error_msg or 'space' in error_msg:
                    raise Exception(f"Not enough disk space to download: {file.filename}")
                else:
                    raise Exception(f"Download failed for {file.filename}: {str(e)}")
            
            # Verify downloaded file exists and has expected size
            file_exists, verify_error = await loop.run_in_executor(
                None, 
                path_validator.verify_file_exists, 
                str(local_path), 
                file.size - 1024
            )
            if not file_exists:
                raise Exception(f"Downloaded file verification failed: {verify_error}")
            
            logger.info(f"File verified: {local_path} ({local_path.stat().st_size} bytes)")
            
            # Validate container integrity and extract duration
            # ATEM Mini Pro writes the moov atom LAST — downloading before it's
            # written produces a file that looks complete (correct size) but is
            # unplayable. ffprobe returns None for duration when moov is missing.
            # Catching this here prevents 13 futile retry cycles in process_worker.
            try:
                from utils.video_metadata import get_video_duration
                duration = await loop.run_in_executor(None, get_video_duration, str(local_path))
            except Exception as e:
                raise Exception(
                    f"Container validation failed for {file.filename}: "
                    f"could not verify video integrity — {e}"
                )
            
            if not duration:
                raise Exception(
                    f"Container validation failed for {file.filename}: "
                    f"no valid duration/moov atom — ATEM may still be writing the file"
                )
            
            file.duration = duration
            logger.info(f"✅ Container valid: {file.filename} — {duration:.2f}s (bitrate: {file.bitrate_kbps:.0f} kbps)")
            
            # Re-evaluate empty file status based on bitrate
            bitrate_threshold = float(self._get_setting('bitrate_threshold_kbps', '500'))
            if file.bitrate_kbps < bitrate_threshold and file.bitrate_kbps > 0:
                file.is_empty = True
                logger.info(f"File marked as empty: bitrate {file.bitrate_kbps:.0f} kbps < {bitrate_threshold:.0f} kbps threshold")
            elif file.is_empty and file.bitrate_kbps >= bitrate_threshold:
                file.is_empty = False
                logger.info(f"File marked as non-empty: bitrate {file.bitrate_kbps:.0f} kbps >= {bitrate_threshold:.0f} kbps threshold")
            
            # Update records on success
            file.path_local = str(local_path)
            file.state = 'COPIED'
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
                    'state': 'COPIED',
                    'progress_pct': 100,
                    'path_local': str(local_path)
                })
            )
            self.db.add(event)
            self.db.commit()
            
            logger.info(f"Copy complete: {file.filename}")
            
            # Queue for processing
            # - Program output files: Full audio enhancement pipeline
            # - ISO files: Size filtering + organize (skip enhancement)
            # - Empty files: Skip everything (mark completed)
            if file.is_empty:
                # Empty files skip all processing/organizing
                file.state = 'COMPLETED'
                self.db.commit()
                
                # Broadcast completion event
                complete_event = Event(
                    file_id=file.id,
                    event_type='file_state_change',
                    payload_json=json.dumps({
                        'filename': file.filename,
                        'session_id': str(file.session_id),
                        'state': 'COMPLETED',
                        'progress_pct': 100,
                        'message': 'Skipped processing (empty file)'
                    })
                )
                self.db.add(complete_event)
                self.db.commit()
                logger.info(f"Marked as complete (empty file): {file.filename}")
            else:
                # All non-empty files go through PROCESS stage
                # Process worker will handle ISO files differently (size check + skip enhancement)
                # Propagate priority so program files stay ahead of ISOs in the process queue
                process_job, created = job_integrity_service.get_or_create_job(
                    self.db,
                    file_id=file.id,
                    kind='PROCESS',
                    priority=job.priority
                )
                if created:
                    self.db.commit()
                
                file_type = "ISO file" if file.is_iso else "program output"
                logger.info(f"Queued for processing ({file_type}): {file.filename}")
        
        except CancellationRequested:
            # Cancellation already handled by WorkerBase
            logger.info(f"Copy cancelled for {file.filename}")
            await worker_status_service.clear_worker_status('copy')

        except Exception as e:
            # Use WorkerBase retry-with-reset logic
            await self.handle_failure_with_reset(job, e)
            await worker_status_service.update_worker_status(
                'copy',
                state='ERROR',
                error_message=str(e)
            )

        finally:
            # Mark job as no longer cancellable
            job.is_cancellable = False
            self.db.commit()

            # Clear worker status back to idle
            await worker_status_service.clear_worker_status('copy')

            # Disconnect from FTP (only if we created the connection)
            if self.ftp and self._owns_ftp:
                await self.ftp.disconnect()
                self.ftp = None
