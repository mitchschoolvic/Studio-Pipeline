"""
Job Service

Handles business logic for job operations including retrieving, formatting,
and managing jobs.

Extracted from jobs.py to follow Single Responsibility Principle.
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from models import Job, File
from repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)


class JobService:
    """Service for job-related business logic."""

    def __init__(self, db: Session):
        """
        Initialize JobService.

        Args:
            db: Database session
        """
        self.db = db
        self.job_repo = JobRepository(db)

    def get_active_jobs_summary(self) -> Dict[str, Any]:
        """
        Get count and details of currently running jobs.

        Returns jobs where state='RUNNING' with associated file information.
        Used by frontend to show pause confirmation dialog.

        Returns:
            Dictionary containing:
                - count: Number of active jobs
                - jobs: List of job data dictionaries
        """
        active_jobs = self.db.query(Job).filter(
            Job.state == 'RUNNING'
        ).all()

        jobs_data = self._format_jobs_list(active_jobs)

        return {
            "count": len(active_jobs),
            "jobs": jobs_data
        }

    def cancel_active_jobs(self) -> Dict[str, Any]:
        """
        Mark all active jobs for cancellation and reset to resumable checkpoints.

        Sets cancellation_requested=True and checkpoint_state for each running job.
        The workers will detect this and handle cancellation gracefully.

        Returns:
            Dictionary containing:
                - cancelled: Number of jobs marked for cancellation
                - message: Summary message
        """
        active_jobs = self.db.query(Job).filter(
            Job.state == 'RUNNING'
        ).all()

        if not active_jobs:
            return {
                "cancelled": 0,
                "message": "No active jobs to cancel"
            }

        reset_count = 0
        for job in active_jobs:
            job.cancellation_requested = True

            # Store checkpoint to reset to when worker detects cancellation
            if job.file:
                job.checkpoint_state = job.file.get_resumable_checkpoint()
                logger.info(
                    f"Marked job {job.id} ({job.kind}) for cancellation, "
                    f"will reset to {job.checkpoint_state}"
                )

            reset_count += 1

        self.db.commit()

        return {
            "cancelled": reset_count,
            "message": f"Marked {reset_count} job(s) for cancellation. "
                       f"Workers will detect and reset to checkpoints."
        }

    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """
        Cancel a queued or running job.

        Args:
            job_id: Job UUID

        Returns:
            Dictionary containing:
                - success: Whether cancellation was successful
                - message: Result message

        Note: This sets the job state to FAILED with an error message.
        Running jobs may not stop immediately - workers should check job state periodically.
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()

        if not job:
            return {
                "success": False,
                "message": "Job not found"
            }

        if job.state == "DONE":
            return {
                "success": False,
                "message": "Cannot cancel a completed job"
            }

        if job.state == "FAILED":
            return {
                "success": False,
                "message": "Job is already failed/cancelled"
            }

        # Mark job as failed with cancellation message
        job.state = "FAILED"
        job.error_message = "Job cancelled by user"

        # Update file state if this was the last job
        file = job.file
        if file:
            # Check if there are any other non-failed jobs for this file
            remaining_jobs = self.db.query(Job).filter(
                Job.file_id == file.id,
                Job.id != job.id,
                Job.state.in_(["QUEUED", "RUNNING"])
            ).count()

            if remaining_jobs == 0:
                # No more jobs, mark file as failed
                file.state = "FAILED"
                file.error_message = "Processing cancelled by user"

        self.db.commit()

        logger.info(f"Job {job_id} cancelled by user")

        return {
            "success": True,
            "message": f"Job {job_id} cancelled successfully"
        }

    def retry_job(self, job_id: str) -> Job:
        """
        Retry a failed job with checkpoint reset.

        Args:
            job_id: Job UUID

        Returns:
            New retry job

        Raises:
            ValueError: If job cannot be retried

        Note: Resets file to resumable checkpoint and creates new job.
        This ensures we don't retry from a corrupted/partial state.
        """
        job = self.db.query(Job).filter(Job.id == job_id).first()

        if not job:
            raise ValueError("Job not found")

        if job.state != "FAILED":
            raise ValueError(
                f"Cannot retry job in state {job.state}. Only FAILED jobs can be retried."
            )

        file = job.file
        if not file:
            raise ValueError("Associated file not found")

        # Get resumable checkpoint
        checkpoint = file.get_resumable_checkpoint()

        # Reset file state to checkpoint
        file.state = checkpoint
        file.error_message = None

        # Determine next job kind based on checkpoint
        if checkpoint == 'DISCOVERED':
            next_kind = 'COPY'
        elif checkpoint == 'COPIED':
            next_kind = 'PROCESS'
        elif checkpoint == 'PROCESSED':
            next_kind = 'ORGANIZE'
        else:
            raise ValueError(f"Cannot retry from checkpoint {checkpoint}")

        # Create new job (don't reuse the failed one)
        new_job = Job(
            file_id=file.id,
            kind=next_kind,
            state='QUEUED',
            priority=job.priority,
            retries=0,  # Reset retry counter for manual retry
            max_retries=job.max_retries
        )

        self.db.add(new_job)
        self.db.commit()
        self.db.refresh(new_job)

        logger.info(
            f"Created retry job {new_job.id} ({next_kind}) for file {file.filename} "
            f"at checkpoint {checkpoint} (old job: {job_id})"
        )

        return new_job

    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.

        Returns counts of jobs by state and kind.

        Returns:
            Dictionary containing job statistics
        """
        # Count jobs by state
        total_jobs = self.db.query(func.count(Job.id)).scalar() or 0
        queued_jobs = self.db.query(func.count(Job.id)).filter(Job.state == "QUEUED").scalar() or 0
        running_jobs = self.db.query(func.count(Job.id)).filter(Job.state == "RUNNING").scalar() or 0
        done_jobs = self.db.query(func.count(Job.id)).filter(Job.state == "DONE").scalar() or 0
        failed_jobs = self.db.query(func.count(Job.id)).filter(Job.state == "FAILED").scalar() or 0

        # Count jobs by kind
        jobs_by_kind = {}
        kind_counts = self.db.query(Job.kind, func.count(Job.id)).group_by(Job.kind).all()
        for kind, count in kind_counts:
            jobs_by_kind[kind] = count

        return {
            "total_jobs": total_jobs,
            "queued_jobs": queued_jobs,
            "running_jobs": running_jobs,
            "done_jobs": done_jobs,
            "failed_jobs": failed_jobs,
            "jobs_by_kind": jobs_by_kind
        }

    def _format_jobs_list(self, jobs: List[Job]) -> List[Dict[str, Any]]:
        """
        Format a list of jobs into dictionaries with file information.

        Args:
            jobs: List of Job objects

        Returns:
            List of formatted job dictionaries
        """
        jobs_data = []
        for job in jobs:
            file = job.file
            jobs_data.append({
                "id": job.id,
                "file_id": job.file_id,
                "kind": job.kind,
                "state": job.state,
                "progress_pct": job.progress_pct or 0,
                "progress_stage": job.progress_stage,
                "retries": job.retries,
                "max_retries": job.max_retries,
                "filename": file.filename if file else None,
                "current_state": file.state if file else None,
                "resumable_checkpoint": file.get_resumable_checkpoint() if file else None,
                "is_cancellable": job.is_cancellable
            })

        return jobs_data
