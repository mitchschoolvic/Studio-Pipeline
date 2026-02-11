from pydantic import BaseModel, Field, validator
from typing import List, Optional, Any, Literal, Dict
from datetime import datetime


# Analytics Schemas
class AnalyticsSummaryItem(BaseModel):
    """Lightweight summary for list views"""
    id: str
    file_id: str
    session_id: Optional[str] = None
    title: Optional[str] = None
    filename: Optional[str] = None
    file_name: Optional[str] = None  # Alias for frontend compatibility
    owner: Optional[str] = None
    state: str
    status: Optional[str] = None  # Alias for state
    created_at: datetime
    analysis_duration_seconds: Optional[int] = None
    llm_total_tokens: Optional[int] = None
    faculty: Optional[str] = None
    content_type: Optional[str] = None
    speaker: Optional[str] = None
    audience: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None
    recording_date: Optional[str] = None

    class Config:
        from_attributes = True


class AnalyticsDetail(BaseModel):
    """Full analytics record with heavy fields"""
    id: str
    file_id: str
    session_id: Optional[str] = None
    title: Optional[str] = None
    filename: Optional[str] = None
    file_name: Optional[str] = None  # Alias for frontend compatibility
    owner: Optional[str] = None
    state: str
    status: Optional[str] = None  # Alias for state
    created_at: datetime

    # Heavy fields (excluded from summary)
    transcript: Optional[str] = None
    analysis_json: Optional[str] = None
    description: Optional[str] = None
    thumbnail_path: Optional[str] = None

    # Metadata fields
    content_type: Optional[str] = None
    faculty: Optional[str] = None
    speaker: Optional[str] = None
    audience: Optional[str] = None
    speaker_type: Optional[str] = None
    audience_type: Optional[str] = None
    speaker_confidence: Optional[str] = None
    rationale_short: Optional[str] = None
    detected_language: Optional[str] = None
    speaker_count: Optional[int] = None
    error_message: Optional[str] = None

    # LLM statistics
    llm_prompt_tokens: Optional[int] = None
    llm_completion_tokens: Optional[int] = None
    llm_total_tokens: Optional[int] = None
    llm_peak_memory_mb: Optional[float] = None
    analysis_duration_seconds: Optional[int] = None

    class Config:
        from_attributes = True


class TranscriptResponse(BaseModel):
    """Separate endpoint for transcript only"""
    file_id: str
    transcript: str


# Settings Schemas
class SettingBase(BaseModel):
    key: str
    value: str

    @validator('value')
    def validate_value(cls, v, values):
        """Validate setting values based on key"""
        key = values.get('key', '')
        
        if key == 'ftp_port':
            try:
                port = int(v)
                if not (1 <= port <= 65535):
                    raise ValueError('Port must be between 1 and 65535')
            except ValueError as e:
                if 'invalid literal' in str(e):
                    raise ValueError('Port must be a number')
                raise
        
        elif key in ['max_concurrent_copy', 'max_concurrent_process']:
            try:
                val = int(v)
                if not (1 <= val <= 10):
                    raise ValueError('Concurrency must be between 1 and 10')
            except ValueError as e:
                if 'invalid literal' in str(e):
                    raise ValueError('Concurrency must be a number')
                raise
        
        elif key == 'ftp_host':
            if not v or not v.strip():
                raise ValueError('FTP host cannot be empty')
        
        elif key == 'source_path':
            if not v or not v.strip():
                raise ValueError('Source path cannot be empty')

        elif key == 'pause_processing':
            if v.lower() not in ['true', 'false']:
                raise ValueError("pause_processing must be 'true' or 'false'")
        
        elif key == 'bitrate_threshold_kbps':
            try:
                val = float(v)
                if not (0 <= val <= 50000):
                    raise ValueError('Bitrate threshold must be between 0 and 50000 kbps')
            except ValueError as e:
                if 'could not convert' in str(e).lower():
                    raise ValueError('Bitrate threshold must be a number')
                raise

        elif key == 'external_audio_export_enabled':
            if v.lower() not in ['true', 'false']:
                raise ValueError("external_audio_export_enabled must be 'true' or 'false'")

        elif key == 'external_audio_export_path':
            # Allow empty string (feature disabled) or valid path
            if v and v.strip():
                from pathlib import Path
                try:
                    # Expand user home directory and validate it's an absolute path
                    path = Path(v).expanduser()
                    if not path.is_absolute():
                        raise ValueError('External audio export path must be an absolute path')
                except Exception as e:
                    raise ValueError(f'Invalid path: {str(e)}')

        return v


class Setting(SettingBase):
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SettingsTestRequest(BaseModel):
    """Request to test FTP connection"""
    ftp_host: str
    ftp_port: str
    ftp_anonymous: str
    ftp_username: str = ''
    ftp_password_encrypted: str = ''
    source_path: str


class SettingsTestResponse(BaseModel):
    """Response from FTP connection test"""
    success: bool
    message: str
    details: Optional[str] = None


# Job Schemas
class JobBase(BaseModel):
    kind: str
    state: str
    priority: Optional[int] = 0


class Job(JobBase):
    id: str
    file_id: str
    retries: int
    max_retries: int
    progress_pct: float
    progress_stage: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# File Schemas
class FileBase(BaseModel):
    filename: str
    size: int
    duration: Optional[float] = None
    state: str
    is_iso: bool
    is_empty: bool
    is_program_output: bool = True
    folder_path: Optional[str] = None
    is_missing: bool = False
    missing_since: Optional[datetime] = None


class File(FileBase):
    id: str
    session_id: str
    path_remote: str
    path_local: Optional[str] = None
    path_processed: Optional[str] = None
    path_final: Optional[str] = None
    external_export_path: Optional[str] = None
    # Computed fields (not stored in DB)
    final_exists: bool = False
    checksum: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    queue_order: Optional[int] = None
    
    # Processing stage tracking (for substep visualization)
    processing_stage: Optional[str] = None
    processing_stage_progress: int = 0
    processing_detail: Optional[str] = None

    # OneDrive fields (may be null if detection disabled or not applicable)
    onedrive_status_code: Optional[str] = None
    onedrive_status_label: Optional[str] = None
    onedrive_uploaded_at: Optional[datetime] = None
    onedrive_last_checked_at: Optional[datetime] = None

    # Deletion tracking fields
    marked_for_deletion_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    deletion_error: Optional[str] = None
    deletion_attempted_at: Optional[datetime] = None
    
    # Failure recovery tracking fields
    failure_category: Optional[str] = None  # FailureCategory enum value
    failure_job_kind: Optional[str] = None  # Which job stage failed
    failed_at: Optional[datetime] = None
    retry_after: Optional[datetime] = None
    recovery_attempts: int = 0
    
    # Thumbnail fields
    thumbnail_state: Optional[str] = None
    thumbnail_path: Optional[str] = None
    thumbnail_generated_at: Optional[datetime] = None
    thumbnail_error: Optional[str] = None
    
    # Waveform fields
    waveform_state: Optional[str] = None
    waveform_path: Optional[str] = None
    waveform_generated_at: Optional[datetime] = None
    waveform_error: Optional[str] = None

    # Nested relationships
    jobs: List[Job] = []

    class Config:
        from_attributes = True


# Session Schemas
class SessionBase(BaseModel):
    name: str
    recording_date: str
    recording_time: str
    campus: Optional[str] = 'Keysborough'


class SessionSummary(SessionBase):
    """Session without files (for list view)"""
    id: str
    discovered_at: datetime
    file_count: int = 0
    total_size: int = 0
    primary_file_id: Optional[str] = None
    primary_is_empty: Optional[bool] = None
    primary_file_state: Optional[str] = None

    class Config:
        from_attributes = True


class Session(SessionBase):
    """Session with files (for detail view)"""
    id: str
    discovered_at: datetime
    file_count: int = 0
    total_size: int = 0
    files: List[File] = []

    class Config:
        from_attributes = True


# Stats Schema
class PipelineStats(BaseModel):
    """Overall pipeline statistics"""
    total_sessions: int
    total_files: int
    files_discovered: int
    files_copying: int
    files_copied: int
    files_processing: int
    files_processed: int
    files_organizing: int
    files_completed: int
    files_failed: int
    
    jobs_queued: int
    jobs_running: int
    jobs_done: int
    jobs_failed: int
    
    total_size_bytes: int
    completed_size_bytes: int


# WebSocket Message Schemas
class BaseWSMessage(BaseModel):
    """Base schema for all WebSocket messages"""
    type: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class FileStateChangeMessage(BaseWSMessage):
    """File state change notification"""
    type: Literal['file_state_change'] = 'file_state_change'
    file_id: str
    state: str
    session_id: str
    progress_pct: Optional[float] = None
    error_message: Optional[str] = None
    progress_stage: Optional[str] = None
    copy_speed_mbps: Optional[float] = None


class JobProgressMessage(BaseWSMessage):
    """Job progress notification"""
    type: Literal['job_progress'] = 'job_progress'
    job_id: str
    session_id: Optional[str] = None
    progress_pct: float
    stage: Optional[str] = None


class SessionFileAddedMessage(BaseWSMessage):
    """Session file added notification"""
    type: Literal['session.file_added'] = 'session.file_added'
    session_id: str
    file_id: str
    file_data: dict


class ProcessingSubstepMessage(BaseWSMessage):
    """Processing substep progress notification"""
    type: Literal['processing_substep'] = 'processing_substep'
    file_id: str
    session_id: Optional[str] = None
    substep: str
    progress: int
    detail: Optional[str] = None


class AnalyticsStateMessage(BaseWSMessage):
    """Analytics state change notification"""
    type: Literal['analytics.state'] = 'analytics.state'
    file_id: str
    filename: str
    state: str
    extra: Optional[dict] = None


class ThumbnailUpdateMessage(BaseWSMessage):
    """Thumbnail state update notification"""
    type: Literal['thumbnail_update'] = 'thumbnail_update'
    file_id: str
    thumbnail_state: str
    etag: Optional[str] = None
    error: Optional[str] = None


class SessionDiscoveredMessage(BaseWSMessage):
    """New session discovered notification"""
    type: Literal['session_discovered'] = 'session_discovered'
    session_id: str
    session_name: str
    file_count: int


class BatchMessage(BaseWSMessage):
    """Batched messages of the same type"""
    type: Literal['batch'] = 'batch'
    batch_type: str
    count: int
    messages: List[dict]


class ErrorMessage(BaseWSMessage):
    """Error notification"""
    type: Literal['error'] = 'error'
    error_type: str
    error_message: str
    context: Optional[dict] = None


class ConnectionMessage(BaseWSMessage):
    """Connection status notification"""
    type: Literal['connection'] = 'connection'
    status: str
    message: str
