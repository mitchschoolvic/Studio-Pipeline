from sqlalchemy import Column, String, Integer, Float, Boolean, Text, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from database import Base
from config.ai_config import AI_ENABLED

if AI_ENABLED:
    from models_analytics import FileAnalytics

def generate_uuid():
    return str(uuid.uuid4())

class Session(Base):
    __tablename__ = 'sessions'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    recording_date = Column(String, nullable=False)  # YYYY-MM-DD
    recording_time = Column(String, nullable=False)  # HH:MM:SS
    discovered_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    file_count = Column(Integer, default=0)
    total_size = Column(Integer, default=0)
    campus = Column(String, default='Keysborough')
    
    files = relationship("File", back_populates="session")
    
    __table_args__ = (
        CheckConstraint("name != ''"),
        UniqueConstraint('name', 'recording_date', 'recording_time', name='uq_session_recording'),
        Index('idx_sessions_date', 'recording_date'),
    )

class File(Base):
    """
    Represents a video file in the pipeline.
    
    File States:
    - DISCOVERED: Found on FTP, awaiting download
    - COPYING: Download in progress
    - COPIED: Downloaded to temp storage, awaiting processing
    - PROCESSING: Audio enhancement in progress (main files only)
    - PROCESSED: Enhanced and ready for organization
    - ORGANIZING: Moving to final output location
    - COMPLETED: Successfully processed and organized to final location
    - FAILED: Permanent failure after max retries
    - SKIPPED: Intentionally excluded from pipeline (e.g., ISO files below size threshold)
    
    ISO File Handling:
    - Large ISO files (>= iso_min_size_mb): COPIED → PROCESSED → COMPLETED
    - Small ISO files (< iso_min_size_mb): COPIED → SKIPPED (not organized)
    - Main files: COPIED → PROCESSED → COMPLETED (full enhancement pipeline)
    """
    __tablename__ = 'files'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    session_id = Column(String, ForeignKey('sessions.id'), nullable=False)
    filename = Column(String, nullable=False)
    path_remote = Column(String, nullable=False)
    path_local = Column(String)
    path_processed = Column(String)
    path_final = Column(String)
    size = Column(Integer, nullable=False)
    duration = Column(Float, nullable=True)  # Video duration in seconds (for bitrate calculation)
    checksum = Column(String)
    state = Column(String, nullable=False, default='DISCOVERED')
    queue_order = Column(Integer, nullable=True)  # Order in which file was added to queue
    is_empty = Column(Boolean, default=False)
    is_iso = Column(Boolean, default=False)
    is_program_output = Column(Boolean, default=True)  # File should be processed (vs copy-only)
    folder_path = Column(Text, nullable=True)  # Parent folder on FTP (for ATEM sessions)
    is_missing = Column(Boolean, default=False)  # File no longer exists on FTP
    missing_since = Column(DateTime, nullable=True)  # When file was first marked as missing
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Failure recovery tracking fields
    failure_category = Column(String, nullable=True)  # FailureCategory enum value: 'FTP_CONNECTION', 'PROCESSING_ERROR', etc.
    failure_job_kind = Column(String, nullable=True)  # Which job stage failed: 'COPY', 'PROCESS', 'ORGANIZE'
    failed_at = Column(DateTime, nullable=True)       # When the failure occurred
    retry_after = Column(DateTime, nullable=True)     # Earliest time to retry (for backoff)
    recovery_attempts = Column(Integer, default=0)    # How many recovery cycles attempted (resets on success)
    
    # Directory structure preservation fields
    session_folder = Column(Text)  # Top-level folder name (e.g., "Haileybury Studio 11")
    relative_path = Column(Text)   # Path relative to session folder (e.g., "Video ISO Files/CAM 1 01.mp4" -> renamed to "Source Files" in output)
    parent_file_id = Column(String, ForeignKey('files.id'))  # Links ISO files to main video
    
    # Thumbnail tracking fields
    thumbnail_path = Column(String, nullable=True)
    thumbnail_state = Column(String, default='PENDING')  # PENDING, GENERATING, READY, FAILED, SKIPPED
    thumbnail_generated_at = Column(DateTime, nullable=True)
    thumbnail_error = Column(Text, nullable=True)
    
    # Waveform tracking fields (for kiosk video playback)
    waveform_path = Column(String, nullable=True)
    waveform_state = Column(String, default='PENDING')  # PENDING, GENERATING, READY, FAILED
    waveform_generated_at = Column(DateTime, nullable=True)
    waveform_error = Column(Text, nullable=True)
    
    # Processing stage tracking fields (for detailed substep visualization)
    processing_stage = Column(Text, nullable=True)  # Current substep: 'extract', 'boost', 'denoise', 'mp3export', 'convert', 'remux', 'quadsplit'
    processing_stage_progress = Column(Integer, default=0)  # Progress within current substep (0-100)
    processing_detail = Column(Text, nullable=True)  # Human-readable detail (e.g., "Applying noise reduction to audio track 2 of 4")

    # MP3 export tracking
    mp3_temp_path = Column(Text, nullable=True)  # Temporary MP3 path before organize (e.g., /tmp/pipeline/{file_id}/session_name.mp3)
    external_export_path = Column(Text, nullable=True)  # UUID folder path in external location for AI analytics (e.g., /path/to/cache/{file_id})

    # Gesture trim tracking
    gesture_trimmed = Column(Boolean, default=False)  # True if video was trimmed due to gesture detection
    gesture_trim_skipped = Column(Boolean, default=False)  # True if no gesture was detected (step was skipped)
    gesture_trim_point = Column(Float, nullable=True)  # Timestamp in seconds where video was trimmed

    # OneDrive upload verification fields
    onedrive_status_code = Column(String, nullable=True)  # e.g., 'UPLOADED', 'UPLOADING', 'NOT_UPLOADED', 'UNKNOWN'
    onedrive_status_label = Column(String, nullable=True)  # human-readable label
    onedrive_uploaded_at = Column(DateTime, nullable=True)  # timestamp when first confirmed uploaded
    onedrive_last_checked_at = Column(DateTime, nullable=True)  # last time we evaluated status

    # Deletion tracking fields
    marked_for_deletion_at = Column(DateTime, nullable=True)  # When marked (null = not marked)
    deleted_at = Column(DateTime, nullable=True)              # When successfully deleted from FTP
    deletion_error = Column(Text, nullable=True)              # FTP deletion error message if any
    deletion_attempted_at = Column(DateTime, nullable=True)   # Last deletion attempt timestamp

    session = relationship("Session", back_populates="files")
    jobs = relationship("Job", back_populates="file")
    events = relationship("Event", back_populates="file")

    @property
    def is_in_subfolder(self) -> bool:
        """Check if file is in a subfolder (ISO file, media file, etc.)"""
        if not self.relative_path:
            return False
        return '/' in self.relative_path
    
    @property
    def subfolder_path(self) -> str:
        """Get subfolder path if exists (e.g., 'Video ISO Files')"""
        if self.is_in_subfolder:
            from pathlib import Path
            return str(Path(self.relative_path).parent)
        return ''
    
    @property
    def bitrate_kbps(self) -> float:
        """
        Calculate average bitrate in kbps from file size and duration.
        
        Returns:
            Bitrate in kbps, or 0 if duration is not available or invalid.
        """
        if not self.duration or self.duration <= 0:
            return 0.0
        # bitrate (kbps) = (file_size_bytes * 8) / (duration_seconds * 1000)
        return (self.size * 8) / (self.duration * 1000)
    
    def get_final_output_path(self, output_root: str) -> str:
        """
        Calculate final output path.

        Structure:
        - Program Files: {output_root}/{year}/{month}/{day}/{filename}
        - Source Files (ISOs): {output_root}/{year}/{month}/{day}/Source Files/{session_folder}/{filename}
        """
        from pathlib import Path

        # Validate inputs
        if not output_root:
            raise ValueError("Output directory path cannot be empty")
        if not self.relative_path and not self.filename:
            raise ValueError("File has no name information - cannot create output path")

        # Get session folder name
        session_folder = self.session_folder or (self.session.name if self.session else None) or 'unknown'

        # Determine relative path components based on file type
        if self.is_in_subfolder:
            # ISO/Source File -> .../Day/Source Files/SessionName/Filename
            # Extract filename from relative path (ignoring original subfolder like "Video ISO Files")
            filename = Path(self.relative_path).name
            final_rel_path = Path("Source Files") / session_folder / filename
        else:
            # Program File -> .../Day/Filename
            filename = self.filename
            final_rel_path = Path(filename)

        # Get date components from session's recording_date
        if self.session and self.session.recording_date:
            # Parse YYYY-MM-DD format
            parts = self.session.recording_date.split('-')
            if len(parts) == 3:
                year, month_num, day_num = parts

                # Create datetime for month/day name formatting
                from datetime import datetime
                date_obj = datetime.strptime(self.session.recording_date, '%Y-%m-%d')
                month_name = date_obj.strftime('%B')  # Full month name
                day_abbrev = date_obj.strftime('%a')  # Day abbreviation

                # Build path components
                month_dir = f"{month_num} - {month_name}"
                day_dir = f"{day_num} {day_abbrev} {month_name}"

                # Combine: output_root/year/month/day/...
                return str(
                    Path(output_root) / year / month_dir / day_dir / final_rel_path
                )

        # Fallback if no proper date info - use session folder at root
        return str(
            Path(output_root) / session_folder / Path(self.filename).name
        )
    
    def get_temp_processing_path(self, temp_root: str) -> str:
        """
        Get isolated temp directory path for this file.

        Uses file_id to prevent collisions between files with duplicate names.
        Structure: {temp_root}/{file_id}/{relative_path}

        Example: /temp_processing/abc-123/Haileybury Studio 01.mp4
        Example: /temp_processing/def-456/Video ISO Files/CAM 1 01.mp4
        Note: Subfolders are preserved during temp storage, renamed to "Source Files" during organize.
        """
        from pathlib import Path
        
        # Validate inputs
        if not temp_root:
            raise ValueError("Temporary storage path cannot be empty")
        if not self.id:
            raise ValueError("File ID is missing - cannot create storage path")
        if not self.relative_path and not self.filename:
            raise ValueError("File has no name information - cannot create storage path")
            
        return str(Path(temp_root) / self.id / (self.relative_path or self.filename))
    
    def get_resumable_checkpoint(self):
        """
        Return the last safe resumable state for this file.
        
        Resumable checkpoints are states where all work is complete and saved:
        - DISCOVERED: No work done yet, safe to restart
        - COPIED: File downloaded to temp, safe to restart processing
        - PROCESSED: File enhanced, safe to restart organizing
        - COMPLETED: All work done
        - SKIPPED: File intentionally excluded, no further work needed
        
        Non-resumable states require rollback:
        - COPYING: Partial download, must reset to DISCOVERED
        - PROCESSING: Partial enhancement, must reset to COPIED
        - ORGANIZING: Partial move, must reset to PROCESSED
        """
        if self.state in ['DISCOVERED', 'COPYING']:
            return 'DISCOVERED'
        elif self.state in ['COPIED', 'PROCESSING']:
            return 'COPIED'
        elif self.state in ['PROCESSED', 'ORGANIZING']:
            return 'PROCESSED'
        elif self.state in ['COMPLETED', 'SKIPPED']:
            return self.state  # Terminal states - no further work
        elif self.state == 'FAILED':
            # For failed files, check which step failed and return appropriate checkpoint
            # Look at the last completed job to determine checkpoint
            completed_jobs = [j for j in self.jobs if j.state == 'DONE']
            if not completed_jobs:
                return 'DISCOVERED'
            
            last_job_kind = max(completed_jobs, key=lambda j: j.completed_at or j.created_at).kind
            if last_job_kind == 'COPY':
                return 'COPIED'
            elif last_job_kind == 'PROCESS':
                return 'PROCESSED'
            else:
                return 'DISCOVERED'
        else:
            return 'DISCOVERED'  # Fallback to start
    
    __table_args__ = (
        CheckConstraint(
            "state IN ('DISCOVERED', 'COPYING', 'COPIED', 'PROCESSING', "
            "'PROCESSED', 'ORGANIZING', 'COMPLETED', 'FAILED', 'SKIPPED')"
        ),
        UniqueConstraint('path_remote', name='uq_file_path_remote'),
        Index('idx_files_session', 'session_id'),
        Index('idx_files_state', 'state'),
        Index('idx_files_path_final', 'path_final'),
        Index('idx_files_onedrive_uploaded', 'onedrive_uploaded_at'),
    )


class Job(Base):
    __tablename__ = 'jobs'
    
    id = Column(String, primary_key=True, default=generate_uuid)
    file_id = Column(String, ForeignKey('files.id'), nullable=False)
    kind = Column(String, nullable=False)
    state = Column(String, nullable=False, default='QUEUED')
    priority = Column(Integer, default=0)
    retries = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    progress_pct = Column(Float, default=0.0)
    progress_stage = Column(String)
    error_message = Column(Text)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Pause/cancellation tracking
    is_cancellable = Column(Boolean, default=False)  # True when job is actively running
    cancellation_requested = Column(Boolean, default=False)  # User requested pause during execution
    checkpoint_state = Column(String)  # Target state to reset to if cancelled
    
    # Heartbeat tracking for stale job detection
    last_heartbeat = Column(DateTime)  # Updated periodically during job execution
    worker_id = Column(String)  # Identifier of the worker processing this job
    
    file = relationship("File", back_populates="jobs")
    
    @property
    def can_resume_from_current_state(self):
        """Check if current file state is a safe resumption point"""
        if self.file:
            return self.file.state in ['DISCOVERED', 'COPIED', 'PROCESSED']
        return False
    
    __table_args__ = (
        CheckConstraint("kind IN ('COPY', 'PROCESS', 'ORGANIZE', 'TRANSCRIBE', 'ANALYZE')"),
        CheckConstraint("state IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED')"),
        Index('idx_jobs_state', 'state', 'kind'),
        Index('idx_jobs_file', 'file_id'),
    )

class Event(Base):
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String, ForeignKey('files.id'))
    event_type = Column(String, nullable=False)
    payload_json = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    file = relationship("File", back_populates="events")
    
    __table_args__ = (
        Index('idx_events_created', 'created_at'),
        Index('idx_events_type', 'event_type'),
    )

class Setting(Base):
    __tablename__ = 'settings'
    
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
