"""
Dev Import Service

Handles scanning folders for processed video files and importing them into the database.
This service is used for database recovery scenarios where files have already been
processed but the database records were lost.
"""

import os
import re
import shutil
import subprocess
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from sqlalchemy.orm import Session
from sqlalchemy import and_
import logging
import uuid

from models import Session as SessionModel, File, Job
from config.ai_config import AI_ENABLED
from utils.video_metadata import get_video_duration
from utils.ffmpeg_helper import get_ffmpeg_path, get_ffprobe_path

if AI_ENABLED:
    from models_analytics import FileAnalytics

logger = logging.getLogger(__name__)


@dataclass
class DevImportSettings:
    """Settings specific to dev queue imports."""
    analytics_export_path: str = ""
    thumbnail_folder: str = ""
    generate_mp3_if_missing: bool = True
    update_existing_records: bool = True


class DevImportService:
    """
    Service for importing already-processed files back into the database.
    
    Scans folder structures matching the expected output format:
    /Year/Month/Day/
    ├── Program File.mp4
    └── Source Files/
        └── Session Folder/
            ├── audio.mp3
            └── CAM X files.mp4
    """
    
    # Pattern: "Studio Keysborough 2025-11-24 09-07-52 01.mp4"
    # Groups: (name, date, time, sequence)
    KEYSBOROUGH_PATTERN = re.compile(
        r'^(.+?)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}-\d{2}-\d{2})\s+(\d{2})\.mp4$',
        re.IGNORECASE
    )
    
    # Pattern: "City Studio - 25-10-24 12-59 PM.mp4"
    # Groups: (name, day, month, year, hour, minute, ampm, sequence)
    CITY_PATTERN = re.compile(
        r'^(.+?)\s+-\s+(\d{2})-(\d{2})-(\d{2})\s+(\d{1,2})-(\d{2})\s+(AM|PM)(?:\s+\((\d+)\))?\.mp4$',
        re.IGNORECASE
    )
    
    # Pattern for ISO files: "Studio Keysborough 2025-11-24 09-07-52 CAM 1 01.mp4"
    ISO_PATTERN = re.compile(
        r'^(.+?)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}-\d{2}-\d{2})\s+CAM\s+(\d+)\s+(\d{2})\.mp4$',
        re.IGNORECASE
    )
    
    # Pattern for MP3 files
    MP3_PATTERN = re.compile(
        r'^(.+?)\s+(\d{4}-\d{2}-\d{2})\s+(\d{2}-\d{2}-\d{2})\s+(\d{2})\.mp3$',
        re.IGNORECASE
    )
    
    def __init__(self, db: Session, settings: DevImportSettings = None):
        self.db = db
        self.settings = settings or DevImportSettings()
    
    def scan_folder(self, root_path: str) -> Dict[str, Any]:
        """
        Scan a folder structure for processed video files.
        
        Args:
            root_path: Root folder to scan (e.g., /Volumes/.../Studio Recordings)
            
        Returns:
            Dictionary with session information:
            {
                "sessions": [...],
                "total_sessions": int,
                "total_size_gb": float
            }
        """
        root = Path(root_path)
        
        if not root.exists():
            raise FileNotFoundError(f"Folder does not exist: {root_path}")
        
        if not root.is_dir():
            raise ValueError(f"Path is not a directory: {root_path}")
        
        sessions = {}
        total_size = 0
        
        # Walk through the directory structure
        for mp4_file in root.rglob("*.mp4"):
            # Skip macOS resource fork files
            if mp4_file.name.startswith('._'):
                continue
            
            # Skip files in Source Files folders - we'll link them to their program
            if "Source Files" in str(mp4_file):
                continue
            
            # Try to parse the filename
            campus = "Keysborough"
            match = self.KEYSBOROUGH_PATTERN.match(mp4_file.name)
            
            if match:
                name, date, time, sequence = match.groups()
            else:
                # Try City pattern
                match = self.CITY_PATTERN.match(mp4_file.name)
                if match:
                    name, day, month, year, hour, minute, ampm, seq_match = match.groups()
                    campus = "City"
                    sequence = seq_match or "01"
                    
                    # Convert date to YYYY-MM-DD
                    date = f"20{year}-{month}-{day}"
                    
                    # Convert time to HH-MM-SS (24h)
                    try:
                        dt = datetime.strptime(f"{hour}:{minute} {ampm}", "%I:%M %p")
                        time = dt.strftime("%H-%M-00")
                    except ValueError:
                        logger.warning(f"Invalid time format in file: {mp4_file.name}")
                        continue
                else:
                    logger.debug(f"Skipping non-matching file: {mp4_file.name}")
                    continue
            
            session_key = f"{name} {date} {time} {sequence}"
            
            # Get file info
            file_size = mp4_file.stat().st_size
            total_size += file_size
            
            # Look for Source Files folder
            day_folder = mp4_file.parent
            source_folder = day_folder / "Source Files" / session_key
            
            # Find ISO files
            iso_files = []
            mp3_file = None
            
            if source_folder.exists():
                for item in source_folder.iterdir():
                    # Skip macOS resource fork files
                    if item.name.startswith('._'):
                        continue
                    if not item.is_file():
                        continue
                    if item.suffix.lower() == '.mp4':
                        iso_match = self.ISO_PATTERN.match(item.name)
                        if iso_match:
                            iso_size = item.stat().st_size
                            total_size += iso_size
                            iso_files.append({
                                "path": str(item),
                                "filename": item.name,
                                "size": iso_size,
                                "cam_number": iso_match.group(4)
                            })
                    elif item.suffix.lower() == '.mp3':
                        mp3_match = self.MP3_PATTERN.match(item.name)
                        if mp3_match:
                            mp3_file = str(item)
            
            # Check if already in database
            already_imported = self._check_session_exists(name, date, time.replace("-", ":"))
            
            sessions[session_key] = {
                "session_key": session_key,
                "name": name,
                "date": date,
                "time": time,
                "sequence": sequence,
                "campus": campus,
                "program_file": str(mp4_file),
                "program_size": file_size,
                "iso_files": iso_files,
                "mp3_file": mp3_file,
                "source_folder": str(source_folder) if source_folder.exists() else None,
                "total_files": 1 + len(iso_files),
                "total_size": file_size + sum(f["size"] for f in iso_files),
                "already_imported": already_imported
            }
        
        sessions_list = list(sessions.values())
        
        # Sort by date and time
        sessions_list.sort(key=lambda s: (s["date"], s["time"]), reverse=True)
        
        return {
            "sessions": sessions_list,
            "total_sessions": len(sessions_list),
            "total_size_gb": round(total_size / (1024 ** 3), 2)
        }
    
    def _check_session_exists(self, name: str, date: str, time: str) -> bool:
        """Check if a session already exists in the database."""
        existing = self.db.query(SessionModel).filter(
            and_(
                SessionModel.name == f"{name} {date} {time.replace('-', ':')}",
                SessionModel.recording_date == date,
                SessionModel.recording_time == time.replace("-", ":")
            )
        ).first()
        return existing is not None
    
    async def import_session(
        self,
        session_data: Dict[str, Any],
        progress_callback: Callable[[str, str], None] = None
    ) -> int:
        """
        Import a single session into the database.
        
        Args:
            session_data: Session info from scan_folder()
            progress_callback: Optional callback for progress updates
            
        Returns:
            Number of files imported
        """
        def update_progress(step: str, detail: str = None):
            if progress_callback:
                progress_callback(step, detail)
        
        session_key = session_data["session_key"]
        logger.info(f"Importing session: {session_key}")
        
        update_progress("checking_existing", session_key)
        
        # Check for existing session
        name = session_data["name"]
        date = session_data["date"]
        time = session_data["time"].replace("-", ":")
        sequence = session_data["sequence"]
        
        # Create session name that matches existing pattern
        full_session_name = f"{name} {date} {time} {sequence}"
        
        existing_session = self.db.query(SessionModel).filter(
            and_(
                SessionModel.name == full_session_name,
                SessionModel.recording_date == date,
                SessionModel.recording_time == time
            )
        ).first()
        
        if existing_session and not self.settings.update_existing_records:
            logger.info(f"Session already exists, skipping: {session_key}")
            return 0
        
        # Create or update session
        update_progress("creating_session", session_key)
        
        if existing_session:
            session = existing_session
            logger.info(f"Updating existing session: {session_key}")
        else:
            session = SessionModel(
                id=str(uuid.uuid4()),
                name=full_session_name,
                recording_date=date,
                recording_time=time,
                discovered_at=datetime.utcnow(),
                file_count=session_data["total_files"],
                total_size=session_data["total_size"],
                campus=session_data.get("campus", "Keysborough")
            )
            self.db.add(session)
            self.db.flush()  # Get the ID
        
        files_imported = 0
        program_file_record = None
        
        # Import program file
        update_progress("importing_program", session_data["program_file"])
        program_file_record = await self._import_file(
            session=session,
            file_path=session_data["program_file"],
            is_program=True,
            is_iso=False,
            session_data=session_data,
            update_progress=update_progress
        )
        if program_file_record:
            files_imported += 1
        
        # Import ISO files
        for iso_data in session_data["iso_files"]:
            update_progress("importing_iso", iso_data["filename"])
            iso_record = await self._import_file(
                session=session,
                file_path=iso_data["path"],
                is_program=False,
                is_iso=True,
                session_data=session_data,
                parent_file=program_file_record,
                update_progress=update_progress
            )
            if iso_record:
                files_imported += 1
        
        # Update session counts
        session.file_count = files_imported
        session.total_size = session_data["total_size"]
        
        self.db.commit()
        
        logger.info(f"Imported session {session_key} with {files_imported} files")
        return files_imported
    
    async def _import_file(
        self,
        session: SessionModel,
        file_path: str,
        is_program: bool,
        is_iso: bool,
        session_data: Dict[str, Any],
        parent_file: File = None,
        update_progress: Callable = None
    ) -> Optional[File]:
        """
        Import a single file into the database.
        
        Creates File record, generates thumbnail, exports/generates MP3.
        """
        path = Path(file_path)
        
        if not path.exists():
            logger.warning(f"File not found, skipping: {file_path}")
            return None
        
        # Check for existing file
        existing_file = self.db.query(File).filter(
            File.path_final == str(path)
        ).first()
        
        if existing_file:
            if self.settings.update_existing_records:
                file_record = existing_file
                logger.info(f"Updating existing file: {path.name}")
            else:
                logger.info(f"File already exists, skipping: {path.name}")
                return existing_file
        else:
            file_record = File(
                id=str(uuid.uuid4()),
                session_id=session.id
            )
            self.db.add(file_record)
        
        # Get file metadata
        file_size = path.stat().st_size
        
        if update_progress:
            update_progress("extracting_metadata", path.name)
        
        # Get duration via ffprobe
        duration = get_video_duration(str(path))
        
        # Determine relative path for ISO files
        relative_path = None
        if is_iso and session_data.get("source_folder"):
            source_folder = Path(session_data["source_folder"])
            if path.is_relative_to(source_folder.parent):
                relative_path = str(path.relative_to(source_folder.parent))
        
        # Update file record
        file_record.filename = path.name
        file_record.path_remote = f"DEV_IMPORT:{path}"  # Unique marker for dev-imported files (uses full path)
        file_record.path_local = None
        file_record.path_final = str(path)
        file_record.size = file_size
        file_record.duration = duration
        file_record.state = "COMPLETED"
        file_record.is_program_output = is_program
        file_record.is_iso = is_iso
        file_record.is_empty = False
        file_record.relative_path = relative_path
        file_record.session_folder = session_data["session_key"]
        
        if parent_file:
            file_record.parent_file_id = parent_file.id
        
        self.db.flush()
        
        # Generate thumbnail (program and ISO files)
        if update_progress:
            update_progress("generating_thumbnail", path.name)
        
        thumbnail_path = await self._generate_thumbnail(file_record, str(path))
        if thumbnail_path:
            file_record.thumbnail_path = thumbnail_path
            file_record.thumbnail_state = "READY"
            file_record.thumbnail_generated_at = datetime.utcnow()
        
        # For program files only: handle analytics export
        if is_program and AI_ENABLED:
            if update_progress:
                update_progress("exporting_analytics", path.name)
            
            await self._setup_analytics(
                file_record,
                session_data,
                update_progress
            )
        
        self.db.flush()
        return file_record
    
    async def _generate_thumbnail(self, file_record: File, video_path: str) -> Optional[str]:
        """Generate thumbnail for a video file."""
        if not self.settings.thumbnail_folder:
            logger.warning("No thumbnail folder configured, skipping thumbnail generation")
            return None
        
        thumbnail_dir = Path(self.settings.thumbnail_folder)
        thumbnail_dir.mkdir(parents=True, exist_ok=True)
        
        thumbnail_filename = f"{file_record.id}.jpg"
        thumbnail_path = thumbnail_dir / thumbnail_filename
        
        try:
            # Use qlmanage (macOS QuickLook) for fast thumbnail generation
            result = subprocess.run([
                'qlmanage',
                '-t',
                '-s', '320',
                '-o', str(thumbnail_dir),
                video_path
            ], capture_output=True, timeout=30, text=True)
            
            if result.returncode != 0:
                logger.warning(f"qlmanage failed: {result.stderr}")
                return None
            
            # qlmanage creates file with .png extension
            generated_file = thumbnail_dir / f"{Path(video_path).name}.png"
            
            if not generated_file.exists():
                # Look for recently created PNG
                import time
                now = time.time()
                for png_file in thumbnail_dir.glob("*.png"):
                    if now - png_file.stat().st_mtime < 30:
                        generated_file = png_file
                        break
            
            if generated_file.exists():
                # Convert to JPEG
                convert_result = subprocess.run([
                    'sips',
                    '-s', 'format', 'jpeg',
                    '-s', 'formatOptions', '85',
                    str(generated_file),
                    '--out', str(thumbnail_path)
                ], capture_output=True, timeout=10)
                
                if convert_result.returncode == 0:
                    generated_file.unlink()  # Remove PNG
                    return str(thumbnail_path)
                else:
                    # Just rename the PNG
                    generated_file.rename(thumbnail_path)
                    return str(thumbnail_path)
            
            logger.warning(f"No thumbnail generated for {video_path}")
            return None
            
        except subprocess.TimeoutExpired:
            logger.error(f"Thumbnail generation timed out for {video_path}")
            return None
        except Exception as e:
            logger.error(f"Thumbnail generation failed for {video_path}: {e}")
            return None
    
    async def _setup_analytics(
        self,
        file_record: File,
        session_data: Dict[str, Any],
        update_progress: Callable = None
    ):
        """Set up analytics record and export MP3 for AI processing."""
        if not self.settings.analytics_export_path:
            logger.warning("No analytics export path configured, skipping analytics setup")
            return
        
        export_dir = Path(self.settings.analytics_export_path) / file_record.id
        export_dir.mkdir(parents=True, exist_ok=True)
        
        # Export or generate MP3
        mp3_export_path = export_dir / f"{Path(file_record.filename).stem}.mp3"
        
        if session_data.get("mp3_file") and Path(session_data["mp3_file"]).exists():
            # Copy existing MP3
            if update_progress:
                update_progress("copying_mp3", session_data["mp3_file"])
            
            shutil.copy2(session_data["mp3_file"], mp3_export_path)
            logger.info(f"Copied existing MP3 to {mp3_export_path}")
            
        elif self.settings.generate_mp3_if_missing:
            # Generate MP3 from video
            if update_progress:
                update_progress("generating_mp3", file_record.filename)
            
            await self._generate_mp3(file_record.path_final, str(mp3_export_path))
        
        # Copy thumbnail to analytics folder
        if file_record.thumbnail_path and Path(file_record.thumbnail_path).exists():
            thumb_export_path = export_dir / f"{file_record.id}.jpg"
            shutil.copy2(file_record.thumbnail_path, thumb_export_path)
        
        # Update file record with export path
        file_record.external_export_path = str(export_dir)
        
        # Create FileAnalytics record
        existing_analytics = self.db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file_record.id
        ).first()
        
        if existing_analytics:
            analytics = existing_analytics
        else:
            analytics = FileAnalytics(
                id=str(uuid.uuid4()),
                file_id=file_record.id
            )
            self.db.add(analytics)
        
        analytics.state = "PENDING"
        analytics.filename = file_record.filename
        analytics.studio_location = self._extract_studio_location(session_data["name"])
        
        # Set duration fields
        if file_record.duration:
            analytics.duration_seconds = int(file_record.duration)
            analytics.duration = self._format_duration(file_record.duration)
        
        # Set timestamp fields
        try:
            dt = datetime.strptime(
                f"{session_data['date']} {session_data['time'].replace('-', ':')}",
                "%Y-%m-%d %H:%M:%S"
            )
            analytics.timestamp = dt.strftime("%b %d, %I:%M %p")
            analytics.timestamp_sort = dt.isoformat()
        except Exception as e:
            logger.warning(f"Could not parse timestamp: {e}")
        
        self.db.flush()
    
    async def _generate_mp3(self, video_path: str, output_path: str) -> bool:
        """Generate MP3 from video file using ffmpeg."""
        try:
            ffmpeg_path = get_ffmpeg_path()
            
            result = subprocess.run([
                ffmpeg_path,
                '-i', video_path,
                '-vn',  # No video
                '-acodec', 'libmp3lame',
                '-ab', '192k',
                '-ar', '44100',
                '-y',  # Overwrite
                output_path
            ], capture_output=True, timeout=300, text=True)
            
            if result.returncode == 0:
                logger.info(f"Generated MP3: {output_path}")
                return True
            else:
                logger.error(f"ffmpeg MP3 generation failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"MP3 generation timed out for {video_path}")
            return False
        except Exception as e:
            logger.error(f"MP3 generation failed: {e}")
            return False
    
    def _extract_studio_location(self, name: str) -> str:
        """Extract studio location from session name."""
        name_lower = name.lower()
        if "keysborough" in name_lower:
            return "Keysborough"
        elif "city" in name_lower:
            return "City"
        return "Unknown"
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration in seconds to MM:SS or HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
