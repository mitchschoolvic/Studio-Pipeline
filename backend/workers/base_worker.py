"""
Base Worker Class with Cancellation and Retry-with-Reset Logic

Provides common functionality for all pipeline workers:
- Cancellation detection and handling
- Automatic reset to resumable checkpoints on failure
- Cleanup of partial work artifacts
- Event broadcasting for state changes
- Heartbeat updates for stale job detection
"""
import asyncio
import shutil
import json
from pathlib import Path
from sqlalchemy.orm import Session
from models import Job, File, Event, Setting
from datetime import datetime, timedelta
from services.failure_classifier import FailureClassifier
from services.job_integrity_service import job_integrity_service
from constants import FailureCategory
import logging

logger = logging.getLogger(__name__)


class CancellationRequested(Exception):
    """Exception raised when job cancellation is detected"""
    pass


class WorkerBase:
    """
    Base class for all workers with cancellation and retry support.
    
    Workers should inherit from this class and call check_cancellation()
    periodically during long-running operations.
    """
    
    # Heartbeat interval in seconds
    HEARTBEAT_INTERVAL = 30
    
    def __init__(self, db: Session):
        self.db = db
        self._last_heartbeat = datetime.utcnow()
    
    def update_heartbeat(self, job: Job):
        """
        Update job heartbeat to indicate worker is still alive.
        
        Call this periodically during long operations (e.g., in progress callbacks).
        Uses rate limiting to avoid excessive DB writes.
        """
        now = datetime.utcnow()
        if (now - self._last_heartbeat).total_seconds() >= self.HEARTBEAT_INTERVAL:
            job_integrity_service.update_heartbeat(self.db, job)
            self._last_heartbeat = now
    
    def clear_recovery_tracking(self, file: File):
        """
        Clear recovery tracking fields when a file progresses successfully.
        
        This should be called when a job completes successfully to reset
        the recovery state, allowing clean tracking if a future step fails.
        """
        if file.failure_category or file.recovery_attempts:
            logger.info(f"✅ Clearing recovery tracking for {file.filename} (was: {file.failure_category})")
            file.failure_category = None
            file.failure_job_kind = None
            file.failed_at = None
            file.retry_after = None
            file.recovery_attempts = 0
            self.db.commit()
    
    async def check_cancellation(self, job: Job) -> bool:
        """
        Check if job has been marked for cancellation.
        Also updates heartbeat to indicate worker is alive.
        
        Returns:
            True if job was cancelled and handled, False otherwise
        """
        # Update heartbeat while checking cancellation
        self.update_heartbeat(job)
        
        # Refresh job from database to get latest state
        self.db.expire(job)
        self.db.refresh(job)
        
        if job.cancellation_requested:
            logger.warning(f"🛑 Cancellation requested for job {job.id} ({job.kind})")
            await self._handle_cancellation(job)
            return True
        
        return False
    
    async def handle_failure_with_reset(self, job: Job, error: Exception):
        """
        Handle job failure with automatic retry and checkpoint reset.
        
        Strategy:
        1. Increment retry counter
        2. If retries exhausted → mark FAILED permanently
        3. If retries remain → reset to resumable checkpoint and re-queue
        
        Args:
            job: The failed job
            error: The exception that caused the failure
        """
        file = job.file
        job.retries += 1
        
        logger.warning(
            f"⚠️ Job {job.id} failed (attempt {job.retries}/{job.max_retries}): {error}"
        )
        
        if job.retries >= job.max_retries:
            # Permanent failure - no more retries
            await self._mark_permanent_failure(job, file, error)
        else:
            # Retry with reset to checkpoint
            await self._retry_with_checkpoint_reset(job, file, error)
    
    async def _mark_permanent_failure(self, job: Job, file: File, error: Exception):
        """Mark job and file as permanently failed after max retries with failure classification"""
        # Classify the failure for intelligent recovery
        failure_category, cleaned_message = FailureClassifier.classify(error, job.kind)
        
        job.state = 'FAILED'
        job.error_message = f"Failed after {job.retries} retries: {cleaned_message}"
        file.state = 'FAILED'
        file.error_message = cleaned_message
        
        # Set failure tracking fields for recovery orchestrator
        file.failure_category = failure_category.value
        file.failure_job_kind = job.kind
        file.failed_at = datetime.utcnow()
        
        # Calculate initial retry_after based on category and recovery attempts
        backoff_minutes = FailureClassifier.get_backoff_minutes(failure_category, file.recovery_attempts + 1)
        file.retry_after = datetime.utcnow() + timedelta(minutes=backoff_minutes)
        
        self.db.commit()
        
        # Determine if this failure is recoverable
        is_recoverable = not FailureCategory.is_unrecoverable(failure_category)
        recovery_hint = FailureCategory.get_recovery_hint(failure_category)
        
        # Broadcast failure event with recovery information
        event = Event(
            file_id=file.id,
            event_type='file_state_change',
            payload_json=json.dumps({
                'filename': file.filename,
                'session_id': str(file.session_id),
                'state': 'FAILED',
                'error_message': cleaned_message,
                'retries': job.retries,
                'failure_category': failure_category.value,
                'failure_job_kind': job.kind,
                'is_recoverable': is_recoverable,
                'recovery_hint': recovery_hint,
                'retry_after': file.retry_after.isoformat() if file.retry_after else None
            })
        )
        self.db.add(event)
        self.db.commit()
        
        logger.error(
            f"❌ Permanent failure for {file.filename} after {job.retries} attempts "
            f"(category: {failure_category.value}, recoverable: {is_recoverable})"
        )
    
    async def _retry_with_checkpoint_reset(self, job: Job, file: File, error: Exception):
        """
        Reset file to last resumable checkpoint and create new job to retry.
        
        This ensures we don't retry from a corrupted/partial state.
        """
        checkpoint = file.get_resumable_checkpoint()
        
        logger.info(
            f"🔄 Resetting {file.filename} from {file.state} to {checkpoint} "
            f"(retry {job.retries}/{job.max_retries})"
        )
        
        # Cleanup partial work based on job type
        await self._cleanup_partial_work(job, file)
        
        # Reset file state to checkpoint
        old_state = file.state
        file.state = checkpoint
        
        # Mark current job as failed (with retry indicator)
        job.state = 'FAILED'
        job.error_message = f"Attempt {job.retries}/{job.max_retries} failed: {str(error)}. Reset to {checkpoint}."
        
        self.db.commit()
        
        # Create new job to retry from checkpoint
        next_job_kind = self._next_job_kind(checkpoint)
        new_job = Job(
            file_id=file.id,
            kind=next_job_kind,
            state='QUEUED',
            priority=job.priority,
            retries=job.retries,  # Carry over retry count
            max_retries=job.max_retries
        )
        self.db.add(new_job)
        self.db.commit()
        
        # Broadcast reset event
        event = Event(
            file_id=file.id,
            event_type='file_state_change',
            payload_json=json.dumps({
                'filename': file.filename,
                'session_id': str(file.session_id),
                'state': checkpoint,
                'previous_state': old_state,
                'message': f'Reset to {checkpoint} for retry (attempt {job.retries}/{job.max_retries})',
                'retry_attempt': job.retries,
                'max_retries': job.max_retries
            })
        )
        self.db.add(event)
        self.db.commit()
        
        logger.info(
            f"✅ Created new {next_job_kind} job for {file.filename} "
            f"(retry {job.retries}/{job.max_retries})"
        )
    
    async def _handle_cancellation(self, job: Job):
        """Handle user-requested cancellation by resetting to checkpoint"""
        file = job.file
        checkpoint = job.checkpoint_state or file.get_resumable_checkpoint()
        
        logger.info(
            f"🛑 Cancelling {job.kind} job for {file.filename}, "
            f"resetting from {file.state} to {checkpoint}"
        )
        
        # Cleanup partial work
        await self._cleanup_partial_work(job, file)
        
        # Reset file state
        file.state = checkpoint
        
        # Mark job as failed (cancelled)
        job.state = 'FAILED'
        job.error_message = 'Cancelled by user (pause requested)'
        job.cancellation_requested = False
        job.is_cancellable = False
        
        self.db.commit()
        
        # Create new queued job if not already at final state
        if checkpoint not in ['COMPLETED', 'FAILED']:
            next_job_kind = self._next_job_kind(checkpoint)
            new_job = Job(
                file_id=file.id,
                kind=next_job_kind,
                state='QUEUED',
                priority=job.priority
            )
            self.db.add(new_job)
            self.db.commit()
            
            logger.info(f"Created new {next_job_kind} job after cancellation")
        
        # Broadcast cancellation event
        event = Event(
            file_id=file.id,
            event_type='file_state_change',
            payload_json=json.dumps({
                'filename': file.filename,
                'session_id': str(file.session_id),
                'state': checkpoint,
                'message': f'Cancelled and reset to {checkpoint}'
            })
        )
        self.db.add(event)
        self.db.commit()
    
    async def _cleanup_partial_work(self, job: Job, file: File):
        """
        Cleanup partial work artifacts based on job type.
        
        Ensures clean slate for retry attempts.
        """
        if job.kind == 'COPY':
            await self._cleanup_partial_copy(file)
        elif job.kind == 'PROCESS':
            await self._cleanup_partial_process(file)
        elif job.kind == 'ORGANIZE':
            await self._cleanup_partial_organize(file)
    
    async def _cleanup_partial_copy(self, file: File):
        """
        Delete partial .part files and entire file_id temp directory.
        
        New structure: /temp_processing/{file_id}/
        This directory contains the file and any subdirectories (Video ISO Files, etc.)
        """
        if file.path_local:
            # Delete .part file if exists
            part_file = Path(file.path_local + '.part')
            if part_file.exists():
                try:
                    part_file.unlink()
                    logger.info(f"🗑️ Deleted partial download: {part_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete {part_file}: {e}")
            
            # Delete metadata file if exists
            meta_file = Path(file.path_local + '.part.meta')
            if meta_file.exists():
                try:
                    meta_file.unlink()
                    logger.debug(f"Deleted metadata file: {meta_file}")
                except Exception as e:
                    logger.warning(f"Failed to delete {meta_file}: {e}")
            
            # NEW: Delete entire file_id directory for clean slate
            # path_local format: /temp_processing/{file_id}/{relative_path}
            # We want to delete: /temp_processing/{file_id}/
            file_id_dir = Path(file.path_local).parent
            
            # Go up one more level if file is in subfolder (ISO files)
            if file.is_in_subfolder:
                file_id_dir = file_id_dir.parent
            
            # Safety check: directory name should be a UUID (our file_id)
            if file_id_dir.exists() and file_id_dir.name == file.id:
                try:
                    shutil.rmtree(file_id_dir, ignore_errors=True)
                    logger.info(f"🗑️ Deleted file_id temp directory: {file_id_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete {file_id_dir}: {e}")
        
        # Clear local path since we're restarting
        file.path_local = None
        self.db.commit()
    
    async def _cleanup_partial_process(self, file: File):
        """Delete temp processing directory but keep downloaded file"""
        if file.path_processed:
            temp_dir = Path(file.path_processed).parent
            
            # Safety check: only delete if it's in our temp directory
            if temp_dir.exists() and '/tmp/pipeline/' in str(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.info(f"🗑️ Deleted temp processing dir: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to delete {temp_dir}: {e}")
        
        # Clear processed path, but KEEP path_local (the downloaded file)
        file.path_processed = None
        self.db.commit()
    
    async def _cleanup_partial_organize(self, file: File):
        """
        No cleanup needed for organize - just retry the atomic move.
        
        The organize operation is atomic (shutil.move), so either it
        completed or it didn't. No partial state possible.
        """
        pass
    
    def _next_job_kind(self, checkpoint_state: str) -> str:
        """
        Determine next job kind based on checkpoint state.
        
        State machine:
        DISCOVERED → COPY
        COPIED → PROCESS
        PROCESSED → ORGANIZE
        """
        if checkpoint_state == 'DISCOVERED':
            return 'COPY'
        elif checkpoint_state == 'COPIED':
            return 'PROCESS'
        elif checkpoint_state == 'PROCESSED':
            return 'ORGANIZE'
        else:
            # Fallback
            return 'COPY'
    
    def _get_setting(self, key: str, default: str = None) -> str:
        """Helper to get setting value from database"""
        setting = self.db.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else default
