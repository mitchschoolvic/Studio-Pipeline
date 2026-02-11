"""
Jobs and Queue API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from database import get_db
from models import Job, File
from schemas import Job as JobSchema
from services.job_service import JobService
from constants import HTTPStatus
from typing import List
from pydantic import BaseModel
from exceptions import DatabaseError
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class QueueStats(BaseModel):
    """Queue statistics"""
    total_jobs: int
    queued_jobs: int
    running_jobs: int
    done_jobs: int
    failed_jobs: int
    jobs_by_kind: dict[str, int]


class CancelResult(BaseModel):
    """Job cancellation result"""
    success: bool
    message: str


@router.get("/jobs/active")
async def get_active_jobs(db: Session = Depends(get_db)) -> dict:
    """
    Get count and details of currently running jobs.

    Returns jobs where state='RUNNING' with associated file information.
    Used by frontend to show pause confirmation dialog.

    Raises:
        HTTPException: If database query fails
    """
    try:
        job_service = JobService(db)
        return job_service.get_active_jobs_summary()
    except Exception as e:
        logger.error(f"Failed to retrieve active jobs: {e}", exc_info=True)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Failed to retrieve active jobs")


@router.post("/jobs/cancel-active")
async def cancel_active_jobs(db: Session = Depends(get_db)) -> dict:
    """
    Mark all active jobs for cancellation and reset to resumable checkpoints.

    Sets cancellation_requested=True and checkpoint_state for each running job.
    The workers will detect this and handle cancellation gracefully.

    Returns:
        dict: Count of jobs marked for cancellation

    Raises:
        HTTPException: If database operation fails
    """
    try:
        job_service = JobService(db)
        return job_service.cancel_active_jobs()
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to cancel active jobs: {e}", exc_info=True)
        raise HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail="Failed to cancel active jobs")


@router.get("/jobs", response_model=List[JobSchema])
def list_jobs(
    state: str | None = None,
    kind: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    List jobs with optional filtering
    
    Args:
        state: Filter by job state (QUEUED, RUNNING, DONE, FAILED)
        kind: Filter by job kind (COPY, PROCESS, ORGANIZE)
        limit: Maximum number of jobs to return (default 100)
        db: Database session
        
    Returns:
        List of jobs ordered by priority and creation time
    """
    query = db.query(Job).options(joinedload(Job.file))
    
    if state:
        query = query.filter(Job.state == state.upper())
    
    if kind:
        query = query.filter(Job.kind == kind.upper())
    
    # Order by priority (high to low), then creation time (old to new)
    query = query.order_by(Job.priority.desc(), Job.created_at)
    
    jobs = query.limit(limit).all()
    
    return jobs


@router.get("/jobs/{job_id}", response_model=JobSchema)
def get_job(job_id: str, db: Session = Depends(get_db)):
    """
    Get details for a specific job
    
    Args:
        job_id: Job UUID
        db: Database session
        
    Returns:
        Job details with related file information
    """
    job = db.query(Job).options(joinedload(Job.file)).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found")
    
    return job


@router.get("/queue/stats", response_model=QueueStats)
def get_queue_stats(db: Session = Depends(get_db)):
    """
    Get queue statistics

    Returns counts of jobs by state and kind
    """
    job_service = JobService(db)
    stats = job_service.get_queue_stats()

    return QueueStats(
        total_jobs=stats["total_jobs"],
        queued_jobs=stats["queued_jobs"],
        running_jobs=stats["running_jobs"],
        done_jobs=stats["done_jobs"],
        failed_jobs=stats["failed_jobs"],
        jobs_by_kind=stats["jobs_by_kind"]
    )


@router.post("/jobs/{job_id}/cancel", response_model=CancelResult)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    """
    Cancel a queued or running job

    Args:
        job_id: Job UUID
        db: Database session

    Returns:
        Cancellation result

    Note: This sets the job state to FAILED with an error message.
    Running jobs may not stop immediately - workers should check job state periodically.
    """
    job_service = JobService(db)
    result = job_service.cancel_job(job_id)

    if not result["success"] and result["message"] == "Job not found":
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Job not found")

    return CancelResult(
        success=result["success"],
        message=result["message"]
    )


@router.post("/jobs/{job_id}/retry", response_model=JobSchema)
def retry_job(job_id: str, db: Session = Depends(get_db)):
    """
    Retry a failed job with checkpoint reset.

    Args:
        job_id: Job UUID
        db: Database session

    Returns:
        New retry job

    Note: Resets file to resumable checkpoint and creates new job.
    This ensures we don't retry from a corrupted/partial state.
    """
    job_service = JobService(db)

    try:
        return job_service.retry_job(job_id)
    except ValueError as e:
        error_msg = str(e)
        if error_msg == "Job not found":
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=error_msg)
        elif error_msg == "Associated file not found":
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=error_msg)
        elif "Cannot retry" in error_msg:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=error_msg)
        else:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=error_msg)
