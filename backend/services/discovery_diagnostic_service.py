"""
Discovery Diagnostic Service

Provides detailed diagnostic information about FTP discovery,
showing why files are or aren't being added to sessions.
"""

import re
import logging
from pathlib import Path
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from models import File, Setting
from workers.ftp_client import FTPClient
from constants import SettingKeys

logger = logging.getLogger(__name__)


class FileStatus:
    """File status codes for diagnostic display"""
    ADDED = "added"              # File was added to a session
    EXISTS = "exists"            # File already exists in database
    EXCLUDED = "excluded"        # File is in an excluded folder
    HIDDEN = "hidden"            # Hidden file (starts with . or $)
    SYSTEM = "system"            # System folder ($RECYCLE.BIN, etc.)
    WRONG_EXTENSION = "wrong_extension"  # Not .mp4 or .mov
    TOO_SMALL = "too_small"      # Below minimum size threshold
    INVALID_NAME = "invalid_name"  # Doesn't match naming patterns


class DiscoveryDiagnosticService:
    """Service for running diagnostic scans on FTP discovery."""
    
    # Files smaller than 5MB are likely empty (no camera signal)
    EMPTY_FILE_THRESHOLD = 5 * 1024 * 1024  # 5 MB
    
    # Valid video extensions
    VALID_EXTENSIONS = {'.mp4', '.mov'}
    
    # Pattern: "Studio Keysborough 2025-10-28 19-37-38 01.mp4" 
    FILENAME_PATTERN = r'(.*?) (\d{4}-\d{2}-\d{2}) (\d{2}-\d{2}-\d{2}) (\d{2})\.mp4'
    FILENAME_PATTERN_ALT = r'([A-Za-z]+)_(\d{10})_(\d{4})\.mp4'
    
    def __init__(self, db: Session, ftp_config: dict):
        self.db = db
        self.ftp_config = ftp_config
        self.excluded_folders = self._parse_excluded_folders()
    
    def _parse_excluded_folders(self) -> List[str]:
        """Parse excluded folders from FTP config"""
        excluded_str = self.ftp_config.get('exclude_folders', '')
        if not excluded_str:
            return []
        return [f.strip() for f in excluded_str.split(',') if f.strip()]
    
    def _get_existing_file_paths(self) -> set:
        """Get set of all remote paths already in database"""
        files = self.db.query(File.path_remote).all()
        return {f.path_remote for f in files}
    
    def _classify_file(self, file_info: dict, existing_paths: set) -> str:
        """
        Classify a file and return its status code.
        
        Args:
            file_info: Dict with 'path', 'size', 'modified'
            existing_paths: Set of paths already in database
            
        Returns:
            FileStatus code
        """
        path_str = file_info['path']
        path = Path(path_str)
        filename = path.name
        extension = path.suffix.lower()
        
        # Check if already exists in database
        if path_str in existing_paths:
            return FileStatus.EXISTS
        
        # Check for hidden files (starts with . or $)
        if filename.startswith('.') or filename.startswith('$'):
            return FileStatus.HIDDEN
        
        # Check for system folders in path
        if '$RECYCLE.BIN' in path_str or 'System Volume Information' in path_str:
            return FileStatus.SYSTEM
        
        # Check excluded folders
        for excluded in self.excluded_folders:
            if excluded in path.parts:
                return FileStatus.EXCLUDED
        
        # Check file extension
        if extension not in self.VALID_EXTENSIONS:
            return FileStatus.WRONG_EXTENSION
        
        # Check file size
        if file_info['size'] < self.EMPTY_FILE_THRESHOLD:
            return FileStatus.TOO_SMALL
        
        # Would be added (passes all filters)
        return FileStatus.ADDED
    
    def _extract_directories(self, remote_files: list, source_path: str) -> List[Dict[str, Any]]:
        """
        Extract unique directories from file list with exclusion status.
        
        Returns list of dicts with 'path' and 'is_excluded'
        """
        source_path_normalized = Path(source_path)
        directories = {}
        
        for file_info in remote_files:
            path = Path(file_info['path'])
            parent = path.parent
            
            # Don't include the source path itself
            if parent == source_path_normalized:
                continue
            
            # Walk up the path to get all parent directories
            current = parent
            while current != source_path_normalized and str(current) != '/':
                dir_str = str(current)
                
                if dir_str not in directories:
                    # Check if this directory is excluded
                    is_excluded = any(
                        excluded in current.parts 
                        for excluded in self.excluded_folders
                    )
                    
                    # Check if it's a system folder
                    is_system = (
                        '$RECYCLE.BIN' in dir_str or 
                        'System Volume Information' in dir_str or
                        current.name.startswith('.') or
                        current.name.startswith('$')
                    )
                    
                    directories[dir_str] = {
                        'path': dir_str,
                        'is_excluded': is_excluded,
                        'is_system': is_system,
                        'name': current.name
                    }
                
                current = current.parent
        
        # Sort by path for consistent display
        return sorted(directories.values(), key=lambda d: d['path'])
    
    async def run_diagnostic(self) -> Dict[str, Any]:
        """
        Run a diagnostic scan of the FTP server.
        
        Returns diagnostic info including:
        - directories: List of directories found with exclusion status
        - files: List of files with status codes
        - summary: Count of files by status
        
        Note: Excluded folders are reported but their contents are not scanned.
        """
        ftp = FTPClient(
            host=self.ftp_config['host'],
            port=int(self.ftp_config['port']),
            username=self.ftp_config['username'],
            password=self.ftp_config['password']
        )
        
        try:
            await ftp.connect()
            source_path = self.ftp_config.get('source_path', '/')
            
            # Get files and directories, with excluded folder contents skipped
            scan_result = await ftp.list_files_and_directories(
                source_path, 
                excluded_folders=self.excluded_folders
            )
            remote_files = scan_result['files']
            remote_directories = scan_result['directories']
            
            # Get existing file paths from database
            existing_paths = self._get_existing_file_paths()
            
            # Format directories for response (use the ones from FTP scan directly)
            directories = [
                {
                    'path': d['path'],
                    'name': d['name'],
                    'is_excluded': d['is_excluded'],
                    'is_system': False,  # System folders are already filtered out
                    'depth': d.get('depth', 0)  # Include depth for UI indentation
                }
                for d in remote_directories
            ]
            # Sort by path for consistent display
            directories.sort(key=lambda d: d['path'])
            
            # Classify each file
            file_results = []
            status_counts = {}
            
            for file_info in remote_files:
                status = self._classify_file(file_info, existing_paths)
                
                # Count by status
                status_counts[status] = status_counts.get(status, 0) + 1
                
                path = Path(file_info['path'])
                file_results.append({
                    'path': file_info['path'],
                    'filename': path.name,
                    'folder': str(path.parent),
                    'size': file_info['size'],
                    'size_mb': round(file_info['size'] / (1024 * 1024), 2),
                    'status': status
                })
            
            # Sort files: ADDED first, then EXISTS, then others
            status_order = {
                FileStatus.ADDED: 0,
                FileStatus.EXISTS: 1,
                FileStatus.EXCLUDED: 2,
                FileStatus.TOO_SMALL: 3,
                FileStatus.WRONG_EXTENSION: 4,
                FileStatus.HIDDEN: 5,
                FileStatus.SYSTEM: 6,
                FileStatus.INVALID_NAME: 7,
            }
            file_results.sort(key=lambda f: (status_order.get(f['status'], 99), f['path']))
            
            from datetime import datetime
            
            # Count excluded directories
            excluded_dir_count = sum(1 for d in directories if d['is_excluded'])
            
            return {
                'success': True,
                'scanned_at': datetime.now().isoformat(),
                'source_path': source_path,
                'excluded_folders': self.excluded_folders,
                'directories': directories,
                'files': file_results,
                'summary': {
                    'total_files': len(remote_files),
                    'total_directories': len(directories),
                    'excluded_directories': excluded_dir_count,
                    'scanned_directories': scan_result['stats']['scanned_count'],
                    'by_status': status_counts
                }
            }
            
        except Exception as e:
            logger.error(f"Diagnostic scan failed: {e}", exc_info=True)
            from datetime import datetime
            
            return {
                'success': False,
                'scanned_at': datetime.now().isoformat(),
                'error': str(e),
                'source_path': self.ftp_config.get('source_path', '/'),
                'excluded_folders': self.excluded_folders,
                'directories': [],
                'files': [],
                'summary': {
                    'total_files': 0,
                    'total_directories': 0,
                    'by_status': {}
                }
            }
        
        finally:
            await ftp.disconnect()
