from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from typing import List, Optional
from database import get_db
from repositories.file_repository import FileRepository
from services.file_cleanup_service import FileCleanupService
from services.ftp_deletion_service import FTPDeletionService
from services.websocket import manager as websocket_manager
from utils.error_handlers import handle_api_errors
from constants import HTTPStatus, FailureCategory
from schemas import File
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/files", response_model=List[File])
@handle_api_errors("Get files")
def get_files(
    state: str = None,
    session_id: str = None,
    is_program_output: bool = None,
    db: DBSession = Depends(get_db)
):
    """
    Get list of files with optional filtering

    Query parameters:
    - state: Filter by file state (DISCOVERED, COPYING, COPIED, etc.) - supports comma-separated
    - session_id: Filter by session ID
    - is_program_output: Filter by program output status (true = program files only)

    Raises:
        HTTPException: If database query fails
    """
    file_repo = FileRepository(db)
    return file_repo.get_filtered(state=state, session_id=session_id, is_program_output=is_program_output)


@router.get("/files/{file_id}", response_model=File)
@handle_api_errors("Get file")
def get_file(file_id: str, db: DBSession = Depends(get_db)):
    """
    Get a specific file with its jobs

    Args:
        file_id: Unique file identifier
        db: Database session

    Returns:
        File: File object with associated jobs

    Raises:
        HTTPException: If file not found or database query fails
    """
    file_repo = FileRepository(db)
    file = file_repo.get_with_jobs(file_id)

    if not file:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"File '{file_id}' not found")

    return file


@router.get("/files/{file_id}/processing-detail")
@handle_api_errors("Get file processing detail")
def get_file_processing_detail(file_id: str, db: DBSession = Depends(get_db)):
    """
    Get detailed processing substep information for a file.
    
    Returns the current substep and progress for each stage of the processing pipeline.
    This enables the UI to show detailed step indicators like:
    - Extract (completed/active/pending/skipped)
    - Boost (completed/active/pending/skipped)
    - Denoise (completed/active/pending/skipped)
    - Convert (completed/active/pending/skipped)
    - Remux (completed/active/pending/skipped)
    - Quad Split (completed/active/pending/skipped)
    
    Args:
        file_id: Unique file identifier
        db: Database session
        
    Returns:
        dict: Processing substep breakdown with status for each step
        
    Raises:
        HTTPException: If file not found
    """
    file_repo = FileRepository(db)
    file = file_repo.get_with_jobs(file_id)
    
    if not file:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"File '{file_id}' not found")
    
    # Define substep order
    substeps = ['extract', 'boost', 'denoise', 'mp3export', 'convert', 'remux', 'quadsplit']
    
    # Determine status for each substep
    substep_statuses = {}
    current_stage = file.processing_stage
    
    # If file is not in PROCESSING state, mark all as pending or skipped
    if file.state != 'PROCESSING':
        for substep in substeps:
            # Quad split is skipped for ISO files
            if substep == 'quadsplit' and not file.is_program_output:
                substep_statuses[substep] = 'skipped'
            elif file.state == 'COMPLETED':
                # If completed, check if it was processed or skipped
                if file.is_program_output:
                    substep_statuses[substep] = 'completed' if substep != 'quadsplit' else 'skipped'
                else:
                    substep_statuses[substep] = 'skipped'
            else:
                substep_statuses[substep] = 'pending'
    else:
        # File is actively processing
        current_stage_index = substeps.index(current_stage) if current_stage in substeps else -1
        
        for i, substep in enumerate(substeps):
            # Quad split is skipped for ISO files
            if substep == 'quadsplit' and not file.is_program_output:
                substep_statuses[substep] = 'skipped'
            elif i < current_stage_index:
                substep_statuses[substep] = 'completed'
            elif i == current_stage_index:
                substep_statuses[substep] = 'active'
            else:
                substep_statuses[substep] = 'pending'
    
    return {
        "file_id": file.id,
        "filename": file.filename,
        "state": file.state,
        "current_stage": current_stage,
        "stage_progress": file.processing_stage_progress,
        "detail": file.processing_detail,
        "substeps": substep_statuses
    }


@router.delete("/files/missing")
@handle_api_errors("Delete missing files")
def delete_missing_files(db: DBSession = Depends(get_db)):
    """
    Delete all files marked as missing from the database.
    Also deletes associated jobs, events, and empty sessions.

    Returns:
        dict: Number of files and sessions deleted

    Raises:
        HTTPException: If database operation fails
    """
    return FileCleanupService.delete_missing_files(db)


@router.put("/files/{file_id}/mark-for-deletion")
@handle_api_errors("Mark file for deletion")
async def mark_file_for_deletion(
    file_id: str,
    mark: bool,
    db: DBSession = Depends(get_db)
):
    """
    Mark or unmark a single file for deletion.

    Args:
        file_id: File UUID
        mark: True to mark for deletion, False to unmark
        db: Database session

    Returns:
        File: Updated file object

    Raises:
        HTTPException: If file not found or database operation fails
    """
    file_repo = FileRepository(db)
    file = file_repo.mark_for_deletion(file_id, mark)

    if not file:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"File '{file_id}' not found")

    db.commit()

    # Broadcast WebSocket event
    await websocket_manager.broadcast({
        'type': 'file_deletion_marked',
        'file_id': file.id,
        'session_id': file.session_id,
        'marked_for_deletion_at': file.marked_for_deletion_at.isoformat() if file.marked_for_deletion_at else None
    })

    return file


@router.put("/sessions/{session_id}/mark-for-deletion")
@handle_api_errors("Mark session for deletion")
async def mark_session_for_deletion(
    session_id: str,
    mark: bool,
    db: DBSession = Depends(get_db)
):
    """
    Mark or unmark all files in a session for deletion.

    Args:
        session_id: Session UUID
        mark: True to mark for deletion, False to unmark
        db: Database session

    Returns:
        dict: Updated file count and list of files

    Raises:
        HTTPException: If session not found or database operation fails
    """
    file_repo = FileRepository(db)
    updated_files = file_repo.mark_session_files_for_deletion(session_id, mark)

    if not updated_files:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"No files found for session '{session_id}'")

    db.commit()

    # Broadcast WebSocket events for each file
    for file in updated_files:
        await websocket_manager.broadcast({
            'type': 'file_deletion_marked',
            'file_id': file.id,
            'session_id': file.session_id,
            'marked_for_deletion_at': file.marked_for_deletion_at.isoformat() if file.marked_for_deletion_at else None
        })

    return {
        "session_id": session_id,
        "files_updated": len(updated_files),
        "marked": mark,
        "files": updated_files
    }


@router.delete("/sessions/{session_id}/delete-immediately")
@handle_api_errors("Delete session immediately")
async def delete_session_immediately(
    session_id: str,
    db: DBSession = Depends(get_db)
):
    """
    Immediately delete all files in a session from FTP server.
    This bypasses the 7-day waiting period for marked files.
    Database entries are retained with deleted_at timestamp.

    Args:
        session_id: Session UUID
        db: Database session

    Returns:
        dict: Deletion results with success and failure counts

    Raises:
        HTTPException: If session not found or deletion fails
    """
    file_repo = FileRepository(db)

    # Get all files in the session that are marked for deletion
    files = file_repo.get_by_session_id(session_id)
    marked_files = [f for f in files if f.marked_for_deletion_at and not f.deleted_at]

    if not marked_files:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail=f"No files marked for deletion in session '{session_id}'"
        )

    # Delete entire session folder from FTP (including all files)
    ftp_deletion_service = FTPDeletionService(db)
    success_count, failure_count = ftp_deletion_service.delete_session_folder_from_ftp(marked_files)

    db.commit()

    return {
        "session_id": session_id,
        "files_processed": len(marked_files),
        "success_count": success_count,
        "failure_count": failure_count
    }


@router.post("/files/{file_id}/reprocess")
@handle_api_errors("Reprocess file")
def reprocess_file(file_id: str, db: DBSession = Depends(get_db)):
    """
    Reset a file to DISCOVERED state and requeue all processing jobs.
    
    This will:
    - Reset file state to DISCOVERED
    - Clear any error messages
    - Create a new COPY job to restart the entire pipeline
    - Preserve the original file metadata
    
    Useful for files that failed processing or were processed before AI features were enabled.
    
    Args:
        file_id: Unique file identifier
        db: Database session
        
    Returns:
        dict: Success message with new job ID
        
    Raises:
        HTTPException: If file not found or cannot be reprocessed
    """
    from models import File, Job
    from utils.uuid_helper import generate_uuid
    from datetime import datetime
    
    file_repo = FileRepository(db)
    file = file_repo.get_with_jobs(file_id)
    
    if not file:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"File '{file_id}' not found")
    
    # Check if file is missing from FTP
    if file.is_missing:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Cannot reprocess file that is missing from FTP server"
        )
    
    # Reset file state
    old_state = file.state
    file.state = 'DISCOVERED'
    file.error_message = None
    file.processing_stage = None
    file.processing_stage_progress = 0
    file.processing_detail = None
    
    # Mark all existing jobs as cancelled
    for job in file.jobs:
        if job.state in ['QUEUED', 'RUNNING']:
            job.state = 'FAILED'
            job.error_message = 'Cancelled due to file reprocess request'
    
    # Create new COPY job to restart pipeline
    new_job = Job(
        id=generate_uuid(),
        file_id=file.id,
        kind='COPY',
        state='QUEUED',
        priority=1000,  # High priority for manual reprocess
        created_at=datetime.utcnow()
    )
    db.add(new_job)
    db.commit()
    
    logger.warning(f"🔄 File {file.filename} reset from {old_state} to DISCOVERED for reprocessing (Job: {new_job.id})")
    
    # Broadcast file state change
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(websocket_manager.send_file_update(
                file_id=str(file.id),
                state='DISCOVERED',
                session_id=str(file.session_id),
                progress_pct=0,
                progress_stage='Queued for reprocessing',
                filename=file.filename
            ))
        else:
            loop.run_until_complete(websocket_manager.send_file_update(
                file_id=str(file.id),
                state='DISCOVERED',
                session_id=str(file.session_id),
                progress_pct=0,
                progress_stage='Queued for reprocessing',
                filename=file.filename
            ))
    except Exception as e:
        logger.warning(f"Failed to broadcast reprocess event: {e}")
    
    return {
        "success": True,
        "file_id": file.id,
        "filename": file.filename,
        "old_state": old_state,
        "new_state": "DISCOVERED",
        "job_id": new_job.id,
        "message": f"File reset to DISCOVERED and queued for reprocessing"
    }


@router.get("/files/marked-for-deletion")
@handle_api_errors("Get files marked for deletion")
def get_marked_for_deletion(
    include_deleted: bool = False,
    db: DBSession = Depends(get_db)
):
    """
    Get all files marked for deletion.

    Query parameters:
    - include_deleted: If True, include files already deleted from FTP (default: False)

    Returns:
        List[File]: Files marked for deletion

    Raises:
        HTTPException: If database query fails
    """
    file_repo = FileRepository(db)
    return file_repo.get_marked_for_deletion(include_deleted=include_deleted)


class BulkDeleteFilesRequest(BaseModel):
    session_ids: List[str]


@router.post("/files/bulk-delete-immediately")
async def bulk_delete_files_immediately(
    request: BulkDeleteFilesRequest,
    db: DBSession = Depends(get_db)
):
    """
    Immediately delete all files in multiple sessions from FTP server.
    """
    if not request.session_ids:
        return {"success": True, "processed_count": 0}

    file_repo = FileRepository(db)
    ftp_deletion_service = FTPDeletionService(db)
    
    total_success = 0
    total_failure = 0
    processed_sessions = 0

    for session_id in request.session_ids:
        # Get all files in the session that are marked for deletion
        files = file_repo.get_by_session_id(session_id)
        marked_files = [f for f in files if f.marked_for_deletion_at and not f.deleted_at]

        if marked_files:
            success_count, failure_count = ftp_deletion_service.delete_session_folder_from_ftp(marked_files)
            total_success += success_count
            total_failure += failure_count
            processed_sessions += 1

    db.commit()

    return {
        "success": True,
        "processed_sessions": processed_sessions,
        "total_success": total_success,
        "total_failure": total_failure
    }


@router.get("/files/failed/summary")
@handle_api_errors("Get failed files summary")
def get_failed_files_summary(db: DBSession = Depends(get_db)):
    """
    Get summary of failed files grouped by failure category.
    
    Returns detailed information about failed files and recovery status,
    enabling the UI to show appropriate recovery indicators and messaging.
    
    Returns:
        dict with:
          - by_category: { 'FTP_CONNECTION': [...], 'PROCESSING_ERROR': [...] }
          - total_failed: int
          - ftp_connected: bool
          - queue_empty: bool (all other work done)
          - recovery_pending: bool (files waiting for FTP)
    """
    from models import File as FileModel, Job
    from services.reconciler import reconciler
    
    # Get all failed files
    failed_files = db.query(FileModel).filter(FileModel.state == 'FAILED').all()
    
    # Group by category
    by_category = {}
    for file in failed_files:
        cat = file.failure_category or 'UNKNOWN'
        if cat not in by_category:
            by_category[cat] = {
                'files': [],
                'label': FailureCategory.get_ui_label(FailureCategory(cat)) if cat != 'UNKNOWN' else 'Unknown Error',
                'recovery_hint': FailureCategory.get_recovery_hint(FailureCategory(cat)) if cat != 'UNKNOWN' else 'Will retry after other files complete',
                'is_recoverable': not FailureCategory.is_unrecoverable(FailureCategory(cat)) if cat != 'UNKNOWN' else True,
                'requires_ftp': FailureCategory.requires_ftp(FailureCategory(cat)) if cat != 'UNKNOWN' else False
            }
        by_category[cat]['files'].append({
            'id': file.id,
            'filename': file.filename,
            'session_id': file.session_id,
            'error_message': file.error_message,
            'failure_job_kind': file.failure_job_kind,
            'failed_at': file.failed_at.isoformat() if file.failed_at else None,
            'recovery_attempts': file.recovery_attempts or 0,
            'retry_after': file.retry_after.isoformat() if file.retry_after else None
        })
    
    # Check active jobs
    active_jobs = db.query(Job).filter(Job.state.in_(['QUEUED', 'RUNNING'])).count()
    
    # Get FTP status from reconciler
    ftp_connected = reconciler.last_ftp_connected or False
    
    # Check if any files are waiting for FTP
    ftp_waiting = any(
        file.failure_category in ['FTP_CONNECTION', 'FTP_TRANSFER', 'FTP_TIMEOUT']
        for file in failed_files
    )
    
    return {
        'by_category': by_category,
        'total_failed': len(failed_files),
        'ftp_connected': ftp_connected,
        'queue_empty': active_jobs == 0,
        'recovery_pending': ftp_waiting and not ftp_connected,
        'active_jobs': active_jobs
    }


@router.post("/files/{file_id}/retry-now")
@handle_api_errors("Retry failed file now")
def retry_file_now(file_id: str, db: DBSession = Depends(get_db)):
    """
    Immediately queue a recovery job for a failed file, bypassing backoff.
    
    This is useful when the user has fixed the underlying issue and wants
    to retry immediately without waiting for the recovery orchestrator.
    
    Args:
        file_id: Unique file identifier
        
    Returns:
        dict: Success message with new job ID
        
    Raises:
        HTTPException: If file not found or not in FAILED state
    """
    from models import File as FileModel, Job
    from utils.uuid_helper import generate_uuid
    from datetime import datetime
    
    file_repo = FileRepository(db)
    file = file_repo.get_with_jobs(file_id)
    
    if not file:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=f"File '{file_id}' not found")
    
    if file.state != 'FAILED':
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"File is not in FAILED state (current: {file.state})"
        )
    
    if file.is_missing:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Cannot retry file that is missing from FTP server"
        )
    
    # Check failure category for unrecoverable errors
    if file.failure_category:
        try:
            category = FailureCategory(file.failure_category)
            if FailureCategory.is_unrecoverable(category):
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"File cannot be automatically recovered: {FailureCategory.get_recovery_hint(category)}"
                )
        except ValueError:
            pass
    
    # Reset file state to checkpoint
    checkpoint = file.get_resumable_checkpoint()
    old_state = file.state
    file.state = checkpoint
    file.error_message = None
    file.retry_after = None  # Clear backoff
    file.recovery_attempts = (file.recovery_attempts or 0) + 1
    
    # Determine job kind from checkpoint
    if checkpoint == 'DISCOVERED':
        job_kind = 'COPY'
    elif checkpoint == 'COPIED':
        job_kind = 'PROCESS'
    elif checkpoint == 'PROCESSED':
        job_kind = 'ORGANIZE'
    else:
        job_kind = 'COPY'
    
    # Check for existing queued job
    existing_job = db.query(Job).filter(
        Job.file_id == file.id,
        Job.kind == job_kind,
        Job.state == 'QUEUED'
    ).first()
    
    if existing_job:
        return {
            "success": True,
            "file_id": file.id,
            "filename": file.filename,
            "job_id": existing_job.id,
            "message": "Recovery job already queued"
        }
    
    # Create new job with high priority
    new_job = Job(
        id=generate_uuid(),
        file_id=file.id,
        kind=job_kind,
        state='QUEUED',
        priority=500,  # High priority for manual retry
        retries=0,
        max_retries=3,
        created_at=datetime.utcnow()
    )
    db.add(new_job)
    db.commit()
    
    logger.info(f"🔄 Manual retry queued for {file.filename} ({job_kind} job, attempt {file.recovery_attempts})")
    
    # Broadcast state change
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(websocket_manager.send_file_update(
                file_id=str(file.id),
                state=checkpoint,
                session_id=str(file.session_id),
                progress_pct=0,
                progress_stage=f'Manual retry queued ({job_kind})',
                filename=file.filename
            ))
    except Exception as e:
        logger.warning(f"Failed to broadcast retry event: {e}")
    
    return {
        "success": True,
        "file_id": file.id,
        "filename": file.filename,
        "old_state": old_state,
        "new_state": checkpoint,
        "job_id": new_job.id,
        "job_kind": job_kind,
        "recovery_attempt": file.recovery_attempts,
        "message": f"Recovery job queued: {job_kind}"
    }
