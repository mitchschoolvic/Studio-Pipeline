"""
Dev Queue API Router

Provides endpoints for importing already-processed files back into the database
without running the full processing pipeline. Used for database recovery scenarios.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from database import get_db
from services.dev_import_service import DevImportService, DevImportSettings
import logging

logger = logging.getLogger(__name__)
# Trigger reload

router = APIRouter(tags=["dev-queue"])

# In-memory state for import job (simple approach - could use Redis for production)
_import_job_state: Dict[str, Any] = {
    "job_id": None,
    "status": "idle",
    "progress": {
        "sessions_processed": 0,
        "sessions_total": 0,
        "current_session": None,
        "current_step": None,
        "files_processed": 0,
        "files_total": 0,
        "errors": []
    }
}


class ScanRequest(BaseModel):
    folder_path: str


class ScanResponse(BaseModel):
    success: bool
    sessions: List[Dict[str, Any]]
    total_sessions: int
    total_size_gb: float
    error: Optional[str] = None


class ImportRequest(BaseModel):
    folder_path: str
    session_keys: List[str] = []  # Empty = import all
    settings: Dict[str, Any]  # Dev queue specific settings


class ImportResponse(BaseModel):
    job_id: str
    status: str
    total_sessions: int


class StatusResponse(BaseModel):
    job_id: Optional[str]
    status: str
    progress: Dict[str, Any]


class SettingsSaveRequest(BaseModel):
    settings: Dict[str, Any]


class DevQueueSettingsResponse(BaseModel):
    source_path: str
    analytics_export_path: str
    thumbnail_folder: str
    generate_mp3_if_missing: bool
    update_existing_records: bool


@router.post("/scan", response_model=ScanResponse)
async def scan_folder(request: ScanRequest, db: DBSession = Depends(get_db)):
    """
    Scan a folder for existing processed video files.
    
    Returns a list of discovered sessions with their files.
    Does not modify the database - this is a read-only operation.
    """
    try:
        service = DevImportService(db)
        result = service.scan_folder(request.folder_path)
        
        return ScanResponse(
            success=True,
            sessions=result["sessions"],
            total_sessions=result["total_sessions"],
            total_size_gb=result["total_size_gb"]
        )
    except FileNotFoundError as e:
        return ScanResponse(
            success=False,
            sessions=[],
            total_sessions=0,
            total_size_gb=0,
            error=f"Folder not found: {str(e)}"
        )
    except PermissionError as e:
        return ScanResponse(
            success=False,
            sessions=[],
            total_sessions=0,
            total_size_gb=0,
            error=f"Permission denied: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Scan error: {e}", exc_info=True)
        return ScanResponse(
            success=False,
            sessions=[],
            total_sessions=0,
            total_size_gb=0,
            error=str(e)
        )


@router.post("/import", response_model=ImportResponse)
async def import_sessions(
    request: ImportRequest,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_db)
):
    """
    Import selected sessions into the database.
    
    Creates Session, File, and FileAnalytics records.
    Generates thumbnails and exports MP3 for analytics.
    Runs as a background task with progress reporting.
    """
    global _import_job_state
    
    # Check if already running
    if _import_job_state["status"] == "running":
        raise HTTPException(
            status_code=409,
            detail="Import already in progress. Cancel or wait for completion."
        )
    
    import uuid
    job_id = str(uuid.uuid4())
    
    # Parse settings from request
    settings = DevImportSettings(
        analytics_export_path=request.settings.get("analytics_export_path", ""),
        thumbnail_folder=request.settings.get("thumbnail_folder", ""),
        generate_mp3_if_missing=request.settings.get("generate_mp3_if_missing", True),
        update_existing_records=request.settings.get("update_existing_records", True)
    )
    
    # First scan to get total count
    service = DevImportService(db)
    scan_result = service.scan_folder(request.folder_path)
    
    # Filter sessions if specific ones selected
    sessions_to_import = scan_result["sessions"]
    if request.session_keys:
        sessions_to_import = [
            s for s in sessions_to_import 
            if s["session_key"] in request.session_keys
        ]
    
    total_sessions = len(sessions_to_import)
    total_files = sum(s["total_files"] for s in sessions_to_import)
    
    # Initialize job state
    _import_job_state = {
        "job_id": job_id,
        "status": "running",
        "progress": {
            "sessions_processed": 0,
            "sessions_total": total_sessions,
            "current_session": None,
            "current_step": "initializing",
            "files_processed": 0,
            "files_total": total_files,
            "errors": []
        }
    }
    
    # Start background import
    background_tasks.add_task(
        _run_import_job,
        job_id,
        request.folder_path,
        sessions_to_import,
        settings
    )
    
    return ImportResponse(
        job_id=job_id,
        status="started",
        total_sessions=total_sessions
    )


async def _run_import_job(
    job_id: str,
    folder_path: str,
    sessions: List[Dict],
    settings: DevImportSettings
):
    """Background task to run the import job."""
    global _import_job_state
    
    from database import get_db
    
    try:
        # Get fresh DB session for background task
        db = next(get_db())
        service = DevImportService(db, settings)
        
        for i, session_data in enumerate(sessions):
            if _import_job_state["status"] == "cancelled":
                logger.info(f"Import job {job_id} cancelled")
                break
            
            _import_job_state["progress"]["current_session"] = session_data["session_key"]
            _import_job_state["progress"]["current_step"] = "importing_session"
            
            try:
                files_imported = await service.import_session(
                    session_data,
                    progress_callback=lambda step, detail: _update_progress(step, detail)
                )
                
                _import_job_state["progress"]["files_processed"] += files_imported
                
            except Exception as e:
                logger.error(f"Error importing session {session_data['session_key']}: {e}")
                _import_job_state["progress"]["errors"].append({
                    "session": session_data["session_key"],
                    "error": str(e)
                })
            
            _import_job_state["progress"]["sessions_processed"] = i + 1
        
        _import_job_state["status"] = "completed"
        _import_job_state["progress"]["current_step"] = "done"
        
    except Exception as e:
        logger.error(f"Import job {job_id} failed: {e}", exc_info=True)
        _import_job_state["status"] = "failed"
        _import_job_state["progress"]["errors"].append({
            "session": "general",
            "error": str(e)
        })
    finally:
        if 'db' in locals():
            db.close()


def _update_progress(step: str, detail: str = None):
    """Update progress state during import."""
    global _import_job_state
    _import_job_state["progress"]["current_step"] = step
    if detail:
        _import_job_state["progress"]["current_detail"] = detail


@router.get("/status", response_model=StatusResponse)
async def get_import_status():
    """Get the current status of the import job."""
    return StatusResponse(
        job_id=_import_job_state["job_id"],
        status=_import_job_state["status"],
        progress=_import_job_state["progress"]
    )


@router.post("/cancel")
async def cancel_import():
    """Cancel the current import job."""
    global _import_job_state
    
    if _import_job_state["status"] != "running":
        raise HTTPException(
            status_code=400,
            detail="No import job is currently running"
        )
    
    _import_job_state["status"] = "cancelled"
    return {"message": "Import cancellation requested"}


@router.post("/reset")
async def reset_import_state():
    """Reset the import state (for recovery from stuck states)."""
    global _import_job_state
    
    _import_job_state = {
        "job_id": None,
        "status": "idle",
        "progress": {
            "sessions_processed": 0,
            "sessions_total": 0,
            "current_session": None,
            "current_step": None,
            "files_processed": 0,
            "files_total": 0,
            "errors": []
        }
    }
    return {"message": "Import state reset"}


@router.get("/settings", response_model=DevQueueSettingsResponse)
async def get_dev_queue_settings(db: DBSession = Depends(get_db)):
    """Get dev queue specific settings."""
    from models import Setting
    
    def get_setting(key: str, default: str = "") -> str:
        setting = db.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting else default
    
    return DevQueueSettingsResponse(
        source_path=get_setting("dev_queue_source_path", ""),
        analytics_export_path=get_setting("dev_queue_analytics_export_path", ""),
        thumbnail_folder=get_setting("dev_queue_thumbnail_folder", ""),
        generate_mp3_if_missing=get_setting("dev_queue_generate_mp3", "true").lower() == "true",
        update_existing_records=get_setting("dev_queue_update_existing", "true").lower() == "true"
    )


@router.post("/settings")
async def save_dev_queue_settings(
    request: SettingsSaveRequest,
    db: DBSession = Depends(get_db)
):
    """Save dev queue specific settings."""
    from models import Setting
    from datetime import datetime
    
    settings_map = {
        "source_path": "dev_queue_source_path",
        "analytics_export_path": "dev_queue_analytics_export_path",
        "thumbnail_folder": "dev_queue_thumbnail_folder",
        "generate_mp3_if_missing": "dev_queue_generate_mp3",
        "update_existing_records": "dev_queue_update_existing"
    }
    
    for frontend_key, db_key in settings_map.items():
        if frontend_key in request.settings:
            value = request.settings[frontend_key]
            # Convert boolean to string for storage
            if isinstance(value, bool):
                value = "true" if value else "false"
            
            existing = db.query(Setting).filter(Setting.key == db_key).first()
            if existing:
                existing.value = str(value)
                existing.updated_at = datetime.utcnow()
            else:
                new_setting = Setting(key=db_key, value=str(value))
                db.add(new_setting)
    
    db.commit()
    return {"success": True, "message": "Settings saved"}
