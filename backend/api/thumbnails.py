"""
Thumbnail API Endpoints

Provides endpoints for serving and managing video thumbnails.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from database import get_db
from models import File
from pathlib import Path
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/thumbnails/stats")
async def get_thumbnail_stats(db: Session = Depends(get_db)):
    """
    Get thumbnail generation statistics.
    
    Returns counts by state and other useful metrics.
    """
    from sqlalchemy import func
    
    # Count by state
    state_counts = db.query(
        File.thumbnail_state,
        func.count(File.id)
    ).group_by(File.thumbnail_state).all()
    
    stats = {
        'by_state': {state: count for state, count in state_counts},
        'total_files': db.query(File).count(),
        'pending': db.query(File).filter(File.thumbnail_state == 'PENDING').count(),
        'ready': db.query(File).filter(File.thumbnail_state == 'READY').count(),
        'failed': db.query(File).filter(File.thumbnail_state == 'FAILED').count(),
        'generating': db.query(File).filter(File.thumbnail_state == 'GENERATING').count(),
        'skipped': db.query(File).filter(File.thumbnail_state == 'SKIPPED').count()
    }
    
    # Add recent generation times
    recent_generated = db.query(File).filter(
        File.thumbnail_state == 'READY',
        File.thumbnail_generated_at.isnot(None)
    ).order_by(File.thumbnail_generated_at.desc()).limit(10).all()
    
    if recent_generated:
        generation_times = []
        for file in recent_generated:
            if file.thumbnail_generated_at and file.created_at:
                time_diff = (file.thumbnail_generated_at - file.created_at).total_seconds()
                generation_times.append(time_diff)
        
        if generation_times:
            stats['avg_generation_time'] = sum(generation_times) / len(generation_times)
            stats['max_generation_time'] = max(generation_times)
            stats['min_generation_time'] = min(generation_times)
    
    return stats


@router.get("/thumbnails/{file_id}")
async def get_thumbnail(file_id: str, db: Session = Depends(get_db)):
    """
    Get thumbnail for a file.
    
    Returns:
        - JPEG image if thumbnail is READY
        - 202 (Accepted) if thumbnail is PENDING or GENERATING
        - 404 (Not Found) if file not found or thumbnail FAILED
    
    The frontend should poll this endpoint for PENDING/GENERATING files.
    """
    file = db.query(File).filter(File.id == file_id).first()
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Return thumbnail if ready
    if file.thumbnail_state == 'READY' and file.thumbnail_path:
        thumbnail_path = Path(file.thumbnail_path)
        
        # Self-healing: Check if path is valid, if not try to find it in standard directory
        # This handles cases where DB was moved between machines with different usernames
        if not thumbnail_path.exists():
            # Standard path: ~/Library/Application Support/StudioPipeline/thumbnails
            standard_dir = Path.home() / "Library/Application Support/StudioPipeline/thumbnails"
            potential_path = standard_dir / thumbnail_path.name
            
            if potential_path.exists():
                logger.info(f"✨ Auto-healing thumbnail path for {file.filename}: {thumbnail_path} -> {potential_path}")
                file.thumbnail_path = str(potential_path)
                db.commit()
                thumbnail_path = potential_path
        
        if thumbnail_path.exists():
            # Determine media type
            media_type = "image/jpeg"
            if thumbnail_path.suffix.lower() == '.png':
                media_type = "image/png"
            
            # Add cache headers for performance
            return FileResponse(
                thumbnail_path,
                media_type=media_type,
                headers={
                    "Cache-Control": "public, max-age=86400",  # Cache for 1 day
                    "ETag": f"{file_id}-{int(file.thumbnail_generated_at.timestamp())}",
                    "Last-Modified": file.thumbnail_generated_at.strftime("%a, %d %b %Y %H:%M:%S GMT")
                }
            )
        else:
            # Thumbnail was deleted or moved
            logger.warning(f"Thumbnail file missing for {file.filename}: {thumbnail_path}")
            file.thumbnail_state = 'FAILED'
            file.thumbnail_error = "Thumbnail file not found on disk"
            db.commit()
            raise HTTPException(status_code=404, detail="Thumbnail file missing")
    
    # Return appropriate status for non-ready thumbnails
    if file.thumbnail_state == 'PENDING':
        # Prevent browsers from caching the pending response
        raise HTTPException(
            status_code=202,
            detail="Thumbnail generation pending",
            headers={"Cache-Control": "no-store"}
        )
    elif file.thumbnail_state == 'GENERATING':
        # Prevent browsers from caching the generating response
        raise HTTPException(
            status_code=202,
            detail="Thumbnail being generated",
            headers={"Cache-Control": "no-store"}
        )
    elif file.thumbnail_state == 'FAILED':
        # Prevent caching failures so clients can retry after fixes
        raise HTTPException(
            status_code=404,
            detail=f"Thumbnail generation failed: {file.thumbnail_error or 'Unknown error'}",
            headers={"Cache-Control": "no-store"}
        )
    elif file.thumbnail_state == 'SKIPPED':
        # Empty file - should use client-side placeholder
        raise HTTPException(
            status_code=404,
            detail="Empty file - use placeholder",
            headers={"Cache-Control": "no-store"}
        )
    
    raise HTTPException(status_code=404, detail="Thumbnail not available")


@router.post("/thumbnails/{file_id}/regenerate")
async def regenerate_thumbnail(file_id: str, db: Session = Depends(get_db)):
    """
    Request thumbnail regeneration for a file.
    
    Resets thumbnail state to PENDING, which will be picked up by the worker.
    Useful for retrying failed thumbnails or updating thumbnails after re-processing.
    """
    file = db.query(File).filter(File.id == file_id).first()
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Don't regenerate for empty files
    if file.is_empty:
        raise HTTPException(
            status_code=400,
            detail="Cannot regenerate thumbnail for empty file"
        )
    
    # Reset thumbnail state
    old_state = file.thumbnail_state
    file.thumbnail_state = 'PENDING'
    file.thumbnail_error = None
    db.commit()
    
    logger.info(f"Thumbnail regeneration requested for {file.filename} (was {old_state})")
    
    return {
        "message": "Thumbnail regeneration queued",
        "file_id": file_id,
        "previous_state": old_state
    }


@router.post("/thumbnails/regenerate-all")
async def regenerate_all_thumbnails(db: Session = Depends(get_db)):
    """
    Reset all thumbnails to PENDING for regeneration.
    
    Use with caution - this will regenerate ALL thumbnails.
    Useful after a major video re-processing or bug fix.
    """
    # Reset all non-empty, non-skipped files
    updated = db.query(File).filter(
        File.is_empty == False,
        File.thumbnail_state.in_(['READY', 'FAILED'])
    ).update({
        'thumbnail_state': 'PENDING',
        'thumbnail_error': None
    }, synchronize_session=False)
    
    db.commit()
    
    logger.warning(f"Regeneration requested for {updated} thumbnails")
    
    return {
        "message": f"Regeneration queued for {updated} thumbnails",
        "count": updated
    }


@router.delete("/thumbnails/clear-failed")
async def clear_failed_thumbnails(db: Session = Depends(get_db)):
    """
    Reset failed thumbnails to PENDING for retry.
    
    Useful for retrying after fixing issues.
    """
    updated = db.query(File).filter(
        File.thumbnail_state == 'FAILED'
    ).update({
        'thumbnail_state': 'PENDING',
        'thumbnail_error': None
    }, synchronize_session=False)
    
    db.commit()
    
    logger.info(f"Retry queued for {updated} failed thumbnails")
    
    return {
        "message": f"Retry queued for {updated} failed thumbnails",
        "count": updated
    }
