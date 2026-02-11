"""
Job Integrity Service - Ensures robust job queue management

Provides:
1. Startup Recovery: Reclaim zombie RUNNING jobs from crashed sessions
2. Job Deduplication: Prevent multiple active jobs per file+kind
3. Watchdog: Detect and reclaim stale jobs based on heartbeat
4. Graceful Shutdown: Mark jobs for recovery before shutdown
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from models import Job, File, Event
from database import SessionLocal
import logging
import json

logger = logging.getLogger(__name__)


# Stale job threshold - jobs without heartbeat for this long are considered dead
STALE_JOB_THRESHOLD_MINUTES = 5

# Watchdog poll interval
WATCHDOG_POLL_SECONDS = 60


class JobIntegrityService:
    """Service for maintaining job queue integrity"""
    
    def __init__(self):
        self.worker_id = str(uuid.uuid4())[:8]  # Unique ID for this worker pool instance
        self._running = False
        self._watchdog_task: Optional[asyncio.Task] = None
    
    def startup_recovery(self, db: Session) -> int:
        """
        Recover zombie RUNNING jobs from previous crashed session.
        
        Called once at startup before workers begin processing.
        
        Returns the number of jobs recovered.
        """
        recovered_count = 0
        
        try:
            # Find all RUNNING jobs (these are from a crashed previous session)
            running_jobs = db.query(Job).filter(
                Job.state == 'RUNNING'
            ).all()
            
            if not running_jobs:
                logger.info("✅ No zombie RUNNING jobs found - queue is clean")
                return 0
            
            logger.warning(f"🔧 Found {len(running_jobs)} zombie RUNNING jobs from previous session")
            
            for job in running_jobs:
                file = job.file
                
                # Determine the appropriate checkpoint state
                checkpoint = file.get_resumable_checkpoint() if file else 'DISCOVERED'
                
                # Reset job to QUEUED for retry
                job.state = 'QUEUED'
                job.started_at = None
                job.last_heartbeat = None
                job.worker_id = None
                job.is_cancellable = False
                job.retries = min(job.retries + 1, job.max_retries)  # Count as a retry
                job.error_message = f"Recovered from crashed session at {datetime.utcnow().isoformat()}"
                
                # Reset file to checkpoint state
                if file:
                    old_state = file.state
                    file.state = checkpoint
                    logger.info(
                        f"  🔄 Recovered {job.kind} job for {file.filename}: "
                        f"file {old_state} → {checkpoint}, job RUNNING → QUEUED"
                    )
                
                recovered_count += 1
            
            db.commit()
            logger.info(f"✅ Recovered {recovered_count} zombie jobs - ready for retry")
            
        except Exception as e:
            logger.error(f"Error during startup job recovery: {e}", exc_info=True)
            db.rollback()
        
        return recovered_count
    
    def get_or_create_job(
        self,
        db: Session,
        file_id: str,
        kind: str,
        priority: int = 0
    ) -> Tuple[Job, bool]:
        """
        Get existing active job or create new one (deduplication).
        
        Prevents creation of duplicate jobs for the same file+kind.
        
        Args:
            db: Database session
            file_id: The file ID
            kind: Job kind (COPY, PROCESS, ORGANIZE, etc.)
            priority: Job priority (only used if creating new)
            
        Returns:
            Tuple of (job, created) where created is True if new job was created
        """
        # Check for existing QUEUED or RUNNING job for this file+kind
        existing = db.query(Job).filter(
            Job.file_id == file_id,
            Job.kind == kind,
            Job.state.in_(['QUEUED', 'RUNNING'])
        ).first()
        
        if existing:
            logger.debug(f"Found existing {kind} job for file {file_id} in state {existing.state}")
            return existing, False
        
        # Create new job
        new_job = Job(
            file_id=file_id,
            kind=kind,
            state='QUEUED',
            priority=priority
        )
        db.add(new_job)
        logger.debug(f"Created new {kind} job for file {file_id}")
        
        return new_job, True
    
    def claim_job(self, db: Session, job: Job) -> bool:
        """
        Claim a job for processing with atomic check.
        
        Uses optimistic locking to prevent race conditions.
        
        Returns True if job was successfully claimed, False if already taken.
        """
        # Refresh job state
        db.refresh(job)
        
        # Check if still QUEUED
        if job.state != 'QUEUED':
            logger.debug(f"Job {job.id} already claimed (state={job.state})")
            return False
        
        # Claim the job
        job.state = 'RUNNING'
        job.started_at = datetime.utcnow()
        job.last_heartbeat = datetime.utcnow()
        job.worker_id = self.worker_id
        job.is_cancellable = True
        
        try:
            db.commit()
            logger.debug(f"Claimed job {job.id} ({job.kind}) for worker {self.worker_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.warning(f"Failed to claim job {job.id}: {e}")
            return False
    
    def update_heartbeat(self, db: Session, job: Job):
        """
        Update job heartbeat to indicate worker is still alive.
        
        Should be called periodically during long operations.
        """
        job.last_heartbeat = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            db.rollback()
    
    async def start_watchdog(self):
        """Start the background watchdog task to detect stale jobs"""
        if self._running:
            return
        
        self._running = True
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        logger.info(f"🐕 Job watchdog started (worker_id={self.worker_id})")
    
    async def stop_watchdog(self):
        """Stop the watchdog task"""
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        logger.info("🐕 Job watchdog stopped")
    
    async def _watchdog_loop(self):
        """Background loop to detect and recover stale jobs"""
        while self._running:
            try:
                await asyncio.sleep(WATCHDOG_POLL_SECONDS)
                
                if not self._running:
                    break
                
                db = SessionLocal()
                try:
                    stale_count = self._reclaim_stale_jobs(db)
                    if stale_count > 0:
                        logger.info(f"🐕 Watchdog reclaimed {stale_count} stale jobs")
                finally:
                    db.close()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog error: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    def _reclaim_stale_jobs(self, db: Session) -> int:
        """
        Find and reclaim jobs that have gone stale (no heartbeat).
        
        Returns the number of jobs reclaimed.
        """
        threshold = datetime.utcnow() - timedelta(minutes=STALE_JOB_THRESHOLD_MINUTES)
        
        # Find RUNNING jobs with stale heartbeat
        stale_jobs = db.query(Job).filter(
            Job.state == 'RUNNING',
            or_(
                Job.last_heartbeat < threshold,
                Job.last_heartbeat.is_(None)  # Old jobs without heartbeat field
            )
        ).all()
        
        if not stale_jobs:
            return 0
        
        reclaimed = 0
        for job in stale_jobs:
            file = job.file
            
            # Log stale job detection
            last_hb = job.last_heartbeat.isoformat() if job.last_heartbeat else "never"
            logger.warning(
                f"🐕 Detected stale {job.kind} job {job.id[:8]} "
                f"(last heartbeat: {last_hb}, worker: {job.worker_id})"
            )
            
            # Get checkpoint for file
            checkpoint = file.get_resumable_checkpoint() if file else 'DISCOVERED'
            
            # Reset job for retry
            job.state = 'QUEUED'
            job.started_at = None
            job.last_heartbeat = None
            job.worker_id = None
            job.is_cancellable = False
            job.retries = min(job.retries + 1, job.max_retries)
            job.error_message = f"Reclaimed by watchdog (stale) at {datetime.utcnow().isoformat()}"
            
            # Reset file state
            if file:
                old_state = file.state
                file.state = checkpoint
                logger.info(f"  Reset {file.filename}: {old_state} → {checkpoint}")
                
                # Broadcast state change
                event = Event(
                    file_id=file.id,
                    event_type='file_state_change',
                    payload_json=json.dumps({
                        'filename': file.filename,
                        'state': checkpoint,
                        'message': 'Recovered stale job'
                    })
                )
                db.add(event)
            
            reclaimed += 1
        
        if reclaimed > 0:
            db.commit()
        
        return reclaimed
    
    def prepare_for_shutdown(self, db: Session) -> int:
        """
        Prepare jobs for graceful shutdown.
        
        Marks all RUNNING jobs from this worker as needing recovery.
        
        Returns the number of jobs prepared.
        """
        # Find our RUNNING jobs
        our_jobs = db.query(Job).filter(
            Job.state == 'RUNNING',
            Job.worker_id == self.worker_id
        ).all()
        
        if not our_jobs:
            return 0
        
        logger.info(f"🛑 Preparing {len(our_jobs)} running jobs for shutdown...")
        
        for job in our_jobs:
            file = job.file
            checkpoint = file.get_resumable_checkpoint() if file else 'DISCOVERED'
            
            # Reset job to QUEUED for next startup
            job.state = 'QUEUED'
            job.started_at = None
            job.last_heartbeat = None
            job.worker_id = None
            job.is_cancellable = False
            job.error_message = f"Graceful shutdown at {datetime.utcnow().isoformat()}"
            
            # Reset file to checkpoint
            if file:
                old_state = file.state
                file.state = checkpoint
                logger.info(f"  Saved {job.kind} job for {file.filename}: {old_state} → {checkpoint}")
        
        db.commit()
        return len(our_jobs)
    
    def cleanup_failed_job_history(self, db: Session, file_id: str, keep_count: int = 3):
        """
        Clean up old FAILED job records to prevent pollution.
        
        Keeps only the most recent N failed jobs per file.
        """
        # Get all failed jobs for this file, ordered by creation
        failed_jobs = db.query(Job).filter(
            Job.file_id == file_id,
            Job.state == 'FAILED'
        ).order_by(Job.created_at.desc()).all()
        
        if len(failed_jobs) <= keep_count:
            return
        
        # Delete excess failed jobs
        jobs_to_delete = failed_jobs[keep_count:]
        for job in jobs_to_delete:
            db.delete(job)
        
        db.commit()
        logger.debug(f"Cleaned up {len(jobs_to_delete)} old failed jobs for file {file_id}")


# Global singleton
job_integrity_service = JobIntegrityService()
