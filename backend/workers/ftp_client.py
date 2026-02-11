import aioftp
import asyncio
from pathlib import Path, PurePosixPath
import json
import hashlib
from typing import Optional, Dict, Callable, List, Set
import logging
import time
import re

logger = logging.getLogger(__name__)


class FTPClient:
    def __init__(self, host: str, port: int, username: str, password: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
    
    async def connect(self):
        """Establish FTP connection"""
        try:
            # Configure client for compatibility with ATEM FTP server
            # ATEM doesn't properly support EPSV (Extended Passive Mode)
            # Use only PASV to avoid protocol errors
            self.client = aioftp.Client(
                socket_timeout=30,
                path_timeout=30,
                passive_commands=("pasv",)  # Skip EPSV, use PASV only
            )
            await self.client.connect(self.host, self.port)
            await self.client.login(self.username, self.password)
            
            logger.info(f"Connected to FTP server: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"FTP connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Close FTP connection"""
        if self.client:
            try:
                await self.client.quit()
                logger.info("Disconnected from FTP server")
            except Exception as e:
                # Ignore errors during disconnect (e.g. if connection already closed)
                logger.debug(f"Error during FTP disconnect: {e}")
            finally:
                self.client = None

    @property
    def is_connected(self) -> bool:
        """Check if FTP client exists (does not verify the connection is alive)."""
        return self.client is not None

    async def ensure_connected(self):
        """Verify the FTP connection is alive. Reconnect if stale.
        
        Uses a lightweight PWD command as a health-check. If the connection
        is dead, disconnects cleanly and re-establishes a fresh connection.
        """
        if self.client is None:
            await self.connect()
            return
        try:
            await self.client.get_current_directory()
        except Exception:
            logger.info("FTP health-check failed, reconnecting...")
            await self.disconnect()
            await self.connect()
    
    async def _raw_list_directory(self, path: str) -> List[Dict]:
        """
        List directory contents using raw FTP commands with tolerance for ATEM quirks.
        
        The ATEM FTP server often returns non-standard response codes that cause
        aioftp's built-in list() to fail. This method handles those quirks.
        
        Returns:
            List of dicts with 'name', 'type' ('file' or 'dir'), 'size'
        """
        items = []
        
        try:
            # Try using aioftp's list with error tolerance
            async for item_path, info in self.client.list(path, recursive=False):
                item_name = PurePosixPath(item_path).name
                items.append({
                    'path': str(item_path),
                    'name': item_name,
                    'type': info.get('type', 'file'),
                    'size': int(info.get('size', 0)),
                    'modify': info.get('modify')
                })
        except aioftp.errors.StatusCodeError as e:
            # ATEM returns wrong codes (226 instead of 200, etc.)
            # If we got here, items collected so far are still valid
            logger.debug(f"FTP StatusCodeError in {path} (collected {len(items)} items before error): {e}")
        except Exception as e:
            # Log other errors but don't fail completely
            logger.warning(f"Error listing {path}: {e}")
        
        return items
    
    async def list_files(self, remote_path: str, excluded_folders: List[str] = None) -> list:
        """List all files in remote directory, skipping excluded folders during traversal.
        
        Args:
            remote_path: The root path to start scanning from
            excluded_folders: List of folder names to skip entirely (won't descend into them)
            
        Returns:
            List of file info dicts with 'path', 'size', 'modified'
        """
        result = await self.list_files_and_directories(remote_path, excluded_folders)
        return result['files']
    
    async def list_files_and_directories(self, remote_path: str, excluded_folders: List[str] = None) -> dict:
        """List all files and directories, skipping contents of excluded folders.
        
        This method scans the FTP server and returns both files and directories found.
        Excluded folders are reported but their contents are not scanned.
        
        Args:
            remote_path: The root path to start scanning from
            excluded_folders: List of folder names whose contents should not be scanned
            
        Returns:
            Dict with:
                - files: List of file info dicts with 'path', 'size', 'modified'
                - directories: List of directory info dicts with 'path', 'name', 'is_excluded'
        """
        files = []
        directories = []
        excluded_set = set(excluded_folders) if excluded_folders else set()
        folders_skipped = 0
        directories_scanned = 0
        
        async def scan_directory(path: str, depth: int = 0):
            """Recursively scan a directory, skipping contents of excluded folders"""
            nonlocal folders_skipped, directories_scanned
            directories_scanned += 1
            
            if depth == 0:
                logger.info(f"Starting FTP scan at root: {path}")
            else:
                logger.debug(f"Scanning subdirectory (depth={depth}): {path}")
            
            # Use our error-tolerant listing method
            items = await self._raw_list_directory(path)
            
            dirs_in_this_level = 0
            files_in_this_level = 0
            
            for item in items:
                item_name = item['name']
                item_type = item['type']
                item_path = item['path']
                
                logger.debug(f"  Processing: {item_type} - {item_path}")
                
                # Skip hidden files/folders and system folders
                if item_name.startswith('.') or item_name.startswith('$'):
                    logger.debug(f"  Skipping hidden/system: {item_name}")
                    continue
                
                if item_type == 'dir':
                    dirs_in_this_level += 1
                    # Skip known system directories entirely
                    if item_name in ('$RECYCLE.BIN', 'System Volume Information'):
                        continue
                    
                    # Check if this directory should be excluded
                    is_excluded = item_name in excluded_set
                    
                    # Always report the directory (for diagnostics)
                    directories.append({
                        'path': item_path,
                        'name': item_name,
                        'is_excluded': is_excluded,
                        'depth': depth + 1  # depth is relative to scan root
                    })
                    
                    if is_excluded:
                        folders_skipped += 1
                        logger.debug(f"Found excluded folder (not scanning contents): {item_path}")
                        # Don't descend into excluded folders
                        continue
                    
                    # Recursively scan non-excluded directories
                    logger.debug(f"Descending into: {item_path}")
                    try:
                        await scan_directory(item_path, depth + 1)
                    except Exception as scan_err:
                        logger.error(f"Failed to scan subdirectory {item_path}: {scan_err}")
                
                elif item_type == 'file':
                    files_in_this_level += 1
                    files.append({
                        'path': item_path,
                        'size': item['size'],
                        'modified': item.get('modify')
                    })
            
            logger.info(f"Directory '{path}' (depth={depth}): {dirs_in_this_level} dirs, {files_in_this_level} files, {len(items)} total items")
        
        try:
            await scan_directory(remote_path)
            
            logger.info(f"FTP scan complete: {len(files)} files, {len(directories)} directories found, {folders_skipped} excluded folders skipped")
                
        except Exception as e:
            logger.error(f"Failed to list files from {remote_path}: {e}")
            raise
            
        return {
            'files': files,
            'directories': directories,
            'stats': {
                'files_count': len(files),
                'directories_count': len(directories),
                'excluded_count': folders_skipped,
                'scanned_count': directories_scanned
            }
        }
    
    async def download_file(
        self, 
        remote_path: str, 
        local_path: Path,
        progress_callback: Optional[Callable] = None
    ) -> bool:
        """Download file with resume support
        
        Uses .part and .part.meta files for resumable downloads.
        
        Args:
            remote_path: Remote file path on FTP server
            local_path: Local destination path
            progress_callback: Optional async callback(downloaded_bytes)
            
        Returns:
            True if download successful
        """
        part_path = Path(str(local_path) + '.part')
        meta_path = Path(str(local_path) + '.part.meta')
        
        # Check for existing partial download
        start_pos = 0
        if part_path.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                if meta.get('source') == remote_path:
                    start_pos = part_path.stat().st_size
                    logger.info(f"Resuming download from byte {start_pos}")
            except Exception as e:
                logger.warning(f"Could not read metadata, starting from beginning: {e}")
                start_pos = 0
        
        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # Get file size for metadata
            stat = await self.client.stat(remote_path)
            expected_size = int(stat['size'])
            
            # Save metadata
            meta = {
                'source': remote_path,
                'expected_size': expected_size,
                'downloaded_bytes': start_pos
            }
            meta_path.write_text(json.dumps(meta))
            
            # Download with resume
            # Optimisations:
            # - Use larger block size (256KB) for fewer syscalls and better throughput
            # - Reduce metadata writes to every 10MB to avoid excessive disk I/O
            # - Throttle progress_callback to at most twice per second to reduce overhead
            BLOCK_SIZE = 262144  # 256KB
            METADATA_INTERVAL_BYTES = 10 * 1024 * 1024  # 10MB
            PROGRESS_CALLBACK_INTERVAL = 0.5  # seconds

            async with self.client.download_stream(remote_path, offset=start_pos) as stream:
                    mode = 'ab' if start_pos > 0 else 'wb'
                    with open(part_path, mode) as f:
                        downloaded = start_pos
                        last_meta_written = start_pos
                        last_progress_time = time.monotonic()
                        async for block in stream.iter_by_block(BLOCK_SIZE):
                            # Write block and update counters
                            f.write(block)
                            downloaded += len(block)

                            # Update metadata less frequently (every METADATA_INTERVAL_BYTES)
                            if downloaded - last_meta_written >= METADATA_INTERVAL_BYTES:
                                try:
                                    meta['downloaded_bytes'] = downloaded
                                    meta_path.write_text(json.dumps(meta))
                                    last_meta_written = downloaded
                                except Exception:
                                    # Non-fatal - don't abort download for metadata write failure
                                    pass

                            # Throttle progress callback to reduce coroutine scheduling overhead
                            if progress_callback:
                                now = time.monotonic()
                                if now - last_progress_time >= PROGRESS_CALLBACK_INTERVAL:
                                    try:
                                        await progress_callback(downloaded)
                                    except Exception:
                                        # Ignore progress callback failures
                                        pass
                                    last_progress_time = now
            
            # Verify file size
            final_size = part_path.stat().st_size
            if final_size != expected_size:
                raise Exception(
                    f"Size mismatch: expected {expected_size}, got {final_size}"
                )
            
            # Move to final location on success
            part_path.rename(local_path)
            if meta_path.exists():
                meta_path.unlink()
            
            logger.info(f"Download complete: {local_path.name} ({expected_size} bytes)")
            return True
        
        except Exception as e:
            # Save metadata for potential resume
            if part_path.exists():
                meta = {
                    'source': remote_path,
                    'expected_size': expected_size if 'expected_size' in locals() else 0,
                    'downloaded_bytes': part_path.stat().st_size
                }
                meta_path.write_text(json.dumps(meta))
            
            logger.error(f"Download failed for {remote_path}: {e}")
            raise
    
    async def get_file_size(self, remote_path: str) -> int:
        """Get remote file size without downloading"""
        try:
            stat = await self.client.stat(remote_path)
            return int(stat['size'])
        except Exception as e:
            logger.error(f"Failed to get file size for {remote_path}: {e}")
            raise
