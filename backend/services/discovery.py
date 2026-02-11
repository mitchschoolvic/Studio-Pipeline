import re
import json
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from models import Session as SessionModel, File, Job, Setting
from workers.ftp_client import FTPClient
from services.job_integrity_service import job_integrity_service
from pathlib import Path
from constants import SettingKeys, JobPriority
import logging

logger = logging.getLogger(__name__)


class DiscoveryService:
    # Pattern: "Studio Keysborough 2025-10-28 19-37-38 01.mp4" or "HyperDeck_2510070226_0623.mp4"
    FILENAME_PATTERN = r'(.*?) (\d{4}-\d{2}-\d{2}) (\d{2}-\d{2}-\d{2}) (\d{2})\.mp4'
    FILENAME_PATTERN_ALT = r'([A-Za-z]+)_(\d{10})_(\d{4})\.mp4'  # HyperDeck_YYMMDDHHSS_MMSS.mp4
    
    # Files smaller than 5MB are likely empty (no camera signal)
    EMPTY_FILE_THRESHOLD = 5 * 1024 * 1024  # 5 MB
    
    # ATEM folder markers
    ATEM_ISO_FOLDER = 'Video ISO Files'
    ATEM_CAM_PATTERN = r'CAM \d+'  # Matches "CAM 1", "CAM 2", etc.
    
    def __init__(self, db: Session, ftp_config: dict):
        self.db = db
        self.ftp_config = ftp_config
    
    def _get_campus(self) -> str:
        """Get the campus name from settings, defaults to 'Keysborough'"""
        setting = self.db.query(Setting).filter(Setting.key == SettingKeys.CAMPUS).first()
        return setting.value if setting else 'Keysborough'
    
    def _group_files_by_session(self, remote_files: list, source_path: str = '/') -> dict:
        """Group files into sessions based on folder structure and sequence numbers

        Detects ATEM folder structure:
        - /Folder Name/Video ISO Files/File CAM X 01.mp4 -> ISO file for Session 01
        - /Folder Name/File 01.mp4 -> Program output for Session 01

        Splits multiple program files in the same folder into separate sessions:
        - /Folder/File 01.mp4 + ISOs -> Session "Folder_01"
        - /Folder/File 02.mp4 + ISOs -> Session "Folder_02"

        Falls back to individual files for non-ATEM structure.

        Args:
            remote_files: List of file info dicts with 'path', 'size', 'modified'
            source_path: FTP source path to treat as root (e.g., '/TEST8')

        Returns:
            {
                'session_key': {
                    'name': 'Session Name',
                    'folder_path': '/path/to/folder',
                    'files': [...]
                }
            }
        """
        sessions = {}
        
        # Helper to extract sequence number from filename
        def get_sequence(filename: str) -> str:
            # Match standard ATEM pattern: "... 01.mp4" or "... CAM 1 01.mp4"
            # We want the last number before extension
            m = re.search(r' (\d{2})\.mp4$', filename, re.IGNORECASE)
            if m:
                return m.group(1)
            return "01" # Default to 01 if not found

        # Normalize source path for comparison
        source_path_normalized = Path(source_path)

        # First pass: Group by parent folder to identify ATEM structures
        folder_groups = {}
        
        for file_info in remote_files:
            path = Path(file_info['path'])
            filename = path.name
            
            # Skip hidden/non-video files
            if filename.startswith('.') or filename.startswith('$') or not (filename.lower().endswith('.mp4') or filename.lower().endswith('.mov')):
                continue
            
            # Skip system folders
            if '$RECYCLE.BIN' in str(path) or 'System Volume Information' in str(path):
                continue

            if filename.endswith('.mcc'):
                continue

            # Determine logical parent folder (grouping root)
            if self.ATEM_ISO_FOLDER in str(path):
                # /Session/Video ISO Files/File.mp4 -> Group by /Session
                group_folder = path.parent.parent
            else:
                # /Session/File.mp4 -> Group by /Session
                group_folder = path.parent
            
            # Handle root files
            if group_folder == source_path_normalized and path.parent == source_path_normalized:
                # Files in root are standalone
                group_key = f"ROOT_{filename}" # Unique group for root files
            else:
                group_key = str(group_folder)

            if group_key not in folder_groups:
                folder_groups[group_key] = {
                    'folder_path': str(group_folder),
                    'is_atem': False,
                    'files': []
                }
            
            # Check if this is an ISO file, marking the group as ATEM
            is_iso = self.ATEM_ISO_FOLDER in str(path)
            if is_iso:
                folder_groups[group_key]['is_atem'] = True
            
            folder_groups[group_key]['files'].append({
                'path': str(path),
                'size': file_info['size'],
                'modified': file_info.get('modify'),
                'filename': filename,
                'is_iso': is_iso,
                'sequence': get_sequence(filename)
            })

        # Second pass: Create sessions from groups
        for group_key, group_data in folder_groups.items():
            # If it's a root file group (standalone)
            if group_key.startswith("ROOT_"):
                f = group_data['files'][0]
                session_key = f['path']
                sessions[session_key] = {
                    'name': Path(f['filename']).stem,
                    'folder_path': group_data['folder_path'],
                    'files': [{
                        **f,
                        'is_program_output': True,
                        'is_iso': False
                    }]
                }
                continue

            # If it's an ATEM folder (has ISOs), split by sequence
            if group_data['is_atem']:
                # Group files by sequence within this folder
                sequence_batches = {}
                for f in group_data['files']:
                    seq = f['sequence']
                    if seq not in sequence_batches:
                        sequence_batches[seq] = []
                    sequence_batches[seq].append(f)
                
                # Create a session for each sequence
                # If multiple sequences exist, append suffix: Session_01, Session_02
                # If only one sequence exists, keep original name: Session
                multi_sequence = len(sequence_batches) > 1
                
                base_name = Path(group_data['folder_path']).name
                
                for seq, batch in sequence_batches.items():
                    # Always append sequence number for ATEM sessions to ensure uniqueness
                    # e.g. "Studio Keysborough ... 01", "Studio Keysborough ... 02"
                    session_name = f"{base_name} {seq}"
                    
                    session_key = f"{group_data['folder_path']}/{session_name}"
                    
                    # Determine program vs ISO for this batch
                    processed_files = []
                    for f in batch:
                        # In ATEM structure:
                        # ISOs are in "Video ISO Files" folder
                        # Program is in the main folder
                        is_iso_file = f['is_iso']
                        is_program = not is_iso_file
                        
                        processed_files.append({
                            'path': f['path'],
                            'size': f['size'],
                            'modified': f['modified'],
                            'filename': f['filename'],
                            'is_program_output': is_program,
                            'is_iso': is_iso_file
                        })
                    
                    sessions[session_key] = {
                        'name': session_name,
                        'folder_path': group_data['folder_path'],
                        'files': processed_files
                    }
            
            else:
                # Non-ATEM folder (just a folder of files)
                # Treat each file as a separate session (existing behavior)
                for f in group_data['files']:
                    session_name = Path(f['filename']).stem
                    session_key = f"{group_data['folder_path']}/{session_name}"
                    
                    sessions[session_key] = {
                        'name': session_name,
                        'folder_path': group_data['folder_path'],
                        'files': [{
                            **f,
                            'is_program_output': True,
                            'is_iso': False
                        }]
                    }

        logger.info(f"Grouped {sum(len(s['files']) for s in sessions.values())} files into {len(sessions)} sessions")
        return sessions
    
    async def discover_and_create_files(self):
        """Scan FTP and create file/session records"""
        ftp = FTPClient(
            host=self.ftp_config['host'],
            port=int(self.ftp_config['port']),
            username=self.ftp_config['username'],
            password=self.ftp_config['password']
        )

        try:
            await ftp.connect()
            source_path = self.ftp_config.get('source_path', '/')
            
            # Get excluded folders from config - pass to FTP client to skip during traversal
            excluded_folders_str = self.ftp_config.get('exclude_folders', '')
            excluded_folders = [f.strip() for f in excluded_folders_str.split(',') if f.strip()] if excluded_folders_str else []
            
            # List files with exclusion applied during traversal (much faster for large excluded folders)
            remote_files = await ftp.list_files(source_path, excluded_folders=excluded_folders)

            # Filter out hidden files and system folders (e.g. $RECYCLE.BIN)
            # This is a global filter applied before any processing
            valid_files = []
            for file_info in remote_files:
                path_str = file_info['path']
                fname = Path(path_str).name
                
                # Check for hidden files/folders
                if fname.startswith('.') or fname.startswith('$'):
                    continue
                    
                # Check for system folders in path
                if '$RECYCLE.BIN' in path_str or 'System Volume Information' in path_str:
                    continue
                    
                valid_files.append(file_info)
            
            if len(valid_files) < len(remote_files):
                logger.info(f"Filtered out {len(remote_files) - len(valid_files)} hidden/system files")
                remote_files = valid_files

            # Build set of remote file paths for efficient lookup
            remote_paths = {file_info['path'] for file_info in remote_files}

            # Mark missing files
            await self._mark_missing_files(remote_paths)

            # Group files into sessions (ATEM-aware)
            grouped_sessions = self._group_files_by_session(remote_files, source_path)
            
            # Process each session
            new_files = 0
            for session_key, session_data in grouped_sessions.items():
                files_created = await self._process_session_group(session_data, ftp)
                new_files += files_created

            # Reconcile ISO parent links in case ISOs arrived before main file
            try:
                await self._reconcile_parent_links()
            except Exception as reco_err:
                logger.warning(f"Reconcile pass failed: {reco_err}")
            
            logger.info(f"Discovery complete: {len(remote_files)} files scanned, {new_files} new files added")
            return new_files
        
        finally:
            await ftp.disconnect()
    
    async def _mark_missing_files(self, remote_paths: set):
        """Mark files as missing if they no longer exist on FTP server"""
        from models import Event
        
        # Get all files that were discovered from this FTP server
        # Check ALL files regardless of state - even COMPLETED files should be marked missing
        files_to_check = self.db.query(File).filter(
            File.is_missing == False  # Not already marked as missing
        ).all()
        
        missing_count = 0
        now = datetime.now()
        
        for file in files_to_check:
            if file.path_remote not in remote_paths:
                logger.warning(f"File no longer on FTP server, marking as missing: {file.filename} (state: {file.state})")
                file.is_missing = True
                file.missing_since = now
                file.updated_at = now
                missing_count += 1
                
                # Create event for WebSocket broadcast
                event = Event(
                    file_id=file.id,
                    event_type='file_missing',
                    payload_json=json.dumps({
                        'message': f"File removed from FTP server: {file.filename}",
                        'filename': file.filename,
                        'session_id': file.session_id,
                        'state': file.state,
                        'missing_since': now.isoformat()
                    })
                )
                self.db.add(event)
        
        if missing_count > 0:
            self.db.commit()
            logger.info(f"Marked {missing_count} files as missing")
    
    # Minimum file size to trigger FTP stability check (50 MB)
    STABILITY_CHECK_MIN_SIZE = 50 * 1024 * 1024
    # How long to wait between size checks (seconds)
    STABILITY_CHECK_DELAY = 1  # Reduced from 3s — copy_worker re-queries size before download

    async def _check_file_stability(self, ftp: 'FTPClient', file_data: dict) -> bool:
        """Quick sanity-check that a large file's FTP listing size matches stat.
        
        The ATEM may report a pre-allocated size in LIST that differs from the
        actual bytes written so far. We do a fast 1s recheck — if the sizes
        diverge, we log a warning but still proceed with discovery. The real
        safety net is the copy_worker's pre-download size re-query which will
        catch any remaining drift right before the actual transfer begins.
        
        This approach prioritises responsiveness over caution because:
        - The ATEM is frequently turned off mid-copy, so corruption prevention
          at discovery time is futile
        - Partial/corrupt copies are handled gracefully by retry logic
        - Blocking discovery delays the user's program file unnecessarily
        
        Args:
            ftp: Active FTP client connection
            file_data: Dict with 'path', 'size', 'filename'
            
        Returns:
            Always True (proceed with discovery). Logs a warning if sizes differ.
        """
        if file_data['size'] < self.STABILITY_CHECK_MIN_SIZE:
            return True
        
        try:
            await asyncio.sleep(self.STABILITY_CHECK_DELAY)
            current_size = await ftp.get_file_size(file_data['path'])
            
            if current_size != file_data['size']:
                logger.warning(
                    f"File size drift detected: {file_data['filename']} "
                    f"(LIST: {file_data['size']}, stat: {current_size}) — "
                    f"ATEM may still be writing. Proceeding — copy_worker will re-verify."
                )
                # Update the file_data with the latest size so the DB record is accurate
                file_data['size'] = current_size
            
            return True
        except Exception as e:
            logger.warning(
                f"Could not verify file stability for {file_data['filename']}: {e} — "
                f"proceeding with discovery"
            )
            return True

    async def _process_session_group(self, session_data: dict, ftp: 'FTPClient' = None) -> int:
        """Process a group of files that belong to the same session
        
        Args:
            session_data: Dict with 'name', 'folder_path', and 'files' list
            ftp: Active FTP client for file stability checks
            
        Returns:
            Number of new files created
        """
        from models import Event
        
        session_name = session_data['name']
        folder_path = session_data['folder_path']
        files = session_data['files']
        
        # First, check if any files are actually new
        # Don't create a session if all files already exist
        new_file_paths = []
        for file_data in files:
            existing = self.db.query(File).filter(
                File.path_remote == file_data['path']
            ).first()
            
            if existing:
                # Handle reappeared files
                if existing.is_missing:
                    logger.info(f"File reappeared on FTP server: {file_data['filename']}")
                    existing.is_missing = False
                    existing.missing_since = None
                    existing.updated_at = datetime.now()
                    
                    event = Event(
                        file_id=existing.id,
                        event_type='file_reappeared',
                        payload_json=json.dumps({
                            'message': f"File returned to FTP server: {file_data['filename']}",
                            'filename': file_data['filename'],
                            'session_id': existing.session_id
                        })
                    )
                    self.db.add(event)
                    self.db.commit()
            else:
                new_file_paths.append(file_data)
        
        # If no new files, return early
        if not new_file_paths:
            return 0
        
        # Determine canonical recording date/time for the session in a stable way
        # Priority:
        # 1) Program output filename that matches known pattern
        # 2) Any filename in the group that matches known patterns
        # 3) Parse from the session folder name (e.g., "... 2025-08-06 11-23-49-A8")
        # 4) Fallback to earliest modified timestamp among files (not current time)
        date = None
        time_formatted = None

        # Helper to parse from filename using either pattern
        def parse_from_filename(fname: str):
            # Try direct match first (program outputs)
            m = re.match(self.FILENAME_PATTERN, fname)
            if m:
                _name, _date, _time, _sequence = m.groups()
                return _date, _time.replace('-', ':')
            # Handle ATEM ISO filenames by stripping the " CAM X " token and retrying
            # e.g., "... 2025-09-11 12-42-40 CAM 4 01.mp4" -> "... 2025-09-11 12-42-40 01.mp4"
            iso_simplified = re.sub(r"\s+CAM\s+\d+\s+", " ", fname)
            if iso_simplified != fname:
                m_iso = re.match(self.FILENAME_PATTERN, iso_simplified)
                if m_iso:
                    _name, _date, _time, _sequence = m_iso.groups()
                    return _date, _time.replace('-', ':')
            # Try alternate HyperDeck pattern
            m2 = re.match(self.FILENAME_PATTERN_ALT, fname)
            if m2:
                _name, date_time, time_suffix = m2.groups()
                year = "20" + date_time[0:2]
                month = date_time[2:4]
                day = date_time[4:6]
                hour = date_time[6:8]
                minute = date_time[8:10]
                second = time_suffix[0:2]
                return f"{year}-{month}-{day}", f"{hour}:{minute}:{second}"
            return None, None

        # 1) Prefer a program output file that matches the pattern
        program_files = [f for f in files if f.get('is_program_output')]
        for f in program_files:
            d, t = parse_from_filename(f['filename'])
            if d and t:
                date, time_formatted = d, t
                break

        # 2) Otherwise, try any file that matches
        if not date or not time_formatted:
            for f in files:
                d, t = parse_from_filename(f['filename'])
                if d and t:
                    date, time_formatted = d, t
                    break

        # 3) Parse from session folder name as a fallback (handles ATEM folder style)
        if not date or not time_formatted:
            # Expect patterns like: "<name> YYYY-MM-DD HH-MM-SS(-A\d+)?"
            # Use search to be resilient to stray characters
            folder_match = re.search(r"(\d{4}-\d{2}-\d{2}) (\d{2}-\d{2}-\d{2})(?:-A\d+)?$", session_name.strip())
            if folder_match:
                d, t = folder_match.groups()
                date, time_formatted = d, t.replace('-', ':')

        # 4) Fallback to earliest modified timestamp among files
        if not date or not time_formatted:
            # Choose the earliest available modified time; if none, use now
            mtimes = []
            for f in files:
                file_mtime = f.get('modified')
                if isinstance(file_mtime, str):
                    try:
                        file_mtime = datetime.strptime(file_mtime, '%Y%m%d%H%M%S')
                    except Exception:
                        file_mtime = None
                if isinstance(file_mtime, datetime):
                    mtimes.append(file_mtime)
            chosen = min(mtimes) if mtimes else datetime.now()
            date = chosen.strftime('%Y-%m-%d')
            time_formatted = chosen.strftime('%H:%M:%S')
        
        # Get or create session
        session = self.db.query(SessionModel).filter(
            SessionModel.name == session_name,
            SessionModel.recording_date == date,
            SessionModel.recording_time == time_formatted
        ).first()
        
        if not session:
            session = SessionModel(
                name=session_name,
                recording_date=date,
                recording_time=time_formatted,
                campus=self._get_campus()
            )
            self.db.add(session)
            self.db.flush()
            logger.info(f"Created new session: {session_name} {date} {time_formatted}")
        
        # Get max queue_order to ensure new files get sequential numbers
        max_queue_order = self.db.query(func.max(File.queue_order)).scalar() or 0

        # Process only new files
        new_files_count = 0
        main_file_id = None  # Track main file ID for linking ISO files

        for file_data in new_file_paths:
            # Gate: verify large files are stable on the ATEM FTP before creating records.
            # The ATEM pre-allocates file sizes in LIST before finishing writes.
            # If the size is changing, skip this file — it will be picked up on the
            # next reconciler poll (every 5 seconds) once the ATEM finishes writing.
            if ftp and not await self._check_file_stability(ftp, file_data):
                logger.info(f"Skipping unstable file: {file_data['filename']} (will retry next scan)")
                continue

            # Create new file record
            is_empty = file_data['size'] < self.EMPTY_FILE_THRESHOLD
            
            # Extract session_folder and relative_path from remote path
            # path_remote format: /J-USB/<session_folder>/<relative_path>
            # or: /J-USB/<session_folder>/Video ISO Files/<filename>
            path = Path(file_data['path'])
            
            # Session folder is the parent directory name
            session_folder_name = session_name  # Use session name as session folder
            
            # Calculate relative path from session folder
            if self.ATEM_ISO_FOLDER in str(path):
                # ISO file: relative path includes subfolder
                # e.g., "Video ISO Files/Haileybury Studio CAM 1 01.mp4"
                relative_path_str = f"{self.ATEM_ISO_FOLDER}/{path.name}"
            else:
                # Main file or standalone: just the filename
                relative_path_str = path.name
            
            # Increment queue order for each new file
            max_queue_order += 1

            file = File(
                session_id=session.id,
                filename=file_data['filename'],
                path_remote=file_data['path'],
                size=file_data['size'],
                state='DISCOVERED',
                is_iso=file_data['is_iso'],
                is_program_output=file_data['is_program_output'],
                folder_path=folder_path,
                is_empty=is_empty,
                session_folder=session_folder_name,  # NEW
                relative_path=relative_path_str,      # NEW
                parent_file_id=main_file_id if file_data['is_iso'] else None,  # NEW: Link ISO to main
                queue_order=max_queue_order  # Assign sequential queue order
            )
            self.db.add(file)
            self.db.flush()
            
            # Track main file ID for linking subsequent ISO files
            if not file_data['is_iso'] and file_data['is_program_output']:
                main_file_id = file.id
            
            # Create copy job (with deduplication)
            # Program files get higher priority so they're never blocked behind ISO downloads
            copy_job, _ = job_integrity_service.get_or_create_job(
                self.db,
                file_id=file.id,
                kind='COPY',
                priority=JobPriority.for_file(
                    is_iso=file_data['is_iso'],
                    is_empty=is_empty,
                    is_program_output=file_data['is_program_output']
                )
            )
            
            # Create discovery event
            event = Event(
                file_id=file.id,
                event_type='session_discovered',
                payload_json=json.dumps({
                    'message': f"New file discovered: {file_data['filename']}",
                    'session_id': session.id,
                    'session_name': session_name,
                    'filename': file_data['filename'],
                    'is_program_output': file_data['is_program_output'],
                    'is_iso': file_data['is_iso']
                })
            )
            self.db.add(event)
            
            new_files_count += 1
            
            file_type = "ISO" if file_data['is_iso'] else "Program"
            empty_marker = " (EMPTY)" if is_empty else ""
            logger.info(f"Discovered: {file_data['filename']} - {file_type}{empty_marker} ({file_data['size'] / (1024**2):.1f} MB)")
        
        # Update session aggregates
        session.file_count = len(session.files)
        session.total_size = sum(f.size for f in session.files)
        
        self.db.commit()
        return new_files_count

    async def _reconcile_parent_links(self):
        """
        Ensure ISO files in a session are linked to the session's main program file.
        This handles out-of-order arrival where ISO files are discovered before the main file.
        Safe to run after each discovery; idempotent.
        """
        from models import Event
        
        # Find sessions that have at least one main program file
        sessions_with_main = (
            self.db.query(SessionModel)
            .join(File, File.session_id == SessionModel.id)
            .filter(File.is_program_output == True, File.is_iso == False)
            .all()
        )
        
        total_linked = 0
        for session in sessions_with_main:
            # Identify main file (first match)
            main_file = next((f for f in session.files if f.is_program_output and not f.is_iso), None)
            if not main_file:
                continue
            
            # Link any ISO without parent_file_id
            unlinked_isos = [f for f in session.files if f.is_iso and not getattr(f, 'parent_file_id', None)]
            if not unlinked_isos:
                continue
            
            for iso in unlinked_isos:
                iso.parent_file_id = main_file.id
                total_linked += 1
                
                # Emit event for UI awareness (optional)
                evt = Event(
                    file_id=iso.id,
                    event_type='iso_parent_linked',
                    payload_json=json.dumps({
                        'message': 'Linked ISO to main file',
                        'iso_filename': iso.filename,
                        'main_filename': main_file.filename,
                        'session_id': session.id,
                        'main_file_id': main_file.id
                    })
                )
                self.db.add(evt)
        
        if total_linked:
            self.db.commit()
            logger.info(f"Reconciled {total_linked} ISO parent link(s)")
    
    async def _process_remote_file(self, file_info: dict) -> bool:
        """Create session and file records
        
        Returns:
            True if new file was created, False if already exists or skipped
        """
        filename = Path(file_info['path']).name
        
        # Skip hidden files (starting with .)
        if filename.startswith('.') or filename.startswith('$'):
            logger.debug(f"Skipping hidden file: {filename}")
            return False
            
        # Skip system folders
        if '$RECYCLE.BIN' in file_info['path'] or 'System Volume Information' in file_info['path']:
            logger.debug(f"Skipping system file: {filename}")
            return False
        
        # Only process .mp4 and .mov files (case insensitive)
        file_ext = filename.lower()
        if not (file_ext.endswith('.mp4') or file_ext.endswith('.mov')):
            logger.debug(f"Skipping non-video file: {filename}")
            return False
        
        # Skip .mcc files (recording in progress markers)
        if filename.endswith('.mcc'):
            logger.debug(f"Skipping .mcc file: {filename}")
            return False
        
        # Check if already exists in database
        existing = self.db.query(File).filter(File.path_remote == file_info['path']).first()
        if existing:
            # If file was marked as missing, unmark it since it's back
            if existing.is_missing:
                from models import Event
                
                logger.info(f"File reappeared on FTP server, unmarking as missing: {filename}")
                existing.is_missing = False
                existing.missing_since = None
                existing.updated_at = datetime.now()
                
                # Create event for WebSocket broadcast
                event = Event(
                    file_id=existing.id,
                    event_type='file_reappeared',
                    payload_json=json.dumps({
                        'message': f"File returned to FTP server: {filename}",
                        'filename': filename,
                        'session_id': existing.session_id,
                        'was_missing_since': existing.missing_since.isoformat() if existing.missing_since else None
                    })
                )
                self.db.add(event)
                self.db.commit()
            else:
                logger.debug(f"File already in database: {filename}")
            return False
        
        # Parse filename - try main pattern first
        match = re.match(self.FILENAME_PATTERN, filename)
        if match:
            name, date, time, sequence = match.groups()
            time_formatted = time.replace('-', ':')
            sequence_num = int(sequence)
        else:
            # Try alternative pattern: HyperDeck_YYMMDDHHSS_MMSS.mp4
            match_alt = re.match(self.FILENAME_PATTERN_ALT, filename)
            if match_alt:
                name, date_time, time_suffix = match_alt.groups()
                # Parse: YYMMDDHHSS -> 2025-10-07 02:26:00
                year = "20" + date_time[0:2]
                month = date_time[2:4]
                day = date_time[4:6]
                hour = date_time[6:8]
                minute = date_time[8:10]
                second = time_suffix[0:2]
                
                date = f"{year}-{month}-{day}"
                time_formatted = f"{hour}:{minute}:{second}"
                sequence_num = 1  # Assume main output if no sequence in filename
            else:
                # File doesn't match known patterns - create generic session
                logger.info(f"File doesn't match known pattern, using generic session: {filename}")
                
                # Extract file modification time or use current time
                file_mtime = file_info.get('modify', datetime.now())
                if isinstance(file_mtime, str):
                    # Parse FTP date format if it's a string
                    try:
                        file_mtime = datetime.strptime(file_mtime, '%Y%m%d%H%M%S')
                    except:
                        file_mtime = datetime.now()
                elif not isinstance(file_mtime, datetime):
                    file_mtime = datetime.now()
                
                # Use filename (without extension) as session name
                name = Path(filename).stem
                date = file_mtime.strftime('%Y-%m-%d')
                time_formatted = file_mtime.strftime('%H:%M:%S')
                sequence_num = 1  # Default to main output
        
        # Get or create session
        session = self.db.query(SessionModel).filter(
            SessionModel.name == name,
            SessionModel.recording_date == date,
            SessionModel.recording_time == time_formatted
        ).first()
        
        if not session:
            session = SessionModel(
                name=name,
                recording_date=date,
                recording_time=time_formatted,
                campus=self._get_campus()
            )
            self.db.add(session)
            self.db.flush()
            logger.info(f"Created new session: {name} {date} {time_formatted}")
        
        # Determine file type
        is_iso = sequence_num > 1  # 01 = program output, 02+ = ISO cameras
        is_empty = file_info['size'] < self.EMPTY_FILE_THRESHOLD
        
        # Create file record
        file = File(
            session_id=session.id,
            filename=filename,
            path_remote=file_info['path'],
            size=file_info['size'],
            state='DISCOVERED',
            is_iso=is_iso,
            is_empty=is_empty
        )
        self.db.add(file)
        self.db.flush()
        
        # Update session aggregates
        session.file_count = len(session.files)
        session.total_size = sum(f.size for f in session.files)
        
        # Create copy job (with deduplication)
        # Program files get higher priority so they're never blocked behind ISO downloads
        copy_job, _ = job_integrity_service.get_or_create_job(
            self.db,
            file_id=file.id,
            kind='COPY',
            priority=JobPriority.for_file(
                is_iso=is_iso,
                is_empty=is_empty
            )
        )
        
        # Create event for WebSocket broadcast
        from models import Event
        event = Event(
            file_id=file.id,
            event_type='session_discovered',
            payload_json=json.dumps({
                'message': f"New file discovered: {filename}",
                'session_id': session.id,
                'session_name': session.name,
                'filename': filename,
                'file_count': session.file_count
            })
        )
        self.db.add(event)
        
        self.db.commit()
        
        file_type = "ISO" if is_iso else "Program"
        empty_marker = " (EMPTY)" if is_empty else ""
        logger.info(f"Discovered: {filename} - {file_type}{empty_marker} ({file_info['size'] / (1024**2):.1f} MB)")
        
        return True
    
    def get_session_stats(self) -> dict:
        """Get statistics about discovered sessions"""
        total_sessions = self.db.query(SessionModel).count()
        total_files = self.db.query(File).count()
        total_size = self.db.query(File).with_entities(
            func.sum(File.size)
        ).scalar() or 0
        
        pending_jobs = self.db.query(Job).filter(
            Job.state.in_(['QUEUED', 'RUNNING'])
        ).count()
        
        return {
            'total_sessions': total_sessions,
            'total_files': total_files,
            'total_size_gb': total_size / (1024**3),
            'pending_jobs': pending_jobs
        }
