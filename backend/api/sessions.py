from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession, joinedload
from sqlalchemy import func
from typing import List, Optional
import subprocess
import platform
from pathlib import Path
from database import get_db
from models import Session as SessionModel, File as FileModel
from schemas import Session, SessionSummary, PipelineStats, File as FileSchema
from constants import HTTPStatus
from pydantic import BaseModel

router = APIRouter()


@router.get("/sessions", response_model=List[SessionSummary])
def list_sessions(
    db: DBSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Filter by session name contains (case-insensitive)"),
    sort: Optional[str] = Query("-discovered_at", description="Sort key: discovered_at, file_count, total_size. Prefix with - for desc")
):
    """Paginated lightweight session list (no files)."""
    from models import File as FileModel
    
    # Subquery to find the 'primary' file (program output) for the thumbnail
    # This avoids the N+1 problem on the frontend
    # We want to join Session with File where File.is_program_output is True
    # If multiple exist (shouldn't happen for program output usually, but safe to take one), 
    # we can just use the join.
    
    # Optimized query:
    # Select SessionModel, and specific columns from FileModel
    q = db.query(
        SessionModel,
        FileModel.id.label('primary_file_id'),
        FileModel.is_empty.label('primary_is_empty'),
        FileModel.state.label('primary_file_state')
    ).outerjoin(
        FileModel, 
        (FileModel.session_id == SessionModel.id) & (FileModel.is_program_output == True)
    )

    if search:
        like = f"%{search.lower()}%"
        q = q.filter(func.lower(SessionModel.name).like(like))
        
    # Sorting
    sort_map = {
        'discovered_at': SessionModel.discovered_at,
        'file_count': SessionModel.file_count,
        'total_size': SessionModel.total_size
    }
    desc = False
    key = sort
    if sort.startswith('-'):
        desc = True
        key = sort[1:]
    col = sort_map.get(key, SessionModel.discovered_at)
    if desc:
        col = col.desc()
    else:
        col = col.asc()
        
    # Execute query
    results = q.order_by(col).limit(limit).offset(offset).all()

    summaries: List[SessionSummary] = []
    for s, primary_file_id, primary_is_empty, primary_file_state in results:
        summaries.append(SessionSummary(
            id=s.id,
            name=s.name,
            recording_date=s.recording_date,
            recording_time=s.recording_time,
            campus=s.campus,
            discovered_at=s.discovered_at,
            file_count=s.file_count,
            total_size=s.total_size,
            primary_file_id=primary_file_id,
            primary_is_empty=primary_is_empty,
            primary_file_state=primary_file_state
        ))
    return summaries

@router.get("/sessions/{session_id}/files", response_model=List[FileSchema])
def list_session_files(
    session_id: str,
    db: DBSession = Depends(get_db),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_jobs: bool = Query(False, description="Include job list for each file")
):
    """Paginated files for a session."""
    query = db.query(FileModel).filter(FileModel.session_id == session_id)
    total = query.count()  # Potential future: return total in header
    files = query.order_by(FileModel.filename).limit(limit).offset(offset).all()
    result: List[FileSchema] = []
    for f in files:
        fs = FileSchema.model_validate(f, from_attributes=True)
        try:
            fs.final_exists = bool(Path(fs.path_final).exists()) if fs.path_final else False
        except Exception:
            fs.final_exists = False
        if not include_jobs:
            fs.jobs = []  # Strip jobs if not requested
        result.append(fs)
    return result


@router.get("/sessions/{session_id}", response_model=Session)
def get_session(session_id: str, db: DBSession = Depends(get_db)):
    """Get a specific session with all files and their jobs"""
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id
    ).options(
        joinedload(SessionModel.files).joinedload(FileModel.jobs)
    ).first()
    
    if not session:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"Session '{session_id}' not found")
    
    # Calculate aggregates
    file_count = len(session.files)
    total_size = sum(file.size for file in session.files)
    
    # Build files with computed final_exists
    files_schemas: List[FileSchema] = []
    for f in session.files:
        fs = FileSchema.model_validate(f, from_attributes=True)
        try:
            fs.final_exists = bool(Path(fs.path_final).exists()) if fs.path_final else False
        except Exception:
            fs.final_exists = False
        files_schemas.append(fs)

    # Build response
    session_dict = {
        'id': session.id,
        'name': session.name,
        'recording_date': session.recording_date,
        'recording_time': session.recording_time,
        'discovered_at': session.discovered_at,
        'file_count': file_count,
        'total_size': total_size,
        'files': files_schemas
    }
    
    return Session(**session_dict)


@router.get("/stats", response_model=PipelineStats)
def get_stats(db: DBSession = Depends(get_db)):
    """Get overall pipeline statistics"""
    from models import Job as JobModel

    # Session stats
    total_sessions = db.query(func.count(SessionModel.id)).scalar()

    # File stats by state
    total_files = db.query(func.count(FileModel.id)).scalar()
    files_discovered = db.query(func.count(FileModel.id)).filter(FileModel.state == 'DISCOVERED').scalar()
    files_copying = db.query(func.count(FileModel.id)).filter(FileModel.state == 'COPYING').scalar()
    files_copied = db.query(func.count(FileModel.id)).filter(FileModel.state == 'COPIED').scalar()
    files_processing = db.query(func.count(FileModel.id)).filter(FileModel.state == 'PROCESSING').scalar()
    files_processed = db.query(func.count(FileModel.id)).filter(FileModel.state == 'PROCESSED').scalar()
    files_organizing = db.query(func.count(FileModel.id)).filter(FileModel.state == 'ORGANIZING').scalar()
    files_completed = db.query(func.count(FileModel.id)).filter(FileModel.state == 'COMPLETED').scalar()
    files_failed = db.query(func.count(FileModel.id)).filter(FileModel.state == 'FAILED').scalar()

    # Job stats by state
    jobs_queued = db.query(func.count(JobModel.id)).filter(JobModel.state == 'QUEUED').scalar()
    jobs_running = db.query(func.count(JobModel.id)).filter(JobModel.state == 'RUNNING').scalar()
    jobs_done = db.query(func.count(JobModel.id)).filter(JobModel.state == 'DONE').scalar()
    jobs_failed = db.query(func.count(JobModel.id)).filter(JobModel.state == 'FAILED').scalar()

    # Size stats
    total_size_bytes = db.query(func.sum(FileModel.size)).scalar() or 0
    completed_size_bytes = db.query(func.sum(FileModel.size)).filter(
        FileModel.state == 'COMPLETED'
    ).scalar() or 0

    return PipelineStats(
        total_sessions=total_sessions,
        total_files=total_files,
        files_discovered=files_discovered,
        files_copying=files_copying,
        files_copied=files_copied,
        files_processing=files_processing,
        files_processed=files_processed,
        files_organizing=files_organizing,
        files_completed=files_completed,
        files_failed=files_failed,
        jobs_queued=jobs_queued,
        jobs_running=jobs_running,
        jobs_done=jobs_done,
        jobs_failed=jobs_failed,
        total_size_bytes=total_size_bytes,
        completed_size_bytes=completed_size_bytes
    )


@router.post("/sessions/{session_id}/open-folder")
def open_session_folder(session_id: str, db: DBSession = Depends(get_db)):
    """Open the session's output folder in Finder (macOS only)"""
    # Check platform
    if platform.system() != 'Darwin':
        raise HTTPException(
            status_code=HTTPStatus.NOT_IMPLEMENTED,
            detail="This feature is only supported on macOS"
        )

    # Get session with files
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id
    ).options(
        joinedload(SessionModel.files)
    ).first()

    if not session:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Session '{session_id}' not found"
        )

    # Find first completed file with path_final
    completed_files = [f for f in session.files if f.state == 'COMPLETED' and f.path_final]

    if not completed_files:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="No completed files found for this session"
        )

    # Extract session folder from path_final
    # Path structure: {output}/{year}/{month}/{day}/{session_folder}/{file}
    # Go up 2 levels to get to session folder (parent of parent)
    first_file_path = Path(completed_files[0].path_final)

    # If file is in a subfolder (e.g., "Video ISO Files/CAM 1.mp4"), go up 3 levels
    # Otherwise go up 1 level to get session folder
    session_folder = first_file_path.parent

    # Check if this is a subfolder (contains relative path with /)
    if completed_files[0].relative_path and '/' in completed_files[0].relative_path:
        # File is in subfolder, go up one more level to session root
        session_folder = session_folder.parent

    # Verify folder exists
    if not session_folder.exists() or not session_folder.is_dir():
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Folder not found: {session_folder}"
        )

    # Open folder in Finder
    try:
        subprocess.run(['open', str(session_folder)], check=True)
        return {
            "success": True,
            "message": "Folder opened in Finder",
            "path": str(session_folder)
        }
    except subprocess.CalledProcessError as e:
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to open folder: {str(e)}"
        )


@router.delete("/sessions/{session_id}")
async def delete_session_from_database(session_id: str, db: DBSession = Depends(get_db)):
    """
    Permanently delete a session and all its files from the database.
    This does NOT delete files from FTP or the destination folder.

    WARNING: This operation cannot be undone!

    Args:
        session_id: Session UUID
        db: Database session

    Returns:
        dict: Deletion results with counts

    Raises:
        HTTPException: If session not found or deletion fails
    """
    from models import Job as JobModel, Event as EventModel
    from services.websocket import manager

    # First, check if session exists and get counts
    session = db.query(SessionModel).filter(
        SessionModel.id == session_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"Session '{session_id}' not found"
        )

    try:
        # Get file IDs for this session
        file_ids = [f.id for f in db.query(FileModel.id).filter(
            FileModel.session_id == session_id
        ).all()]

        # Count records before deletion
        file_count = len(file_ids)
        job_count = db.query(func.count(JobModel.id)).filter(
            JobModel.file_id.in_(file_ids)
        ).scalar() if file_ids else 0

        # Delete associated events for all files in this session
        events_deleted = 0
        if file_ids:
            events_deleted = db.query(EventModel).filter(
                EventModel.file_id.in_(file_ids)
            ).delete(synchronize_session=False)

            # Delete all jobs for files in this session
            db.query(JobModel).filter(
                JobModel.file_id.in_(file_ids)
            ).delete(synchronize_session=False)

            # Delete all files in this session
            db.query(FileModel).filter(
                FileModel.session_id == session_id
            ).delete(synchronize_session=False)

        # Delete the session itself
        session_name = session.name
        db.query(SessionModel).filter(
            SessionModel.id == session_id
        ).delete(synchronize_session=False)

        db.commit()

        # Broadcast session deletion to WebSocket clients
        await manager.broadcast({
            'type': 'session.deleted',
            'data': {
                'session_id': session_id,
                'session_name': session_name
            }
        })

        return {
            "success": True,
            "session_id": session_id,
            "session_name": session_name,
            "files_deleted": file_count,
            "jobs_deleted": job_count,
            "events_deleted": events_deleted
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session from database: {str(e)}"
        )


class BulkDeleteRequest(BaseModel):
    session_ids: List[str]


@router.post("/sessions/bulk-delete")
async def bulk_delete_sessions(
    request: BulkDeleteRequest,
    db: DBSession = Depends(get_db)
):
    """
    Bulk delete multiple sessions from the database.
    """
    from models import Job as JobModel, Event as EventModel
    from services.websocket import manager

    if not request.session_ids:
        return {"success": True, "deleted_count": 0}

    try:
        # Get session names before deletion for broadcast
        sessions_to_delete = db.query(SessionModel.id, SessionModel.name).filter(
            SessionModel.id.in_(request.session_ids)
        ).all()
        session_info = {s.id: s.name for s in sessions_to_delete}

        # Get all file IDs for these sessions
        file_ids = [f.id for f in db.query(FileModel.id).filter(
            FileModel.session_id.in_(request.session_ids)
        ).all()]

        # Delete associated events
        if file_ids:
            db.query(EventModel).filter(
                EventModel.file_id.in_(file_ids)
            ).delete(synchronize_session=False)

            # Delete jobs
            db.query(JobModel).filter(
                JobModel.file_id.in_(file_ids)
            ).delete(synchronize_session=False)

            # Delete files
            db.query(FileModel).filter(
                FileModel.session_id.in_(request.session_ids)
            ).delete(synchronize_session=False)

        # Delete sessions
        result = db.query(SessionModel).filter(
            SessionModel.id.in_(request.session_ids)
        ).delete(synchronize_session=False)

        db.commit()

        # Broadcast session deletion for each deleted session
        for session_id, session_name in session_info.items():
            await manager.broadcast({
                'type': 'session.deleted',
                'data': {
                    'session_id': session_id,
                    'session_name': session_name
                }
            })

        return {
            "success": True,
            "deleted_count": result,
            "message": f"Successfully deleted {result} sessions"
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail=f"Failed to bulk delete sessions: {str(e)}"
        )
