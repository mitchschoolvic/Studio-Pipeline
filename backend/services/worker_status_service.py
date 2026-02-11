"""
Worker Status Service - Tracks real-time status of all background workers

Provides centralized tracking of worker states, current jobs, and performance metrics.
Used by the /api/workers/status endpoint and WebSocket broadcasts.
"""
import asyncio
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session
from models import Job, File, Setting
from config.ai_config import AI_ENABLED
import logging

logger = logging.getLogger(__name__)


class WorkerStatus:
    """Tracks the status of a single worker"""

    def __init__(self, worker_type: str, name: str):
        self.worker_type = worker_type  # 'pipeline' or 'analytics'
        self.name = name
        self.state = 'IDLE'  # IDLE, ACTIVE, PAUSED, WAITING, THROTTLED, ERROR
        self.current_job_id: Optional[str] = None
        self.current_file_id: Optional[str] = None
        self.current_filename: Optional[str] = None
        self.progress_pct: float = 0.0
        self.stage: Optional[str] = None
        self.substep: Optional[str] = None
        self.substep_progress: float = 0.0
        self.detail: Optional[str] = None
        self.wait_reason: Optional[str] = None
        self.speed_mbps: Optional[float] = None
        self.duration_seconds: Optional[int] = None
        self.gpu_lock_held: bool = False
        self.is_cancellable: bool = False
        self.last_activity: Optional[float] = None
        self.error_message: Optional[str] = None
        self.cpu_percent: Optional[float] = None
        self.batch_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            'worker_type': self.worker_type,
            'name': self.name,
            'state': self.state,
            'current_job_id': self.current_job_id,
            'current_file_id': self.current_file_id,
            'current_filename': self.current_filename,
            'progress_pct': self.progress_pct,
            'stage': self.stage,
            'substep': self.substep,
            'substep_progress': self.substep_progress,
            'detail': self.detail,
            'wait_reason': self.wait_reason,
            'speed_mbps': self.speed_mbps,
            'duration_seconds': self.duration_seconds,
            'gpu_lock_held': self.gpu_lock_held,
            'is_cancellable': self.is_cancellable,
            'last_activity': self.last_activity,
            'last_activity_ago': self._time_ago(self.last_activity) if self.last_activity else None,
            'error_message': self.error_message,
            'cpu_percent': self.cpu_percent,
            'batch_count': self.batch_count
        }

    def _time_ago(self, timestamp: float) -> str:
        """Format time ago string"""
        seconds = int(time.time() - timestamp)
        if seconds < 60:
            return f"{seconds}s ago"
        elif seconds < 3600:
            return f"{seconds // 60}m ago"
        else:
            return f"{seconds // 3600}h ago"

    def update_from_job(self, job: Job, file: File):
        """Update status from a running job"""
        self.current_job_id = job.id
        self.current_file_id = file.id
        self.current_filename = file.filename
        self.progress_pct = job.progress_pct or 0.0
        self.detail = job.progress_stage
        self.is_cancellable = job.is_cancellable
        self.last_activity = time.time()

        # Extract stage/substep from file if available
        if hasattr(file, 'processing_stage') and file.processing_stage:
            self.substep = file.processing_stage
            self.substep_progress = file.processing_stage_progress or 0.0

        # Set state based on job state
        if job.state == 'RUNNING':
            self.state = 'ACTIVE'
        elif job.state == 'QUEUED':
            self.state = 'WAITING'

    def clear(self):
        """Clear current job info and return to idle"""
        self.state = 'IDLE'
        self.current_job_id = None
        self.current_file_id = None
        self.current_filename = None
        self.progress_pct = 0.0
        self.stage = None
        self.substep = None
        self.substep_progress = 0.0
        self.detail = None
        self.wait_reason = None
        self.speed_mbps = None
        self.duration_seconds = None
        self.is_cancellable = False
        self.error_message = None
        self.last_activity = time.time()


class WorkerStatusService:
    """
    Centralized service for tracking all worker statuses.

    Workers update their status through this service, and the API/WebSocket
    query this service for current state.
    """

    def __init__(self):
        # Initialize worker status objects
        self.workers = {
            'copy': WorkerStatus('pipeline', 'Copy Worker'),
            'process': WorkerStatus('pipeline', 'Process Worker'),
            'organize': WorkerStatus('pipeline', 'Organize Worker'),
            'thumbnail': WorkerStatus('pipeline', 'Thumbnail Worker'),
        }

        # Add AI workers if enabled
        if AI_ENABLED:
            self.workers['transcribe'] = WorkerStatus('analytics', 'Transcribe Worker')
            self.workers['analyze'] = WorkerStatus('analytics', 'Analyze Worker')

        self._lock = asyncio.Lock()

    async def update_worker_status(
        self,
        worker_name: str,
        state: str = None,
        job: Job = None,
        file: File = None,
        **kwargs
    ):
        """
        Update a worker's status.

        Args:
            worker_name: 'copy', 'process', 'organize', 'thumbnail', 'transcribe', 'analyze'
            state: IDLE, ACTIVE, PAUSED, WAITING, THROTTLED, ERROR
            job: Current job being processed
            file: Current file being processed
            **kwargs: Additional status fields (speed_mbps, substep, etc.)
        """
        async with self._lock:
            if worker_name not in self.workers:
                logger.warning(f"Unknown worker: {worker_name}")
                return

            worker = self.workers[worker_name]

            # Update state if provided
            if state:
                worker.state = state

            # Update from job/file if provided
            if job and file:
                worker.update_from_job(job, file)

            # Update additional fields
            for key, value in kwargs.items():
                if hasattr(worker, key):
                    setattr(worker, key, value)

            worker.last_activity = time.time()

    async def clear_worker_status(self, worker_name: str):
        """Clear a worker's status (return to idle)"""
        async with self._lock:
            if worker_name in self.workers:
                self.workers[worker_name].clear()

    async def get_status_summary(self, db: Session) -> Dict[str, Any]:
        """
        Get comprehensive status summary of all workers.

        Returns:
            Dictionary with worker statuses and queue counts
        """
        async with self._lock:
            # Get current worker states
            worker_list = [w.to_dict() for w in self.workers.values()]

            # Query database for current running jobs and queue counts
            try:
                # Get running jobs to update worker states
                running_jobs = db.query(Job).filter(Job.state == 'RUNNING').all()

                for job in running_jobs:
                    worker_name = self._job_kind_to_worker_name(job.kind)
                    if worker_name in self.workers:
                        worker = self.workers[worker_name]
                        if worker.state == 'IDLE':
                            # Update worker with job info if not already set
                            worker.update_from_job(job, job.file)

                # Get queue counts
                queue_counts = {}
                for kind in ['COPY', 'PROCESS', 'ORGANIZE', 'TRANSCRIBE', 'ANALYZE']:
                    count = db.query(Job).filter(
                        Job.kind == kind,
                        Job.state == 'QUEUED'
                    ).count()
                    queue_counts[kind.lower()] = count

                # Check pause states
                pause_processing = db.query(Setting).filter(
                    Setting.key == 'pause_processing'
                ).first()
                pause_analytics = db.query(Setting).filter(
                    Setting.key == 'pause_analytics'
                ).first()

                paused = {
                    'processing': pause_processing.value == 'true' if pause_processing else False,
                    'analytics': pause_analytics.value == 'true' if pause_analytics else False
                }

                # Update worker states based on pause settings
                if paused['processing']:
                    for worker_name in ['process']:
                        if self.workers[worker_name].state == 'IDLE':
                            self.workers[worker_name].state = 'PAUSED'
                            self.workers[worker_name].wait_reason = 'Processing paused in settings'
                else:
                    # Clear PAUSED state when processing is resumed
                    for worker_name in ['process']:
                        if self.workers[worker_name].state == 'PAUSED' and self.workers[worker_name].wait_reason == 'Processing paused in settings':
                            self.workers[worker_name].state = 'IDLE'
                            self.workers[worker_name].wait_reason = None

                if AI_ENABLED and paused['analytics']:
                    for worker_name in ['transcribe', 'analyze']:
                        if worker_name in self.workers and self.workers[worker_name].state == 'IDLE':
                            self.workers[worker_name].state = 'PAUSED'
                            self.workers[worker_name].wait_reason = 'Analytics paused in settings'
                elif AI_ENABLED:
                    # Clear PAUSED state when analytics is resumed
                    for worker_name in ['transcribe', 'analyze']:
                        if worker_name in self.workers and self.workers[worker_name].state == 'PAUSED' and self.workers[worker_name].wait_reason == 'Analytics paused in settings':
                            self.workers[worker_name].state = 'IDLE'
                            self.workers[worker_name].wait_reason = None

                # Check for blocking conditions when workers are IDLE but jobs are queued
                self._check_blocking_conditions(db, queue_counts, paused)

                # Refresh worker list after updates
                worker_list = [w.to_dict() for w in self.workers.values()]

                return {
                    'workers': worker_list,
                    'queue_counts': queue_counts,
                    'paused': paused,
                    'timestamp': time.time()
                }

            except Exception as e:
                logger.error(f"Error getting status summary: {e}", exc_info=True)
                return {
                    'workers': worker_list,
                    'queue_counts': {},
                    'paused': {'processing': False, 'analytics': False},
                    'timestamp': time.time(),
                    'error': str(e)
                }

    def _job_kind_to_worker_name(self, kind: str) -> str:
        """Map job kind to worker name"""
        mapping = {
            'COPY': 'copy',
            'PROCESS': 'process',
            'ORGANIZE': 'organize',
            'TRANSCRIBE': 'transcribe',
            'ANALYZE': 'analyze'
        }
        return mapping.get(kind, 'unknown')

    def _check_blocking_conditions(self, db: Session, queue_counts: dict, paused: dict):
        """
        Check for blocking conditions when workers are IDLE but jobs are queued.
        Updates worker state to WAITING with descriptive wait_reason.
        """
        try:
            # Check analytics workers (only if AI enabled)
            if AI_ENABLED:
                self._check_analyze_worker_blocking(db, queue_counts.get('analyze', 0), paused)
                self._check_transcribe_worker_blocking(db, queue_counts.get('transcribe', 0))

            # Check pipeline workers
            self._check_process_worker_blocking(db, queue_counts.get('process', 0), paused)

        except Exception as e:
            logger.error(f"Error checking blocking conditions: {e}", exc_info=True)

    def _check_analyze_worker_blocking(self, db: Session, queue_count: int, paused: dict):
        """Check if analyze worker is blocked and update its status"""
        if queue_count == 0 or 'analyze' not in self.workers:
            return

        worker = self.workers['analyze']

        # Skip if already active or already has a wait reason set
        if worker.state not in ('IDLE', 'PAUSED'):
            return

        # If paused, enhance message with queue count
        if paused.get('analytics', False):
            worker.wait_reason = f"{queue_count} job{'s' if queue_count != 1 else ''} paused in settings"
            return

        # Check for idle mode blocking
        idle_setting = db.query(Setting).filter(
            Setting.key == 'run_analytics_when_idle'
        ).first()

        if idle_setting and idle_setting.value == 'true':
            pipeline_active = db.query(Job).filter(
                Job.kind.in_(['COPY', 'PROCESS', 'ORGANIZE']),
                Job.state == 'RUNNING'
            ).count() > 0

            if pipeline_active:
                worker.state = 'WAITING'
                worker.wait_reason = f"{queue_count} job{'s' if queue_count != 1 else ''} waiting for pipeline to idle"
                return

        # Check for missing or incomplete transcripts
        from models_analytics import FileAnalytics
        from sqlalchemy import or_, func

        # Count jobs with missing or very short transcripts (< 20 chars = empty/whitespace)
        blocked_by_transcript = db.query(Job).join(
            File, Job.file_id == File.id
        ).join(
            FileAnalytics, FileAnalytics.file_id == File.id
        ).filter(
            Job.kind == 'ANALYZE',
            Job.state == 'QUEUED',
            or_(
                FileAnalytics.transcript.is_(None),
                FileAnalytics.transcript == '',
                func.length(FileAnalytics.transcript) < 20
            )
        ).count()

        # Check for orphaned jobs (ANALYZE jobs without FileAnalytics records)
        orphaned_jobs = db.query(Job).outerjoin(
            File, Job.file_id == File.id
        ).outerjoin(
            FileAnalytics, FileAnalytics.file_id == File.id
        ).filter(
            Job.kind == 'ANALYZE',
            Job.state == 'QUEUED',
            FileAnalytics.id.is_(None)
        ).count()

        if blocked_by_transcript > 0 or orphaned_jobs > 0:
            worker.state = 'WAITING'
            reasons = []
            if blocked_by_transcript > 0:
                reasons.append(f"{blocked_by_transcript} job{'s' if blocked_by_transcript != 1 else ''} missing transcript data")
            if orphaned_jobs > 0:
                reasons.append(f"{orphaned_jobs} orphaned job{'s' if orphaned_jobs != 1 else ''}")
            worker.wait_reason = ", ".join(reasons)
            return

    def _check_transcribe_worker_blocking(self, db: Session, queue_count: int):
        """Check if transcribe worker is blocked and update its status"""
        if queue_count == 0 or 'transcribe' not in self.workers:
            return

        worker = self.workers['transcribe']

        # Transcribe worker has no blocking conditions currently
        # Could add checks for missing models, etc. in the future
        pass

    def _check_process_worker_blocking(self, db: Session, queue_count: int, paused: dict):
        """Check if process worker is blocked and update its status"""
        if queue_count == 0 or 'process' not in self.workers:
            return

        worker = self.workers['process']

        # If paused, enhance message with queue count
        if paused.get('processing', False) and worker.state == 'PAUSED':
            worker.wait_reason = f"{queue_count} job{'s' if queue_count != 1 else ''} paused in settings"
            return


# Global singleton
worker_status_service = WorkerStatusService()
