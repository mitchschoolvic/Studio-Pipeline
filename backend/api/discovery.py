"""
Discovery API endpoints
"""
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from services.interfaces import IDiscoveryService
from services.discovery_status_service import DiscoveryStatusService
from services.discovery_diagnostic_service import DiscoveryDiagnosticService
from services.ftp_config_service import FTPConfigService
from services.reconciler import get_reconciler_status
from dependencies import get_discovery_service
from utils.error_handlers import handle_api_errors
from pydantic import BaseModel
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class DiscoveryResult(BaseModel):
    """Discovery result response"""
    sessions_discovered: int
    files_discovered: int
    message: str


class DiscoveryRequest(BaseModel):
    """Discovery request with optional FTP override"""
    ftp_host: str | None = None
    ftp_port: int | None = None
    ftp_path: str | None = None


# Removed: _run_discovery function is now handled by DiscoveryOrchestrator


@router.post("/scan", response_model=DiscoveryResult)
@handle_api_errors("Discovery scan")
async def trigger_discovery(
    request: DiscoveryRequest | None = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    discovery_service: IDiscoveryService = Depends(get_discovery_service)
):
    """
    Trigger FTP discovery scan

    This endpoint immediately triggers a discovery scan of the FTP server.
    The scan runs in the background and returns immediately.

    Args:
        request: Optional FTP connection override parameters
        background_tasks: FastAPI background tasks
        db: Database session
        discovery_service: Discovery service (injected)

    Returns:
        DiscoveryResult with count of sessions/files to be discovered

    Raises:
        HTTPException: If FTP configuration is invalid or missing

    Note: This is a manual trigger. The normal flow uses the discovery worker
    which runs automatically on a schedule.
    """
    result = await discovery_service.trigger_scan(db, request, background_tasks)
    return DiscoveryResult(
        sessions_discovered=result.sessions_discovered,
        files_discovered=result.files_discovered,
        message=result.message
    )


@router.get("/status", response_model=dict)
@handle_api_errors("Get discovery status")
def get_discovery_status(db: Session = Depends(get_db)):
    """
    Get discovery service status

    Returns information about the FTP configuration, last discovery run,
    and automatic scan status.

    Raises:
        HTTPException: If database query fails
    """
    status = DiscoveryStatusService.get_status(db)
    
    # Add reconciler (automatic scan) status
    reconciler_status = get_reconciler_status()
    status['auto_scan'] = {
        'enabled': reconciler_status['running'],
        'interval_seconds': reconciler_status['ftp_check_interval'],
        'last_scan': reconciler_status['last_ftp_scan'],
        'ftp_connected': reconciler_status['ftp_connected'],
    }
    
    return status


@router.post("/verify", response_model=DiscoveryResult)
@handle_api_errors("Discovery verification")
async def verify_discovery(
    request: DiscoveryRequest | None = None,
    db: Session = Depends(get_db),
    discovery_service: IDiscoveryService = Depends(get_discovery_service)
):
    """
    Run discovery immediately and return counts.

    This endpoint runs discovery synchronously (awaits completion) so the
    caller receives immediate feedback about how many files were found/added.

    Args:
        request: Optional FTP connection override parameters
        db: Database session
        discovery_service: Discovery service (injected)

    Returns:
        DiscoveryResult with actual counts of discovered files

    Raises:
        HTTPException: If FTP configuration is invalid or discovery fails
    """
    result = await discovery_service.verify_scan(db, request)
    return DiscoveryResult(
        sessions_discovered=result.sessions_discovered,
        files_discovered=result.files_discovered,
        message=result.message
    )


@router.get("/diagnose", response_model=Dict[str, Any])
@handle_api_errors("Discovery diagnostic")
async def run_diagnostic(db: Session = Depends(get_db)):
    """
    Run a diagnostic scan of the FTP server.
    
    Returns detailed information about what files are found and why
    they are or aren't being added to sessions. Useful for troubleshooting
    discovery issues.
    
    Returns:
        Dictionary containing:
            - success: bool
            - source_path: FTP source path
            - excluded_folders: List of excluded folder names
            - directories: List of directories with exclusion status
            - files: List of files with status codes
            - summary: Counts by status
            
    Status codes:
        - added: File would be added to a session
        - exists: File already exists in database
        - excluded: File is in an excluded folder
        - hidden: Hidden file (starts with . or $)
        - system: System folder ($RECYCLE.BIN, etc.)
        - wrong_extension: Not .mp4 or .mov
        - too_small: Below 5MB minimum size
    """
    # Get FTP config
    ftp_config = FTPConfigService.get_ftp_config(db)
    
    if not ftp_config or not ftp_config.get('host'):
        raise HTTPException(
            status_code=400, 
            detail="FTP not configured. Please configure FTP settings first."
        )
    
    diagnostic_service = DiscoveryDiagnosticService(db, ftp_config)
    return await diagnostic_service.run_diagnostic()
