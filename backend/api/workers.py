"""
Workers API - Endpoints for monitoring worker status
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services.worker_status_service import worker_status_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workers", tags=["workers"])


@router.get("/status")
async def get_worker_status(db: Session = Depends(get_db)):
    """
    Get real-time status of all background workers.

    Returns:
        - workers: List of worker status objects
        - queue_counts: Number of jobs queued for each worker
        - paused: Which worker types are paused
        - timestamp: Current timestamp
    """
    try:
        status = await worker_status_service.get_status_summary(db)
        return status
    except Exception as e:
        logger.error(f"Error getting worker status: {e}", exc_info=True)
        return {
            'workers': [],
            'queue_counts': {},
            'paused': {'processing': False, 'analytics': False},
            'timestamp': 0,
            'error': str(e)
        }
