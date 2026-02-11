"""
File repository for file-specific data access operations.

Now supports Specification Pattern for complex queries.
"""

from typing import List, Optional
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta

from models import File as FileModel
from .base_repository import BaseRepository
from .specifications import Specification


class FileRepository(BaseRepository[FileModel]):
    """Repository for File model operations."""

    def __init__(self, db: Session):
        super().__init__(db, FileModel)

    def get_by_state(self, state: str) -> List[FileModel]:
        """
        Get all files with a specific state.

        Args:
            state: File state (DISCOVERED, COPYING, etc.)

        Returns:
            List of files in the specified state
        """
        return self.db.query(self.model).filter(
            self.model.state == state
        ).all()

    def get_by_session_id(self, session_id: str) -> List[FileModel]:
        """
        Get all files for a specific session.

        Args:
            session_id: Session UUID

        Returns:
            List of files in the session
        """
        return self.db.query(self.model).filter(
            self.model.session_id == session_id
        ).all()

    def get_with_jobs(self, file_id: str) -> Optional[FileModel]:
        """
        Get a file with its related jobs eagerly loaded.

        Args:
            file_id: File UUID

        Returns:
            File instance with jobs, or None if not found
        """
        return self.db.query(self.model).options(
            joinedload(self.model.jobs)
        ).filter(self.model.id == file_id).first()

    def find_missing(self) -> List[FileModel]:
        """
        Find all files marked as missing.

        Returns:
            List of missing files
        """
        return self.db.query(self.model).filter(
            self.model.is_missing == True
        ).all()

    def get_filtered(
        self,
        state: Optional[str] = None,
        session_id: Optional[str] = None,
        is_missing: Optional[bool] = None,
        is_program_output: Optional[bool] = None
    ) -> List[FileModel]:
        """
        Get files with optional filtering.

        Args:
            state: Filter by file state (supports comma-separated for multiple states,
                   e.g., "COMPLETED,PROCESSED")
            session_id: Filter by session ID
            is_missing: Filter by missing status
            is_program_output: Filter by program output status (True = program files only)

        Returns:
            List of matching files
        """
        query = self.db.query(self.model)

        if state:
            # Support comma-separated states for IN queries
            states = [s.strip() for s in state.split(',')]
            if len(states) == 1:
                query = query.filter(self.model.state == states[0])
            else:
                query = query.filter(self.model.state.in_(states))
        if session_id:
            query = query.filter(self.model.session_id == session_id)
        if is_missing is not None:
            query = query.filter(self.model.is_missing == is_missing)
        if is_program_output is not None:
            query = query.filter(self.model.is_program_output == is_program_output)

        return query.all()

    def mark_as_missing(self, file_id: str) -> Optional[FileModel]:
        """
        Mark a file as missing.

        Args:
            file_id: File UUID

        Returns:
            Updated file instance, or None if not found
        """
        file = self.get_by_id(file_id)
        if file:
            file.is_missing = True
            file.missing_since = datetime.utcnow()
            self.db.flush()
        return file

    def delete_missing_files(self) -> int:
        """
        Delete all files marked as missing.

        Returns:
            Number of files deleted
        """
        missing_files = self.find_missing()
        count = len(missing_files)

        for file in missing_files:
            self.delete(file)

        return count

    def update_state(self, file_id: str, new_state: str) -> Optional[FileModel]:
        """
        Update the state of a file.

        Args:
            file_id: File UUID
            new_state: New state value

        Returns:
            Updated file instance, or None if not found
        """
        file = self.get_by_id(file_id)
        if file:
            file.state = new_state
            file.updated_at = datetime.utcnow()
            self.db.flush()
        return file

    def count_by_state(self, state: str) -> int:
        """
        Count files in a specific state.

        Args:
            state: File state

        Returns:
            Number of files in the state
        """
        return self.db.query(self.model).filter(
            self.model.state == state
        ).count()

    def get_by_remote_path(self, path_remote: str) -> Optional[FileModel]:
        """
        Get file by its remote FTP path.

        Args:
            path_remote: Remote FTP path

        Returns:
            File instance or None if not found
        """
        return self.db.query(self.model).filter(
            self.model.path_remote == path_remote
        ).first()

    def find(self, spec: Specification[FileModel]) -> List[FileModel]:
        """
        Find files using a Specification.

        This implements the Specification Pattern, allowing complex queries
        to be built using composable specifications.

        Args:
            spec: Specification to match files against

        Returns:
            List of files matching the specification

        Example:
            # Simple specification
            spec = FilesByStateSpec('processing')
            files = file_repo.find(spec)

            # Composed specifications
            spec = FilesByStateSpec('completed') & FilesCreatedAfterSpec(
                datetime.now() - timedelta(days=7)
            )
            recent_completed_files = file_repo.find(spec)
        """
        query = self.db.query(self.model)
        sql_filter = spec.to_sql_filter()
        return query.filter(sql_filter).all()

    def find_one(self, spec: Specification[FileModel]) -> Optional[FileModel]:
        """
        Find first file matching a Specification.

        Args:
            spec: Specification to match file against

        Returns:
            First file matching the specification, or None
        """
        query = self.db.query(self.model)
        sql_filter = spec.to_sql_filter()
        return query.filter(sql_filter).first()

    def count(self, spec: Specification[FileModel]) -> int:
        """
        Count files matching a Specification.

        Args:
            spec: Specification to match files against

        Returns:
            Number of files matching the specification
        """
        query = self.db.query(self.model)
        sql_filter = spec.to_sql_filter()
        return query.filter(sql_filter).count()

    # Deletion tracking methods

    def mark_for_deletion(self, file_id: str, mark: bool) -> Optional[FileModel]:
        """
        Mark or unmark a file for deletion.

        Args:
            file_id: File UUID
            mark: True to mark for deletion, False to unmark

        Returns:
            Updated file instance, or None if not found
        """
        file = self.get_by_id(file_id)
        if file:
            if mark:
                file.marked_for_deletion_at = datetime.utcnow()
            else:
                # Unmark - clear all deletion fields
                file.marked_for_deletion_at = None
                file.deletion_error = None
                file.deletion_attempted_at = None
            file.updated_at = datetime.utcnow()
            self.db.flush()
        return file

    def mark_session_files_for_deletion(self, session_id: str, mark: bool) -> List[FileModel]:
        """
        Mark or unmark all files in a session for deletion.

        Args:
            session_id: Session UUID
            mark: True to mark for deletion, False to unmark

        Returns:
            List of updated files
        """
        files = self.get_by_session_id(session_id)
        updated_files = []

        for file in files:
            if mark:
                file.marked_for_deletion_at = datetime.utcnow()
            else:
                # Unmark - clear all deletion fields
                file.marked_for_deletion_at = None
                file.deletion_error = None
                file.deletion_attempted_at = None
            file.updated_at = datetime.utcnow()
            updated_files.append(file)

        self.db.flush()
        return updated_files

    def get_marked_for_deletion(self, include_deleted: bool = False) -> List[FileModel]:
        """
        Get all files marked for deletion.

        Args:
            include_deleted: If True, include files already deleted from FTP

        Returns:
            List of files marked for deletion
        """
        query = self.db.query(self.model).filter(
            self.model.marked_for_deletion_at.isnot(None)
        )

        if not include_deleted:
            query = query.filter(self.model.deleted_at.is_(None))

        return query.all()

    def get_files_ready_for_deletion(self, days: int = 7) -> List[FileModel]:
        """
        Get files marked for deletion for >= specified days and not yet deleted.

        Args:
            days: Minimum number of days since marked

        Returns:
            List of files ready for deletion
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        return self.db.query(self.model).filter(
            self.model.marked_for_deletion_at.isnot(None),
            self.model.marked_for_deletion_at < cutoff,
            self.model.deleted_at.is_(None)
        ).all()

    def record_deletion_success(self, file_id: str) -> Optional[FileModel]:
        """
        Mark file as successfully deleted from FTP.

        Args:
            file_id: File UUID

        Returns:
            Updated file instance, or None if not found
        """
        file = self.get_by_id(file_id)
        if file:
            file.deleted_at = datetime.utcnow()
            file.deletion_error = None  # Clear any previous errors
            file.updated_at = datetime.utcnow()
            self.db.flush()
        return file

    def record_deletion_failure(self, file_id: str, error: str) -> Optional[FileModel]:
        """
        Record FTP deletion failure.

        Args:
            file_id: File UUID
            error: Error message

        Returns:
            Updated file instance, or None if not found
        """
        file = self.get_by_id(file_id)
        if file:
            file.deletion_attempted_at = datetime.utcnow()
            file.deletion_error = error
            file.updated_at = datetime.utcnow()
            self.db.flush()
        return file
