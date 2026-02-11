"""
Recovery Orchestrator Service

Manages automatic recovery of failed files with intelligent retry logic.
Monitors for failed files and intelligently retries them based on their
failure category and system state.

Key behaviors:
1. Waits until all non-failed files in queue are processed (priority queue)
2. For FTP failures: Waits until FTP is connected before retrying
3. For processing failures: Applies exponential backoff
4. For storage failures: Validates paths before retrying
5. Broadcasts recovery status updates to frontend
"""
import asyncio
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from database import get_db
from models import File, Job, Event, Setting
from constants import FailureCategory, JobPriority
from services.failure_classifier import FailureClassifier
from services.path_validator import path_validator
from services.job_integrity_service import job_integrity_service
import logging

logger = logging.getLogger(__name__)


class RecoveryOrchestrator:
    """
    Manages automatic recovery of failed files.
    
    This service runs as a background task and periodically checks for
    failed files that can be recovered. Recovery is deferred until all
    non-failed work is complete, ensuring failed files don't block the queue.
    """
    
    def __init__(self, poll_interval: float = 10.0, max_recovery_attempts: int = 10):
        """
        Initialize the recovery orchestrator.
        
        Args:
            poll_interval: How often to check for recoverable files (seconds)
            max_recovery_attempts: Maximum times to attempt recovery before giving up
        """
        self.poll_interval = poll_interval
        self.max_recovery_attempts = max_recovery_attempts
        self.running = False
        self._last_status_broadcast = None
    
    async def start(self):
        """Start the recovery orchestrator service"""
        self.running = True
        logger.info(f"🔄 Recovery Orchestrator started (polling every {self.poll_interval}s)")
        
        while self.running:
            try:
                await self._process_recovery_queue()
                await self._broadcast_recovery_status()
            except Exception as e:
                logger.error(f"Recovery orchestrator error: {e}", exc_info=True)
            
            await asyncio.sleep(self.poll_interval)
    
    async def stop(self):
        """Stop the recovery orchestrator service"""
        self.running = False
        logger.info("Recovery Orchestrator stopped")
    
    async def _process_recovery_queue(self):
        """Check for recoverable failed files and queue recovery jobs.
        
        Uses two-level gating:
        1. Session-awareness: defers ALL recovery when live work (new files) is active.
           Recovery only runs when the system has no pending/active non-recovery work.
        2. Stage-aware gating: if recovery does run, FTP failures only wait for copy
           worker to be free, not for the entire pipeline to drain.
        """
        db = next(get_db())
        
        try:
            # ── Session-awareness gate ──────────────────────────────────
            # If ANY non-recovery work is queued or running, defer completely.
            # Recovery priority is -5; anything >= 0 is live/new work.
            active_live_jobs = db.query(Job).filter(
                Job.state.in_(['QUEUED', 'RUNNING']),
                Job.priority > JobPriority.RECOVERY
            ).count()
            
            if active_live_jobs > 0:
                logger.debug(
                    f"Recovery deferred: {active_live_jobs} active live job(s) — "
                    f"waiting for new files to finish before recovering old failures"
                )
                return
            
            # ── Stage-aware gating ──────────────────────────────────────
            # Build a set of active job kinds for per-worker gating
            active_job_kinds = set(
                row[0] for row in db.query(Job.kind).filter(
                    Job.state.in_(['QUEUED', 'RUNNING'])
                ).distinct().all()
            )
            
            if active_job_kinds:
                logger.debug(f"Active job kinds: {active_job_kinds}")
            
            # Step 2: Retry failed files with stage-aware gating
            await self._retry_failed_files(db, active_job_kinds)
            
        except Exception as e:
            logger.error(f"Error in recovery queue processing: {e}", exc_info=True)
        finally:
            db.close()
    
    async def _retry_failed_files(self, db: Session, active_job_kinds: set = None):
        """
        Retry failed files based on their failure category.
        
        Uses stage-aware gating: a file's recovery is only deferred if there
        are active jobs of the SAME kind as the recovery job would create.
        For example, FTP failures only wait for active COPY jobs to finish,
        not for PROCESS or ORGANIZE jobs.
        
        Priority order:
        1. FTP failures (if FTP is connected AND copy worker is free)
        2. Processing failures (with backoff check AND process worker is free)
        3. Storage failures (if paths are valid AND organize worker is free)
        """
        if active_job_kinds is None:
            active_job_kinds = set()
        # Get FTP connection status from reconciler
        ftp_connected = await self._check_ftp_connected(db)
        
        # Get current time for backoff comparison
        now = datetime.utcnow()
        
        # Get all recoverable failed files
        failed_files = db.query(File).filter(
            File.state == 'FAILED',
            File.is_missing == False,  # Can't recover missing files
            or_(
                File.recovery_attempts < self.max_recovery_attempts,
                File.recovery_attempts == None
            )
        ).order_by(
            File.failed_at.asc()  # Oldest failures first
        ).all()
        
        if not failed_files:
            return
        
        logger.info(f"🔍 Checking {len(failed_files)} failed files for recovery")
        
        files_queued = 0
        files_skipped_ftp = 0
        files_skipped_backoff = 0
        files_skipped_unrecoverable = 0
        files_skipped_worker_busy = 0
        
        for file in failed_files:
            # Parse failure category
            category = self._get_failure_category(file)
            
            # Skip unrecoverable failures
            if FailureCategory.is_unrecoverable(category):
                files_skipped_unrecoverable += 1
                continue
            
            # Check retry_after backoff
            if file.retry_after and file.retry_after > now:
                files_skipped_backoff += 1
                continue
            
            # Stage-aware gating: only defer recovery if the required worker
            # type is busy. This allows FTP retries to proceed while processing
            # or organizing runs for other files.
            required_kind = FailureCategory.required_job_kind(category)
            if required_kind in active_job_kinds:
                files_skipped_worker_busy += 1
                continue
            
            # Category-specific retry logic
            if FailureCategory.requires_ftp(category):
                if not ftp_connected:
                    files_skipped_ftp += 1
                    continue
                # FTP is connected, queue COPY job
                await self._queue_recovery_job(db, file, 'COPY')
                files_queued += 1
            
            elif FailureCategory.requires_path_validation(category):
                # Validate output path before retrying
                output_path = self._get_setting(db, 'output_path')
                if output_path:
                    path_valid, _, _ = path_validator.ensure_directory(output_path)
                    if path_valid:
                        checkpoint = file.get_resumable_checkpoint()
                        job_kind = self._job_kind_for_checkpoint(checkpoint)
                        await self._queue_recovery_job(db, file, job_kind)
                        files_queued += 1
                    else:
                        logger.debug(f"Skipping {file.filename}: output path not accessible")
            
            else:
                # Processing errors or unknown - retry from checkpoint
                checkpoint = file.get_resumable_checkpoint()
                job_kind = self._job_kind_for_checkpoint(checkpoint)
                await self._queue_recovery_job(db, file, job_kind)
                files_queued += 1
        
        if files_queued > 0:
            logger.info(
                f"✅ Recovery: Queued {files_queued} files, "
                f"skipped {files_skipped_ftp} (awaiting FTP), "
                f"{files_skipped_backoff} (backoff), "
                f"{files_skipped_worker_busy} (worker busy), "
                f"{files_skipped_unrecoverable} (unrecoverable)"
            )
    
    async def _queue_recovery_job(self, db: Session, file: File, job_kind: str):
        """Create a recovery job for a failed file using job integrity service"""
        
        # Increment recovery attempts
        file.recovery_attempts = (file.recovery_attempts or 0) + 1
        
        # Calculate new backoff for next potential failure
        category = self._get_failure_category(file)
        backoff_minutes = FailureClassifier.get_backoff_minutes(category, file.recovery_attempts)
        file.retry_after = datetime.utcnow() + timedelta(minutes=backoff_minutes)
        
        # Reset file state to checkpoint
        checkpoint = file.get_resumable_checkpoint()
        old_state = file.state
        file.state = checkpoint
        
        # Clear error message for retry (keep failure_category for tracking)
        old_error = file.error_message
        file.error_message = None
        
        db.commit()
        
        # Use job integrity service for deduplication
        new_job, created = job_integrity_service.get_or_create_job(
            db,
            file_id=file.id,
            kind=job_kind,
            priority=JobPriority.RECOVERY  # Below new files so recovery never blocks fresh work
        )
        
        if not created:
            logger.debug(f"Recovery job already exists for {file.filename}")
            return
        
        # Commit the new job
        db.commit()
        
        # Clean up old failed jobs to prevent pollution
        job_integrity_service.cleanup_failed_job_history(db, file.id, keep_count=3)
        
        # Create recovery event
        event = Event(
            file_id=file.id,
            event_type='file_state_change',
            payload_json=json.dumps({
                'filename': file.filename,
                'state': checkpoint,
                'previous_state': old_state,
                'message': f'Recovery attempt {file.recovery_attempts}: queued {job_kind} job',
                'recovery_attempt': file.recovery_attempts,
                'failure_category': file.failure_category,
                'job_kind': job_kind
            })
        )
        db.add(event)
        db.commit()
        
        logger.info(
            f"🔄 Queued recovery {job_kind} for {file.filename} "
            f"(attempt {file.recovery_attempts}, category: {file.failure_category})"
        )
    
    async def _broadcast_recovery_status(self):
        """Broadcast recovery status to frontend via WebSocket"""
        # Rate limit broadcasts to every 5 seconds
        now = datetime.utcnow()
        if self._last_status_broadcast and (now - self._last_status_broadcast).total_seconds() < 5:
            return
        
        db = next(get_db())
        try:
            # Get failed files summary
            failed_files = db.query(File).filter(File.state == 'FAILED').all()
            
            if not failed_files:
                return
            
            # Categorize files
            awaiting_ftp = 0
            awaiting_backoff = 0
            unrecoverable = 0
            ready_to_retry = 0
            
            now = datetime.utcnow()
            for file in failed_files:
                category = self._get_failure_category(file)
                
                if FailureCategory.is_unrecoverable(category):
                    unrecoverable += 1
                elif FailureCategory.requires_ftp(category):
                    awaiting_ftp += 1
                elif file.retry_after and file.retry_after > now:
                    awaiting_backoff += 1
                else:
                    ready_to_retry += 1
            
            # Check active jobs
            active_jobs = db.query(Job).filter(
                Job.state.in_(['QUEUED', 'RUNNING'])
            ).count()
            
            # Get FTP status
            ftp_connected = await self._check_ftp_connected(db)
            
            # Import websocket manager
            from services.websocket import manager
            
            await manager.broadcast({
                'type': 'recovery_status',
                'data': {
                    'total_failed': len(failed_files),
                    'awaiting_ftp': awaiting_ftp,
                    'awaiting_backoff': awaiting_backoff,
                    'unrecoverable': unrecoverable,
                    'ready_to_retry': ready_to_retry,
                    'active_jobs': active_jobs,
                    'ftp_connected': ftp_connected,
                    'recovery_blocked': False,  # Stage-aware gating; no global block
                    'recovery_blocked_reason': (
                        'Waiting for FTP' if awaiting_ftp > 0 and not ftp_connected else None
                    )
                }
            })
            
            self._last_status_broadcast = now
            
        except Exception as e:
            logger.debug(f"Failed to broadcast recovery status: {e}")
        finally:
            db.close()
    
    async def _check_ftp_connected(self, db: Session) -> bool:
        """Check if FTP is currently connected"""
        try:
            # Import reconciler to get FTP status
            from services.reconciler import reconciler
            return reconciler.last_ftp_connected or False
        except Exception:
            return False
    
    def _get_failure_category(self, file: File) -> FailureCategory:
        """Parse failure category from file, defaulting to UNKNOWN"""
        if file.failure_category:
            try:
                return FailureCategory(file.failure_category)
            except ValueError:
                pass
        return FailureCategory.UNKNOWN
    
    def _job_kind_for_checkpoint(self, checkpoint_state: str) -> str:
        """Determine job kind based on checkpoint state"""
        if checkpoint_state == 'DISCOVERED':
            return 'COPY'
        elif checkpoint_state == 'COPIED':
            return 'PROCESS'
        elif checkpoint_state == 'PROCESSED':
            return 'ORGANIZE'
        else:
            return 'COPY'  # Fallback
    
    def _get_setting(self, db: Session, key: str) -> str:
        """Get setting value from database"""
        setting = db.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else None
    
    def get_status(self) -> dict:
        """Get current recovery orchestrator status"""
        return {
            'running': self.running,
            'poll_interval': self.poll_interval,
            'max_recovery_attempts': self.max_recovery_attempts
        }


# Global instance
recovery_orchestrator = RecoveryOrchestrator(poll_interval=10.0)


async def start_recovery_orchestrator():
    """Start the recovery orchestrator (call from FastAPI startup)"""
    asyncio.create_task(recovery_orchestrator.start())
    logger.info("Recovery orchestrator service started")


async def stop_recovery_orchestrator():
    """Stop the recovery orchestrator (call from FastAPI shutdown)"""
    await recovery_orchestrator.stop()
    logger.info("Recovery orchestrator service stopped")
