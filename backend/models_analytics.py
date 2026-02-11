"""
AI Analytics Database Models

This module contains database models for AI-powered video analytics.
Only included when BUILD_WITH_AI environment variable is set.
"""
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, Boolean, Float, CheckConstraint, Index
from sqlalchemy.orm import relationship
from database import Base
from utils.uuid_helper import generate_uuid
from datetime import datetime


class FileAnalytics(Base):
    """
    AI-generated analytics for video files.
    
    State Flow:
    - PENDING: File completed, awaiting transcription
    - TRANSCRIBING: Whisper transcription in progress
    - TRANSCRIBED: Transcription complete, awaiting analysis
    - ANALYZING: LLM analysis in progress
    - COMPLETED: Analysis complete, ready for export
    - FAILED: Permanent failure (requires manual retry)
    - SKIPPED: File not eligible for analytics (CAM, ISO, empty)
    
    Retry Behavior:
    - System retries once automatically
    - After second failure, sets manual_retry_required=True
    - Requires explicit API call or GUI action to retry again
    """
    __tablename__ = 'file_analytics'
    
    # Primary key and relationships
    id = Column(String, primary_key=True, default=generate_uuid)
    file_id = Column(String, ForeignKey('files.id', ondelete='CASCADE'), nullable=False, unique=True)
    
    # Analytics state tracking
    state = Column(String, nullable=False, default='PENDING')
    
    # Raw AI outputs
    transcript = Column(Text, nullable=True)  # Whisper transcription (full text)
    analysis_json = Column(Text, nullable=True)  # LLM analysis as JSON string
    
    # LLM Provenance (for version tracking and reproducibility)
    llm_model_version = Column(String, nullable=True)  # e.g., "Qwen2.5-3B-Instruct-4bit"
    llm_prompt_version = Column(String, nullable=True)  # e.g., "v1.0"
    whisper_model_version = Column(String, nullable=True)  # e.g., "whisper-small-mlx"
    
    # Excel/CSV Export Fields (17 fields matching specification)
    title = Column(String, nullable=True)  # video_title
    description = Column(Text, nullable=True)  # short_description
    duration = Column(String, nullable=True)  # Human-readable "15:42"
    duration_seconds = Column(Integer, nullable=True)
    content_type = Column(String, nullable=True)  # "Promotional", "Learning Content", etc.
    faculty = Column(String, nullable=True)  # "Languages", "Sciences", etc.
    speaker_type = Column(Text, nullable=True)  # JSON array: ["Staff", "Student"]
    audience_type = Column(Text, nullable=True)  # JSON array: ["Student", "Parent"]
    speaker_confidence = Column(Text, nullable=True)  # JSON object: {"Staff": 0.6, "Student": 0.4}
    rationale_short = Column(Text, nullable=True)  # AI reasoning for categorization
    timestamp = Column(String, nullable=True)  # Human-readable "Nov 5, 10:30 AM"
    timestamp_sort = Column(String, nullable=True)  # ISO format "2024-11-05T10:30:00"
    thumbnail_url = Column(String, nullable=True)
    filename = Column(String, nullable=True)  # Cached from file
    studio_location = Column(String, nullable=True)  # "Keysborough" or "City"
    detected_language = Column(String, nullable=True)  # Language detected by Whisper
    speaker_count = Column(Integer, nullable=True)
    video_url = Column(String, nullable=True)
    
    # NEW: Simplified string fields for schema compliance (derived from JSON fields above)
    audience = Column(String, nullable=True)  # Comma-separated: "Student, Parent"
    speaker = Column(String, nullable=True)   # Comma-separated: "Staff, Student"
    
    # Processing metadata
    transcription_started_at = Column(DateTime, nullable=True)
    transcription_completed_at = Column(DateTime, nullable=True)
    transcription_duration_seconds = Column(Integer, nullable=True)
    analysis_started_at = Column(DateTime, nullable=True)
    analysis_completed_at = Column(DateTime, nullable=True)
    analysis_duration_seconds = Column(Integer, nullable=True)

    # LLM statistics (for monitoring and optimization)
    llm_prompt_tokens = Column(Integer, nullable=True)  # Number of tokens in the prompt
    llm_completion_tokens = Column(Integer, nullable=True)  # Number of tokens in the completion
    llm_total_tokens = Column(Integer, nullable=True)  # Total tokens used
    llm_peak_memory_mb = Column(Float, nullable=True)  # Peak memory usage in MB during generation

    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    manual_retry_required = Column(Boolean, default=False)  # Set after automatic retry exhausted
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    file = relationship("File", backref="analytics")
    
    __table_args__ = (
        CheckConstraint(
            "state IN ('PENDING', 'TRANSCRIBING', 'TRANSCRIBED', 'ANALYZING', "
            "'COMPLETED', 'FAILED', 'SKIPPED')"
        ),
        Index('idx_analytics_state', 'state'),
        Index('idx_analytics_file_id', 'file_id'),
        Index('idx_analytics_created_at', 'created_at'),
        Index('idx_analytics_manual_retry', 'manual_retry_required'),
    )

    def get_onedrive_path(self, db_session) -> str:
        """
        Generate URL-encoded relative path to session folder for OneDrive.

        This returns the path from output_path to the session folder (excluding filename).
        User can prepend their OneDrive base URL to create full URLs.

        Example:
            Input path_final: /Users/user/Videos/StudioPipeline/2025/02 - February/04 Tue February/Studio Keysborough 2025-02-04 11-26-16/video.mp4
            Output: 2025/02%20-%20February/04%20Tue%20February/Studio%20Keysborough%202025-02-04%2011-26-16

        Args:
            db_session: Database session for settings lookup

        Returns:
            URL-encoded relative path to session folder (empty string if unavailable)
        """
        from urllib.parse import quote
        from pathlib import Path

        # Need file relationship with path_final
        if not self.file or not self.file.path_final:
            return ''

        try:
            # Get output_path setting from database
            from models import Setting
            output_path_setting = db_session.query(Setting).filter_by(key='output_path').first()

            if not output_path_setting or not output_path_setting.value:
                return ''

            # Expand ~ in output path
            import os
            base_path = os.path.expanduser(output_path_setting.value)

            # Get the session folder path (parent directory of the file)
            file_path = Path(self.file.path_final)

            # If file has a relative_path with /, it's in a subfolder (like "Source Files")
            # Go up one more level to get the session folder
            if self.file.relative_path and '/' in self.file.relative_path:
                session_folder_path = file_path.parent.parent
            else:
                session_folder_path = file_path.parent

            # Calculate relative path from output root to session folder
            session_folder_str = str(session_folder_path)

            if not session_folder_str.startswith(base_path):
                return ''

            # Remove base path and leading slash
            relative_path = session_folder_str.replace(base_path, '').lstrip('/')

            # URL encode: spaces → %20, but keep forward slashes
            encoded_path = quote(relative_path, safe='/')

            return encoded_path

        except Exception as e:
            # Log error but don't crash export
            import logging
            logging.getLogger(__name__).error(f"Error generating OneDrive path: {e}")
            return ''

    def to_excel_row(self, db_session=None, thumbnail_url=None, thumbnail_path=None) -> dict:
        """
        Convert analytics to Excel row format matching target schema specification.

        Schema: *[Audience:s, Description:s, Duration:s, DurationSeconds:n, Faculty:s,
                  Filename:s, Language:s, Speaker:s, SpeakerCount:n, StudioLocation:s,
                  ThumbnailUrl:i, ThumbnailPath:s, Timestamp:s, TimestampSort:s, Title:s, Transcript:s,
                  Type:s, VideoUrl:s]

        All values are properly typed (numbers as numbers, not strings).

        Args:
            db_session: Optional database session for VideoUrl generation
            thumbnail_url: Optional pre-computed thumbnail URL (relative path)
            thumbnail_path: Optional absolute path to the thumbnail file

        Returns:
            Dict with all 18 Excel fields ready for export
        """
        import json

        # Compute simplified fields if not pre-populated (backward compatibility)
        audience_str = self.audience
        if not audience_str and self.audience_type:
            try:
                audience_list = json.loads(self.audience_type)
                audience_str = ', '.join(audience_list)
            except (json.JSONDecodeError, TypeError):
                audience_str = ''

        speaker_str = self.speaker
        if not speaker_str and self.speaker_type:
            try:
                speaker_list = json.loads(self.speaker_type)
                speaker_str = ', '.join(speaker_list)
            except (json.JSONDecodeError, TypeError):
                speaker_str = ''

        # Generate VideoUrl if db_session provided (OneDrive-compatible path)
        video_url = self.video_url or ''
        if db_session and not video_url:
            video_url = self.get_onedrive_path(db_session)

        # Use provided thumbnail_url, fall back to self.thumbnail_url
        final_thumbnail_url = thumbnail_url or self.thumbnail_url or ''

        return {
            'Audience': audience_str or '',              # NEW: Simple string format
            'Description': self.description or '',
            'Duration': self.duration or '',
            'DurationSeconds': self.duration_seconds or 0,  # Number type
            'Faculty': self.faculty or '',
            'Filename': self.filename or '',
            'Language': self.detected_language or 'English',
            'Speaker': speaker_str or '',                # NEW: Simple string format
            'SpeakerCount': self.speaker_count or 0,     # Number type
            'StudioLocation': self.studio_location or '',
            'ThumbnailUrl': final_thumbnail_url,
            'ThumbnailPath': thumbnail_path or '',       # NEW: Absolute path
            'Timestamp': self.timestamp or '',
            'TimestampSort': self.timestamp_sort or '',  # ISO string for sorting
            'Title': self.title or '',
            'Transcript': self.transcript or '',
            'Type': self.content_type or '',
            'VideoUrl': video_url
        }
    
    def needs_manual_retry(self) -> bool:
        """Check if this analytics record requires manual intervention"""
        return self.manual_retry_required and self.state == 'FAILED'
    
    def can_retry(self) -> bool:
        """Check if this analytics record can be retried"""
        return self.state == 'FAILED' and not self.manual_retry_required
    
    def reset_for_retry(self):
        """
        Reset analytics state for manual retry.
        
        This should only be called through the API/GUI after manual review.
        """
        if not self.manual_retry_required:
            return False
        
        # Determine where to restart based on what completed
        if self.transcription_completed_at:
            # Transcription succeeded, restart analysis
            self.state = 'TRANSCRIBED'
        else:
            # Restart from beginning
            self.state = 'PENDING'
        
        self.manual_retry_required = False
        self.error_message = None
        self.retry_count = 0
        
        return True
