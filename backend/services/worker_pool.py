import asyncio
import time
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from database import SessionLocal
from workers.copy_worker import CopyWorker
from workers.process_worker import ProcessWorker
from workers.organize_worker import OrganizeWorker
from workers.thumbnail_worker import ThumbnailWorker
from workers.ftp_client import FTPClient
from services.path_validator import path_validator
from services.worker_status_service import worker_status_service
from services.recovery_orchestrator import RecoveryOrchestrator
from services.job_integrity_service import job_integrity_service
from models import Setting
from config.ai_config import AI_ENABLED
import logging

logger = logging.getLogger(__name__)

# Conditionally import AI workers
if AI_ENABLED:
    from workers.transcribe_worker import TranscribeWorker
    from workers.analyze_worker import AnalyzeWorker


# Import the helper function to get swift tools path
def get_swift_tools_path():
    """Get the path to the Swift tools directory (handles both dev and PyInstaller)"""
    import sys
    from pathlib import Path
    
    # Check if running from PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        base_path = Path(sys._MEIPASS)
        swift_tools_path = base_path / 'swift_tools'
    else:
        # Running in development
        base_path = Path(__file__).parent.parent.parent
        swift_tools_path = base_path / 'swift_tools'
    
    return swift_tools_path


class WorkerPool:
    """Manages worker tasks that process jobs from the queue"""
    
    def __init__(self):
        self.copy_semaphore = asyncio.Semaphore(1)      # Max 1 concurrent copy
        self.process_semaphore = asyncio.Semaphore(1)   # Max 1 concurrent process
        self.organize_semaphore = asyncio.Semaphore(1)  # Max 1 concurrent organize

        self.copy_task = None
        self.process_task = None
        self.organize_task = None
        self.thumbnail_task = None

        # AI analytics tasks (if enabled)
        self.transcribe_task = None
        self.analyze_task = None
        
        # Recovery orchestrator task
        self.recovery_task = None
        self.recovery_orchestrator = RecoveryOrchestrator(poll_interval=10.0)

        # Initialize thumbnail worker
        thumbnail_dir = str(Path.home() / "Library/Application Support/StudioPipeline/thumbnails")
        self.thumbnail_worker = ThumbnailWorker(
            thumbnail_dir=thumbnail_dir,
            batch_size=5,  # Process 5 at a time
            delay=3.0,     # Wait 3 seconds between batches
            max_cpu_percent=80.0  # Pause if CPU > 80%
        )
        logger.info(f"Thumbnail directory: {thumbnail_dir}")

        self.running = False
    
    def _get_settings(self, db: Session) -> dict:
        """Load settings from database"""
        settings = db.query(Setting).all()
        settings_dict = {s.key: s.value for s in settings}
        
        # Provide defaults for required settings
        return {
            'ftp_host': settings_dict.get('ftp_host', 'localhost'),
            'ftp_port': settings_dict.get('ftp_port', '21'),
            'ftp_username': settings_dict.get('ftp_username', 'anonymous'),
            'ftp_password': settings_dict.get('ftp_password', ''),
            'source_path': settings_dict.get('ftp_source_path', '/'),
            'temp_path': settings_dict.get('temp_path', '/tmp/pipeline'),
            'output_path': settings_dict.get('output_path', str(Path.home() / 'Videos' / 'StudioPipeline')),
        }
    
    async def _copy_worker_loop(self):
        """Continuously process COPY jobs with shared FTP connection.
        
        Maintains a single FTP connection across iterations to avoid
        per-file connection overhead. The connection is health-checked
        before each job and dropped after 60s idle.
        """
        logger.info("Copy worker loop started")
        shared_ftp: Optional[FTPClient] = None
        last_job_time = time.monotonic()
        FTP_IDLE_TIMEOUT = 60  # seconds
        
        while self.running:
            db = SessionLocal()
            try:
                config = self._get_settings(db)
                
                # Validate paths before processing
                temp_path = config.get('temp_path', '/tmp/pipeline')
                output_path = config.get('output_path', str(Path.home() / 'Videos' / 'StudioPipeline'))
                
                paths_valid, errors = path_validator.validate_workspace_paths(temp_path, output_path)
                if not paths_valid:
                    error_msg = '; '.join(errors)
                    logger.error(f"Workspace paths invalid, copy worker paused: {error_msg}")
                    await worker_status_service.update_worker_status('copy', state='ERROR', error_message=error_msg)
                    await asyncio.sleep(10)  # Wait longer before retrying
                    continue
                
                # Drop idle FTP connection to free server resources
                if shared_ftp is not None and (time.monotonic() - last_job_time) > FTP_IDLE_TIMEOUT:
                    logger.info("Shared FTP idle timeout, disconnecting")
                    try:
                        await shared_ftp.disconnect()
                    except Exception:
                        pass
                    shared_ftp = None
                
                # Lazily create shared FTP connection
                if shared_ftp is None:
                    shared_ftp = FTPClient(
                        host=config.get('ftp_host', config.get('host', 'localhost')),
                        port=int(config.get('ftp_port', config.get('port', 21))),
                        username=config.get('ftp_username', config.get('username', 'anonymous')),
                        password=config.get('ftp_password', config.get('password', ''))
                    )
                
                worker = CopyWorker(db, config, self.copy_semaphore, shared_ftp=shared_ftp)
                
                # Run one iteration (checks for job, processes if found, or sleeps)
                await worker.run_once()
                last_job_time = time.monotonic()
                
            except Exception as e:
                logger.error(f"Copy worker loop error: {e}", exc_info=True)
                await worker_status_service.update_worker_status('copy', state='ERROR', error_message=str(e))
                # Drop shared FTP on unexpected errors to avoid corrupted state
                if shared_ftp is not None:
                    try:
                        await shared_ftp.disconnect()
                    except Exception:
                        pass
                    shared_ftp = None
                await asyncio.sleep(5)  # Back off on error
            finally:
                db.close()
                await asyncio.sleep(0.5)  # Small delay between iterations
        
        # Cleanup shared FTP on shutdown
        if shared_ftp is not None:
            try:
                await shared_ftp.disconnect()
            except Exception:
                pass
        logger.info("Copy worker loop stopped")
    
    async def _process_worker_loop(self):
        """Continuously process PROCESS jobs"""
        logger.info("Process worker loop started")
        
        while self.running:
            db = SessionLocal()
            try:
                config = self._get_settings(db)
                
                # Validate paths before processing
                temp_path = config.get('temp_path', '/tmp/pipeline')
                output_path = config.get('output_path', str(Path.home() / 'Videos' / 'StudioPipeline'))
                
                paths_valid, errors = path_validator.validate_workspace_paths(temp_path, output_path)
                if not paths_valid:
                    error_msg = '; '.join(errors)
                    logger.error(f"Workspace paths invalid, process worker paused: {error_msg}")
                    await worker_status_service.update_worker_status('process', state='ERROR', error_message=error_msg)
                    await asyncio.sleep(10)  # Wait longer before retrying
                    continue
                
                # Get swift tools directory (handles both dev and PyInstaller bundle)
                swift_tools_dir = get_swift_tools_path()
                
                worker = ProcessWorker(db, swift_tools_dir, self.process_semaphore)
                
                # Run one iteration
                await worker.run_once()
                
            except Exception as e:
                logger.error(f"Process worker loop error: {e}", exc_info=True)
                await worker_status_service.update_worker_status('process', state='ERROR', error_message=str(e))
                await asyncio.sleep(5)
            finally:
                db.close()
                await asyncio.sleep(0.5)
        
        logger.info("Process worker loop stopped")
    
    async def _organize_worker_loop(self):
        """Continuously process ORGANIZE jobs"""
        logger.info("Organize worker loop started")
        
        while self.running:
            db = SessionLocal()
            try:
                config = self._get_settings(db)
                
                # Validate output path before processing
                output_path = config.get('output_path', str(Path.home() / 'Videos' / 'StudioPipeline'))
                path_valid, path_error, _ = path_validator.ensure_directory(output_path)
                if not path_valid:
                    logger.error(f"Output path invalid, organize worker paused: {path_error}")
                    await worker_status_service.update_worker_status('organize', state='ERROR', error_message=path_error)
                    await asyncio.sleep(10)  # Wait longer before retrying
                    continue
                
                worker = OrganizeWorker(db, self.organize_semaphore)
                
                # Run one iteration
                await worker.run_once()
                
            except Exception as e:
                logger.error(f"Organize worker loop error: {e}", exc_info=True)
                await worker_status_service.update_worker_status('organize', state='ERROR', error_message=str(e))
                await asyncio.sleep(5)
            finally:
                db.close()
                await asyncio.sleep(0.5)
        
        logger.info("Organize worker loop stopped")

    async def _transcribe_worker_loop(self):
        """Continuously process TRANSCRIBE jobs"""
        logger.info("Transcribe worker loop started")

        while self.running:
            db = SessionLocal()
            try:
                worker = TranscribeWorker(db)
                await worker.run_once()
            except Exception as e:
                logger.error(f"Transcribe worker loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
            finally:
                db.close()
                await asyncio.sleep(0.5)

        logger.info("Transcribe worker loop stopped")

    async def _analyze_worker_loop(self):
        """Continuously process ANALYZE jobs"""
        logger.info("Analyze worker loop started")

        while self.running:
            db = SessionLocal()
            try:
                worker = AnalyzeWorker(db)
                await worker.run_once()
            except Exception as e:
                logger.error(f"Analyze worker loop error: {e}", exc_info=True)
                await asyncio.sleep(5)
            finally:
                db.close()
                await asyncio.sleep(0.5)

        logger.info("Analyze worker loop stopped")

    async def start(self):
        """Start all worker tasks"""
        if self.running:
            logger.warning("WorkerPool already running")
            return
        
        self.running = True
        logger.info("Starting WorkerPool...")
        
        # Run startup recovery for zombie jobs from previous crashed session
        db = SessionLocal()
        try:
            recovered = job_integrity_service.startup_recovery(db)
            if recovered > 0:
                logger.info(f"🔧 Startup recovery: {recovered} zombie jobs recovered")
        except Exception as e:
            logger.error(f"Startup recovery failed: {e}")
        finally:
            db.close()
        
        # Start job watchdog for detecting stale jobs
        await job_integrity_service.start_watchdog()

        # Create tasks for each worker
        self.copy_task = asyncio.create_task(self._copy_worker_loop())
        self.process_task = asyncio.create_task(self._process_worker_loop())
        self.organize_task = asyncio.create_task(self._organize_worker_loop())

        # Start thumbnail worker
        self.thumbnail_task = asyncio.create_task(self.thumbnail_worker.start())

        # Start AI analytics workers if enabled
        if AI_ENABLED:
            self.transcribe_task = asyncio.create_task(self._transcribe_worker_loop())
            self.analyze_task = asyncio.create_task(self._analyze_worker_loop())
            logger.info("✅ AI analytics workers initialized")
        
        # Start recovery orchestrator (monitors failed files and retries when appropriate)
        self.recovery_task = asyncio.create_task(self.recovery_orchestrator.start())
        logger.info("✅ Recovery orchestrator initialized")

        logger.info("WorkerPool started - all workers running")
    
    async def stop(self):
        """Stop all worker tasks gracefully"""
        if not self.running:
            return
        
        logger.info("Stopping WorkerPool...")
        
        # Prepare running jobs for graceful shutdown
        db = SessionLocal()
        try:
            preserved = job_integrity_service.prepare_for_shutdown(db)
            if preserved > 0:
                logger.info(f"🛑 Graceful shutdown: {preserved} running jobs preserved for restart")
        except Exception as e:
            logger.error(f"Graceful shutdown preparation failed: {e}")
        finally:
            db.close()
        
        # Stop job watchdog
        await job_integrity_service.stop_watchdog()
        self.running = False
        
        # Stop thumbnail worker first
        await self.thumbnail_worker.stop()
        
        # Stop recovery orchestrator
        await self.recovery_orchestrator.stop()

        # Cancel all tasks
        tasks = [self.copy_task, self.process_task, self.organize_task, self.thumbnail_task, self.recovery_task]

        # Add AI worker tasks if enabled
        if AI_ENABLED:
            tasks.extend([self.transcribe_task, self.analyze_task])

        for task in tasks:
            if task and not task.done():
                task.cancel()
        
        # Wait for all tasks to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, asyncio.CancelledError):
                logger.info(f"Worker task {i} cancelled successfully")
            elif isinstance(result, Exception):
                logger.error(f"Worker task {i} failed: {result}")
        
        logger.info("WorkerPool stopped")


# Global singleton
worker_pool = WorkerPool()
