"""
Session repository for session-specific data access operations.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from models import Session as SessionModel, File as FileModel
from .base_repository import BaseRepository


class SessionRepository(BaseRepository[SessionModel]):
    """Repository for Session model operations."""

    def __init__(self, db: Session):
        super().__init__(db, SessionModel)

    def get_latest(self) -> Optional[SessionModel]:
        """
        Get the most recently discovered session.

        Returns:
            Latest session or None if no sessions exist
        """
        return self.db.query(self.model).order_by(
            self.model.discovered_at.desc()
        ).first()

    def get_with_files(self, session_id: str) -> Optional[SessionModel]:
        """
        Get a session with its files eagerly loaded.

        Args:
            session_id: Session UUID

        Returns:
            Session instance with files, or None if not found
        """
        return self.db.query(self.model).options(
            joinedload(self.model.files)
        ).filter(self.model.id == session_id).first()

    def get_all_with_files(self) -> List[SessionModel]:
        """
        Get all sessions with their files eagerly loaded.

        Returns:
            List of all sessions with files
        """
        return self.db.query(self.model).options(
            joinedload(self.model.files)
        ).all()

    def get_empty_sessions(self) -> List[SessionModel]:
        """
        Find sessions that have no files.

        Returns:
            List of sessions with zero files
        """
        return self.db.query(self.model).filter(
            self.model.file_count == 0
        ).all()

    def get_by_recording_info(
        self,
        name: str,
        recording_date: str,
        recording_time: str
    ) -> Optional[SessionModel]:
        """
        Find session by its unique recording information.

        Args:
            name: Session name
            recording_date: Recording date (YYYY-MM-DD)
            recording_time: Recording time (HH:MM:SS)

        Returns:
            Session instance or None if not found
        """
        return self.db.query(self.model).filter(
            self.model.name == name,
            self.model.recording_date == recording_date,
            self.model.recording_time == recording_time
        ).first()

    def update_file_count_and_size(self, session_id: str) -> Optional[SessionModel]:
        """
        Recalculate and update file_count and total_size for a session.

        Args:
            session_id: Session UUID

        Returns:
            Updated session instance, or None if not found
        """
        session = self.get_by_id(session_id)
        if not session:
            return None

        # Aggregate file count and total size
        result = self.db.query(
            func.count(FileModel.id).label('count'),
            func.coalesce(func.sum(FileModel.size), 0).label('total_size')
        ).filter(
            FileModel.session_id == session_id
        ).first()

        session.file_count = result.count
        session.total_size = result.total_size
        self.db.flush()

        return session

    def delete_empty_sessions(self) -> int:
        """
        Delete all sessions that have no files.

        Returns:
            Number of sessions deleted
        """
        empty_sessions = self.get_empty_sessions()
        count = len(empty_sessions)

        for session in empty_sessions:
            self.delete(session)

        return count

    def get_stats(self) -> Dict[str, Any]:
        """
        Get overall statistics for all sessions.

        Returns:
            Dictionary with total sessions, files, and total size
        """
        session_count = self.count()

        file_stats = self.db.query(
            func.count(FileModel.id).label('total_files'),
            func.coalesce(func.sum(FileModel.size), 0).label('total_size')
        ).first()

        return {
            "total_sessions": session_count,
            "total_files": file_stats.total_files if file_stats else 0,
            "total_size": file_stats.total_size if file_stats else 0
        }
