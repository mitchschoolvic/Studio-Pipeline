"""
File Cleanup Service

Handles business logic for file cleanup operations including deleting
missing files and cleaning up empty sessions.

Extracted from files.py to follow Single Responsibility Principle
and Open/Closed Principle (strategy pattern ready for extension).
"""

from typing import Dict, Any, Set
from sqlalchemy.orm import Session
import logging

from repositories.file_repository import FileRepository
from repositories.session_repository import SessionRepository
from repositories.job_repository import JobRepository
from models import Event as EventModel, File as FileModel

logger = logging.getLogger(__name__)


class FileCleanupService:
    """Service for file cleanup operations."""

    @staticmethod
    def delete_missing_files(db: Session) -> Dict[str, Any]:
        """
        Delete all files marked as missing, along with their associated
        jobs, events, and empty sessions.

        Args:
            db: Database session

        Returns:
            Dictionary containing:
                - deleted: Number of files deleted
                - sessions_deleted: Number of sessions deleted
                - message: Summary message
        """
        file_repo = FileRepository(db)
        session_repo = SessionRepository(db)

        # Find all missing files
        missing_files = file_repo.find_missing()
        files_count = len(missing_files)

        if files_count == 0:
            return {
                "deleted": 0,
                "sessions_deleted": 0,
                "message": "No missing files found"
            }

        # Track affected sessions
        affected_session_ids = FileCleanupService._clear_file_references(
            db, missing_files
        )

        # Delete associated resources
        FileCleanupService._delete_associated_resources(db, missing_files)

        # Delete the files themselves
        FileCleanupService._delete_files(db, missing_files)

        # Clean up empty sessions
        sessions_deleted = FileCleanupService._cleanup_empty_sessions(
            db, session_repo, affected_session_ids
        )

        db.commit()

        logger.info(
            f"Deleted {files_count} missing files and "
            f"{sessions_deleted} empty sessions"
        )

        return {
            "deleted": files_count,
            "sessions_deleted": sessions_deleted,
            "message": (
                f"Deleted {files_count} missing file(s) and "
                f"{sessions_deleted} empty session(s)"
            )
        }

    @staticmethod
    def _clear_file_references(
        db: Session,
        missing_files: list
    ) -> Set[str]:
        """
        Clear parent_file_id references to prevent foreign key constraint errors.

        Args:
            db: Database session
            missing_files: List of files to be deleted

        Returns:
            Set of affected session IDs
        """
        affected_session_ids = set()

        for file in missing_files:
            affected_session_ids.add(file.session_id)
            # Clear self-referential foreign key
            db.query(FileModel).filter(
                FileModel.parent_file_id == file.id
            ).update({"parent_file_id": None})

        db.commit()
        return affected_session_ids

    @staticmethod
    def _delete_associated_resources(db: Session, missing_files: list) -> None:
        """
        Delete jobs and events associated with files being deleted.

        Args:
            db: Database session
            missing_files: List of files being deleted
        """
        job_repo = JobRepository(db)

        for file in missing_files:
            # Delete jobs
            jobs = job_repo.get_filtered(file_id=file.id)
            for job in jobs:
                job_repo.delete(job)

            # Delete events
            db.query(EventModel).filter(
                EventModel.file_id == file.id
            ).delete()

        db.commit()

    @staticmethod
    def _delete_files(db: Session, missing_files: list) -> None:
        """
        Delete the files themselves.

        Args:
            db: Database session
            missing_files: List of files to delete
        """
        for file in missing_files:
            db.delete(file)

        db.commit()

    @staticmethod
    def _cleanup_empty_sessions(
        db: Session,
        session_repo: SessionRepository,
        affected_session_ids: Set[str]
    ) -> int:
        """
        Delete sessions that have no remaining files.

        Args:
            db: Database session
            session_repo: Session repository instance
            affected_session_ids: Set of session IDs to check

        Returns:
            Number of sessions deleted
        """
        sessions_deleted = 0

        for session_id in affected_session_ids:
            session = session_repo.get_by_id(session_id)
            if session:
                # Count remaining files
                remaining_files = db.query(FileModel).filter(
                    FileModel.session_id == session_id
                ).count()

                if remaining_files == 0:
                    session_repo.delete(session)
                    sessions_deleted += 1

        db.commit()
        return sessions_deleted
