"""
Job repository for job-specific data access operations.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from models import Job as JobModel
from .base_repository import BaseRepository


class JobRepository(BaseRepository[JobModel]):
    """Repository for Job model operations."""

    def __init__(self, db: Session):
        super().__init__(db, JobModel)

    def get_by_state(self, state: str) -> List[JobModel]:
        """
        Get all jobs with a specific state.

        Args:
            state: Job state (QUEUED, RUNNING, DONE, FAILED)

        Returns:
            List of jobs in the specified state
        """
        return self.db.query(self.model).filter(
            self.model.state == state
        ).all()

    def get_by_kind(self, kind: str) -> List[JobModel]:
        """
        Get all jobs of a specific kind.

        Args:
            kind: Job kind (COPY, PROCESS, ORGANIZE)

        Returns:
            List of jobs of the specified kind
        """
        return self.db.query(self.model).filter(
            self.model.kind == kind
        ).all()

    def get_filtered(
        self,
        state: Optional[str] = None,
        kind: Optional[str] = None,
        file_id: Optional[str] = None
    ) -> List[JobModel]:
        """
        Get jobs with optional filtering.

        Args:
            state: Filter by job state
            kind: Filter by job kind
            file_id: Filter by file ID

        Returns:
            List of matching jobs
        """
        query = self.db.query(self.model)

        if state:
            query = query.filter(self.model.state == state)
        if kind:
            query = query.filter(self.model.kind == kind)
        if file_id:
            query = query.filter(self.model.file_id == file_id)

        return query.all()

    def get_with_file(self, job_id: str) -> Optional[JobModel]:
        """
        Get a job with its related file eagerly loaded.

        Args:
            job_id: Job UUID

        Returns:
            Job instance with file, or None if not found
        """
        return self.db.query(self.model).options(
            joinedload(self.model.file)
        ).filter(self.model.id == job_id).first()

    def get_active_jobs(self) -> List[JobModel]:
        """
        Get all currently running jobs.

        Returns:
            List of jobs in RUNNING state
        """
        return self.get_by_state('RUNNING')

    def get_queued_jobs(self) -> List[JobModel]:
        """
        Get all queued jobs, ordered by priority (descending).

        Returns:
            List of queued jobs sorted by priority
        """
        return self.db.query(self.model).filter(
            self.model.state == 'QUEUED'
        ).order_by(self.model.priority.desc()).all()

    def get_failed_jobs(self) -> List[JobModel]:
        """
        Get all failed jobs.

        Returns:
            List of jobs in FAILED state
        """
        return self.get_by_state('FAILED')

    def count_by_state(self, state: str) -> int:
        """
        Count jobs in a specific state.

        Args:
            state: Job state

        Returns:
            Number of jobs in the state
        """
        return self.db.query(self.model).filter(
            self.model.state == state
        ).count()

    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the job queue.

        Returns:
            Dictionary with counts by state and kind
        """
        # Count by state
        state_counts = self.db.query(
            self.model.state,
            func.count(self.model.id).label('count')
        ).group_by(self.model.state).all()

        # Count by kind
        kind_counts = self.db.query(
            self.model.kind,
            func.count(self.model.id).label('count')
        ).group_by(self.model.kind).all()

        return {
            "by_state": {state: count for state, count in state_counts},
            "by_kind": {kind: count for kind, count in kind_counts},
            "total_queued": self.count_by_state('QUEUED'),
            "total_running": self.count_by_state('RUNNING'),
            "total_failed": self.count_by_state('FAILED'),
            "total_done": self.count_by_state('DONE')
        }

    def cancel_job(self, job_id: str) -> Optional[JobModel]:
        """
        Mark a job for cancellation.

        Args:
            job_id: Job UUID

        Returns:
            Updated job instance, or None if not found
        """
        job = self.get_by_id(job_id)
        if job and job.state == 'RUNNING':
            job.cancellation_requested = True
            self.db.flush()
        return job

    def cancel_all_active(self) -> int:
        """
        Request cancellation for all running jobs.

        Returns:
            Number of jobs marked for cancellation
        """
        active_jobs = self.get_active_jobs()
        count = 0

        for job in active_jobs:
            job.cancellation_requested = True
            count += 1

        self.db.flush()
        return count

    def increment_retries(self, job_id: str) -> Optional[JobModel]:
        """
        Increment the retry count for a job.

        Args:
            job_id: Job UUID

        Returns:
            Updated job instance, or None if not found
        """
        job = self.get_by_id(job_id)
        if job:
            job.retries += 1
            self.db.flush()
        return job

    def can_retry(self, job_id: str) -> bool:
        """
        Check if a job can be retried (hasn't exceeded max retries).

        Args:
            job_id: Job UUID

        Returns:
            True if job can be retried, False otherwise
        """
        job = self.get_by_id(job_id)
        if not job:
            return False
        return job.retries < job.max_retries
