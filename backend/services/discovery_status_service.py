"""
Discovery Status Service

Handles business logic for retrieving discovery status information.
Extracted from discovery.py to follow Single Responsibility Principle.
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
import logging

from repositories.session_repository import SessionRepository
from services.ftp_config_service import FTPConfigService

logger = logging.getLogger(__name__)


class DiscoveryStatusService:
    """Service for retrieving discovery status information."""

    @staticmethod
    def get_status(db: Session) -> Dict[str, Any]:
        """
        Get comprehensive discovery status including FTP config and last discovery.

        Args:
            db: Database session

        Returns:
            Dictionary containing:
                - ftp_configured: bool
                - ftp_host: str or None
                - ftp_port: int
                - ftp_user: str
                - ftp_path: str
                - last_discovery: ISO timestamp or None
                - status: str (e.g., "ready")
        """
        # Get FTP configuration status
        ftp_status = FTPConfigService.get_ftp_status(db)

        # Get latest session using repository
        session_repo = SessionRepository(db)
        latest_session = session_repo.get_latest()

        return {
            **ftp_status,
            "last_discovery": latest_session.discovered_at.isoformat() if latest_session else None,
            "status": "ready"
        }
