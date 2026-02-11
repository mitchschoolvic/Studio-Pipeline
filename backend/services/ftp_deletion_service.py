"""
FTP Deletion Service

Handles deletion of files from ATEM FTP server for files marked for deletion.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Tuple
from ftplib import FTP, error_perm, error_temp
from sqlalchemy.orm import Session

from models import File as FileModel
from repositories.file_repository import FileRepository
from services.websocket import manager as websocket_manager
from services.ftp_config_service import FTPConfigService

logger = logging.getLogger(__name__)


class FTPDeletionService:
    """Handles deletion of files from ATEM FTP server."""

    def __init__(self, db: Session):
        self.db = db
        self.file_repo = FileRepository(db)

    def delete_files_marked_for_days(self, days: int = 7) -> Tuple[int, int]:
        """
        Delete session folders for files marked for deletion for >= specified days.
        Groups files by session and deletes entire session folders.

        Args:
            days: Minimum number of days since marked for deletion

        Returns:
            Tuple of (success_count, failure_count)
        """
        files_to_delete = self.file_repo.get_files_ready_for_deletion(days=days)

        if not files_to_delete:
            logger.info("No files ready for deletion")
            return (0, 0)

        logger.info(f"Found {len(files_to_delete)} files ready for deletion (marked {days}+ days ago)")

        # Group files by session_id
        sessions_to_delete = {}
        for file in files_to_delete:
            if file.session_id not in sessions_to_delete:
                sessions_to_delete[file.session_id] = []
            sessions_to_delete[file.session_id].append(file)

        logger.info(f"Grouped into {len(sessions_to_delete)} session(s) to delete")

        total_success = 0
        total_failure = 0

        # Delete each session folder
        for session_id, session_files in sessions_to_delete.items():
            logger.info(f"Deleting session folder for session {session_id} ({len(session_files)} files)")
            success_count, failure_count = self.delete_session_folder_from_ftp(session_files)
            total_success += success_count
            total_failure += failure_count

        logger.info(f"Deletion complete: {total_success} succeeded, {total_failure} failed")
        return (total_success, total_failure)

    def _delete_file_from_ftp(self, file: FileModel):
        """
        Delete a single file from FTP server.

        Args:
            file: File model instance to delete

        Raises:
            Exception: If deletion fails and should be retried
        """
        if not file.path_remote:
            logger.warning(f"File {file.id} has no remote path, marking as deleted anyway")
            self._mark_deleted(file)
            return

        # Check if already deleted/missing
        if file.is_missing:
            logger.info(f"File {file.id} already missing from FTP, marking as deleted")
            self._mark_deleted(file)
            return

        # Get FTP config
        try:
            ftp_config = FTPConfigService.get_ftp_config(self.db)
        except Exception as e:
            logger.error(f"Failed to get FTP config: {e}")
            self._mark_failed(file, f"Configuration error: {str(e)}")
            return

        ftp = None
        try:
            # Connect to FTP
            ftp = FTP()
            ftp.connect(ftp_config['host'], ftp_config['port'])
            ftp.login(ftp_config['username'], ftp_config['password'])

            try:
                # Attempt deletion
                ftp.delete(file.path_remote)
                logger.info(f"Successfully deleted {file.path_remote} from FTP")
                self._mark_deleted(file)

            except error_perm as e:
                error_msg = str(e)

                # File not found = already deleted
                if "550" in error_msg or "No such file" in error_msg.lower():
                    logger.info(f"File {file.path_remote} not found on FTP, marking as deleted")
                    self._mark_deleted(file)

                # Permission denied
                elif "permission denied" in error_msg.lower() or "553" in error_msg:
                    logger.error(f"Permission denied deleting {file.path_remote}: {error_msg}")
                    self._mark_failed(file, f"Permission denied: {error_msg}")

                # File in use or locked
                elif "in use" in error_msg.lower() or "locked" in error_msg.lower() or "busy" in error_msg.lower():
                    logger.warning(f"File in use: {file.path_remote}: {error_msg}")
                    self._mark_failed(file, f"File in use: {error_msg}")

                else:
                    logger.error(f"FTP error deleting {file.path_remote}: {error_msg}")
                    self._mark_failed(file, f"FTP error: {error_msg}")

            except error_temp as e:
                # Temporary error - retry later
                error_msg = str(e)
                logger.warning(f"Temporary FTP error deleting {file.path_remote}: {error_msg}")
                self._mark_failed(file, f"Temporary error: {error_msg}")

        except Exception as e:
            # Connection or other errors
            error_msg = str(e)
            logger.error(f"Failed to connect to FTP or delete {file.path_remote}: {error_msg}")
            self._mark_failed(file, f"Connection error: {error_msg}")

        finally:
            if ftp:
                try:
                    ftp.quit()
                except:
                    pass

    def _mark_deleted(self, file: FileModel):
        """
        Mark file as successfully deleted.

        Args:
            file: File model instance
        """
        self.file_repo.record_deletion_success(file.id)
        self.db.commit()

        # Broadcast WebSocket event
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(websocket_manager.broadcast({
                    'type': 'file_deleted',
                    'file_id': file.id,
                    'session_id': file.session_id,
                    'deleted_at': datetime.utcnow().isoformat()
                }))
            else:
                loop.run_until_complete(websocket_manager.broadcast({
                    'type': 'file_deleted',
                    'file_id': file.id,
                    'session_id': file.session_id,
                    'deleted_at': datetime.utcnow().isoformat()
                }))
        except Exception as e:
            logger.warning(f"Failed to broadcast deletion event: {e}")

    def _mark_failed(self, file: FileModel, error: str):
        """
        Mark deletion attempt as failed.

        Args:
            file: File model instance
            error: Error message
        """
        self.file_repo.record_deletion_failure(file.id, error)
        self.db.commit()

        # Broadcast WebSocket event
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(websocket_manager.broadcast({
                    'type': 'file_deletion_failed',
                    'file_id': file.id,
                    'session_id': file.session_id,
                    'error': error,
                    'attempted_at': datetime.utcnow().isoformat()
                }))
            else:
                loop.run_until_complete(websocket_manager.broadcast({
                    'type': 'file_deletion_failed',
                    'file_id': file.id,
                    'session_id': file.session_id,
                    'error': error,
                    'attempted_at': datetime.utcnow().isoformat()
                }))
        except Exception as e:
            logger.warning(f"Failed to broadcast deletion failure event: {e}")

    def delete_session_folder_from_ftp(self, session_files: List[FileModel]) -> Tuple[int, int]:
        """
        Delete entire session folder from FTP server along with all files.

        Args:
            session_files: List of files in the session to delete

        Returns:
            Tuple of (success_count, failure_count)
        """
        if not session_files:
            logger.warning("No files provided for folder deletion")
            return (0, 0)

        # Get the folder path from the first file
        folder_path = None
        for file in session_files:
            if file.folder_path:
                folder_path = file.folder_path
                break

        if not folder_path:
            logger.warning("No folder path found, falling back to individual file deletion")
            # Fall back to deleting individual files
            success_count = 0
            failure_count = 0
            for file in session_files:
                try:
                    self._delete_file_from_ftp(file)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete file {file.id}: {str(e)}")
                    failure_count += 1
            return (success_count, failure_count)

        # Get FTP config
        try:
            ftp_config = FTPConfigService.get_ftp_config(self.db)
        except Exception as e:
            logger.error(f"Failed to get FTP config: {e}")
            # Mark all files as failed
            for file in session_files:
                self._mark_failed(file, f"Configuration error: {str(e)}")
            return (0, len(session_files))

        ftp = None
        try:
            # Connect to FTP
            ftp = FTP()
            ftp.connect(ftp_config['host'], ftp_config['port'])
            ftp.login(ftp_config['username'], ftp_config['password'])

            # Delete the entire folder recursively
            try:
                self._delete_ftp_folder_recursive(ftp, folder_path)
                logger.info(f"Successfully deleted folder {folder_path} from FTP")

                # Mark all files as deleted
                success_count = 0
                for file in session_files:
                    try:
                        self._mark_deleted(file)
                        success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to mark file {file.id} as deleted: {str(e)}")

                return (success_count, len(session_files) - success_count)

            except error_perm as e:
                error_msg = str(e)

                # Folder not found = already deleted
                if "550" in error_msg or "No such file" in error_msg.lower():
                    logger.info(f"Folder {folder_path} not found on FTP, marking all files as deleted")
                    success_count = 0
                    for file in session_files:
                        try:
                            self._mark_deleted(file)
                            success_count += 1
                        except Exception as e:
                            logger.error(f"Failed to mark file {file.id} as deleted: {str(e)}")
                    return (success_count, len(session_files) - success_count)
                else:
                    logger.error(f"FTP error deleting folder {folder_path}: {error_msg}")
                    for file in session_files:
                        self._mark_failed(file, f"Folder deletion error: {error_msg}")
                    return (0, len(session_files))

            except error_temp as e:
                error_msg = str(e)
                logger.warning(f"Temporary FTP error deleting folder {folder_path}: {error_msg}")
                for file in session_files:
                    self._mark_failed(file, f"Temporary error: {error_msg}")
                return (0, len(session_files))

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to connect to FTP or delete folder {folder_path}: {error_msg}")
            for file in session_files:
                self._mark_failed(file, f"Connection error: {error_msg}")
            return (0, len(session_files))

        finally:
            if ftp:
                try:
                    ftp.quit()
                except:
                    pass

    def _delete_ftp_folder_recursive(self, ftp: FTP, folder_path: str):
        """
        Recursively delete a folder and all its contents from FTP.

        Args:
            ftp: Active FTP connection
            folder_path: Path to the folder to delete
        """
        try:
            # Try to change to the directory
            ftp.cwd(folder_path)
        except error_perm:
            # If we can't change to it, it might not exist or might be a file
            logger.warning(f"Cannot access folder {folder_path}, attempting to delete as file")
            try:
                ftp.delete(folder_path)
            except:
                pass
            return

        # List all items in the directory
        items = []
        try:
            ftp.retrlines('LIST', items.append)
        except error_perm as e:
            logger.error(f"Failed to list directory {folder_path}: {e}")
            return

        # Go back to parent directory
        ftp.cwd('..')

        # Parse the LIST output and delete each item
        for item in items:
            # Parse the line to get the filename
            # Format: drwxr-xr-x  2 user group  4096 Jan 01 12:00 filename
            parts = item.split()
            if len(parts) < 9:
                continue

            filename = ' '.join(parts[8:])  # Handle filenames with spaces
            if filename in ['.', '..']:
                continue

            item_path = f"{folder_path}/{filename}"

            # Check if it's a directory (starts with 'd')
            if item.startswith('d'):
                # Recursively delete subdirectory
                self._delete_ftp_folder_recursive(ftp, item_path)
            else:
                # Delete file
                try:
                    ftp.delete(item_path)
                    logger.debug(f"Deleted file {item_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete file {item_path}: {e}")

        # After all contents are deleted, remove the directory itself
        try:
            ftp.rmd(folder_path)
            logger.info(f"Removed directory {folder_path}")
        except Exception as e:
            logger.error(f"Failed to remove directory {folder_path}: {e}")
            raise
