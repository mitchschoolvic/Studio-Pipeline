"""
Auto-Deletion Service

Automatically marks files for deletion based on their age.
"""
import logging
from datetime import datetime, timedelta
from typing import Tuple
from sqlalchemy.orm import Session

from models import File as FileModel, Setting
from repositories.file_repository import FileRepository
from services.websocket import manager as websocket_manager
from constants import SettingKeys

logger = logging.getLogger(__name__)


class AutoDeletionService:
    """Handles automatic marking of old files for deletion."""

    def __init__(self, db: Session):
        self.db = db
        self.file_repo = FileRepository(db)

    def mark_old_files_for_deletion(self) -> Tuple[int, bool]:
        """
        Mark files older than configured age for deletion.

        Returns:
            Tuple of (files_marked_count, enabled)
        """
        # Check if auto-deletion is enabled
        enabled_setting = self.db.query(Setting).filter(
            Setting.key == SettingKeys.AUTO_DELETE_ENABLED
        ).first()

        if not enabled_setting or enabled_setting.value.lower() != 'true':
            logger.debug("Auto-deletion is disabled")
            return (0, False)

        # Get age threshold in months
        age_setting = self.db.query(Setting).filter(
            Setting.key == SettingKeys.AUTO_DELETE_AGE_MONTHS
        ).first()

        if not age_setting:
            logger.warning("Auto-deletion age setting not found, using default of 12 months")
            age_months = 12
        else:
            try:
                age_months = int(age_setting.value)
            except ValueError:
                logger.error(f"Invalid age setting value: {age_setting.value}, using default of 12 months")
                age_months = 12

        # Calculate cutoff date
        cutoff_date = datetime.utcnow() - timedelta(days=age_months * 30)  # Approximate months as 30 days

        logger.info(f"Checking for files older than {age_months} months (before {cutoff_date.date()})")

        # Find files older than cutoff that are:
        # 1. COMPLETED state
        # 2. Not already marked for deletion
        # 3. Not already deleted
        # 4. Created before cutoff date
        old_files = self.db.query(FileModel).filter(
            FileModel.state == 'COMPLETED',
            FileModel.created_at < cutoff_date,
            FileModel.marked_for_deletion_at.is_(None),
            FileModel.deleted_at.is_(None)
        ).all()

        if not old_files:
            logger.info("No old files found to mark for deletion")
            return (0, True)

        logger.info(f"Found {len(old_files)} old files to mark for deletion")

        # Mark each file
        marked_count = 0
        for file in old_files:
            try:
                file.marked_for_deletion_at = datetime.utcnow()
                file.updated_at = datetime.utcnow()
                marked_count += 1

                # Broadcast WebSocket event
                try:
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(websocket_manager.broadcast({
                            'type': 'file_deletion_marked',
                            'file_id': file.id,
                            'session_id': file.session_id,
                            'marked_for_deletion_at': file.marked_for_deletion_at.isoformat()
                        }))
                except Exception as e:
                    logger.warning(f"Failed to broadcast auto-deletion event for file {file.id}: {e}")

            except Exception as e:
                logger.error(f"Failed to mark file {file.id} for deletion: {e}")

        self.db.commit()
        logger.info(f"Successfully marked {marked_count} old files for deletion")

        return (marked_count, True)
