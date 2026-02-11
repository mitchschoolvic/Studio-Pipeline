"""
Application-wide constants and configuration keys.

This module centralizes all magic strings and numbers used throughout the application
to improve maintainability and reduce duplication.
"""
from enum import Enum


class FailureCategory(str, Enum):
    """
    Categorizes failure types to enable intelligent retry logic.
    
    Each category has different recovery prerequisites:
    - FTP_* categories require FTP connectivity before retry
    - PROCESSING_* categories use exponential backoff
    - STORAGE_* categories require path validation before retry
    """
    
    # FTP-related failures (require FTP connection to recover)
    FTP_CONNECTION = 'FTP_CONNECTION'      # FTP server unreachable/connection lost
    FTP_FILE_MISSING = 'FTP_FILE_MISSING'  # File no longer exists on FTP (unrecoverable)
    FTP_TRANSFER = 'FTP_TRANSFER'          # Transfer interrupted (disk disconnected, network drop)
    FTP_TIMEOUT = 'FTP_TIMEOUT'            # Connection timeout during transfer
    FTP_AUTH = 'FTP_AUTH'                  # Authentication failed
    
    # Processing failures (retry with backoff)
    PROCESSING_ERROR = 'PROCESSING_ERROR'        # Audio/video processing failure
    PROCESSING_RESOURCE = 'PROCESSING_RESOURCE'  # Out of memory, CPU overload
    PROCESSING_CORRUPT = 'PROCESSING_CORRUPT'    # Input file corrupted
    
    # Storage failures (require path validation)
    STORAGE_PATH = 'STORAGE_PATH'              # Output path unavailable/unmounted
    STORAGE_PERMISSION = 'STORAGE_PERMISSION'  # Permission denied
    STORAGE_SPACE = 'STORAGE_SPACE'            # Insufficient disk space
    
    # Unknown/unclassified
    UNKNOWN = 'UNKNOWN'
    
    @classmethod
    def requires_ftp(cls, category: 'FailureCategory') -> bool:
        """Check if this failure category requires FTP to be connected before retry"""
        return category in [
            cls.FTP_CONNECTION,
            cls.FTP_TRANSFER,
            cls.FTP_TIMEOUT
        ]
    
    @classmethod
    def is_unrecoverable(cls, category: 'FailureCategory') -> bool:
        """Check if this failure category cannot be automatically recovered"""
        return category in [
            cls.FTP_FILE_MISSING,
            cls.FTP_AUTH,
            cls.PROCESSING_CORRUPT
        ]
    
    @classmethod
    def requires_path_validation(cls, category: 'FailureCategory') -> bool:
        """Check if this failure category requires path validation before retry"""
        return category in [
            cls.STORAGE_PATH,
            cls.STORAGE_PERMISSION,
            cls.STORAGE_SPACE
        ]
    
    @classmethod
    def get_ui_label(cls, category: 'FailureCategory') -> str:
        """Get human-readable label for UI display"""
        labels = {
            cls.FTP_CONNECTION: "FTP Connection Lost",
            cls.FTP_FILE_MISSING: "File Missing from FTP",
            cls.FTP_TRANSFER: "Transfer Interrupted",
            cls.FTP_TIMEOUT: "FTP Timeout",
            cls.FTP_AUTH: "FTP Authentication Failed",
            cls.PROCESSING_ERROR: "Processing Error",
            cls.PROCESSING_RESOURCE: "Insufficient Resources",
            cls.PROCESSING_CORRUPT: "Corrupted File",
            cls.STORAGE_PATH: "Output Path Unavailable",
            cls.STORAGE_PERMISSION: "Permission Denied",
            cls.STORAGE_SPACE: "Insufficient Disk Space",
            cls.UNKNOWN: "Unknown Error"
        }
        return labels.get(category, "Unknown Error")
    
    @classmethod
    def get_recovery_hint(cls, category: 'FailureCategory') -> str:
        """Get recovery hint for UI display"""
        hints = {
            cls.FTP_CONNECTION: "Will retry automatically when FTP reconnects",
            cls.FTP_FILE_MISSING: "File must be re-uploaded to FTP server",
            cls.FTP_TRANSFER: "Will retry automatically when FTP reconnects",
            cls.FTP_TIMEOUT: "Will retry automatically when FTP reconnects",
            cls.FTP_AUTH: "Check FTP credentials in settings",
            cls.PROCESSING_ERROR: "Will retry after other files complete",
            cls.PROCESSING_RESOURCE: "Will retry when resources are available",
            cls.PROCESSING_CORRUPT: "Re-upload or replace source file",
            cls.STORAGE_PATH: "Check output path in settings",
            cls.STORAGE_PERMISSION: "Check folder permissions",
            cls.STORAGE_SPACE: "Free up disk space",
            cls.UNKNOWN: "Will retry after other files complete"
        }
        return hints.get(category, "Will retry after other files complete")

    @classmethod
    def required_job_kind(cls, category: 'FailureCategory') -> str:
        """Returns the job kind whose worker must be free before recovery.
        
        Used by the recovery orchestrator for stage-aware gating:
        FTP failures only need the copy worker free, not the entire pipeline.
        """
        if cls.requires_ftp(category):
            return 'COPY'
        if category in (cls.PROCESSING_ERROR, cls.PROCESSING_RESOURCE):
            return 'PROCESS'
        if cls.requires_path_validation(category):
            return 'ORGANIZE'
        return 'COPY'  # Default: gate on copy worker


class JobPriority:
    """Centralized job priority constants.
    
    Higher values = processed first. The copy/process/organize workers all
    pick jobs with ORDER BY priority DESC, created_at ASC.
    
    Priority tiers (highest to lowest):
        MANUAL_REPROCESS (1000) — User clicked "Reprocess" in UI
        ANALYTICS_IMMEDIATE (900) — Analytics batch/immediate requests
        MANUAL_RETRY (500) — User clicked "Retry" in UI
        ANALYTICS (200) — Background analytics/transcription
        PROGRAM (100) — Program output files (small, fast, user-facing)
        NORMAL (0) — Default: ISO files, general discovery
        RECOVERY (-5) — Auto-recovery of old failures (yields to all new work)
        EMPTY (-10) — Empty/placeholder files (lowest)
    """
    MANUAL_REPROCESS = 1000
    ANALYTICS_IMMEDIATE = 900
    MANUAL_RETRY = 500
    ANALYTICS = 200
    PROGRAM = 100
    NORMAL = 0
    RECOVERY = -5
    EMPTY = -10

    @classmethod
    def for_file(cls, *, is_iso: bool = False, is_empty: bool = False,
                 is_program_output: bool = True) -> int:
        """Determine the appropriate priority for a file based on its type.
        
        Program output files get elevated priority so they are never blocked
        behind slow or failing ISO downloads.
        """
        if is_empty:
            return cls.EMPTY
        if not is_iso and is_program_output:
            return cls.PROGRAM
        return cls.NORMAL


class ServerConfig:
    """Server configuration constants"""
    
    HOST = "0.0.0.0"  # Listen on all interfaces by default for network accessibility
    PORT = 8888  # Using 8888 to avoid conflicts with other apps (e.g., Bitfocus Companion uses 8000)
    
    @classmethod
    def url(cls) -> str:
        """Get the full server URL"""
        return f"http://{cls.HOST}:{cls.PORT}"
    
    @classmethod
    def ws_url(cls) -> str:
        """Get the WebSocket URL"""
        return f"ws://{cls.HOST}:{cls.PORT}"


class SettingKeys:
    """Database setting keys used throughout the application"""

    # FTP Configuration
    FTP_HOST = "ftp_host"
    FTP_PORT = "ftp_port"
    FTP_USERNAME = "ftp_username"
    FTP_PASSWORD = "ftp_password_encrypted"
    FTP_USER = "ftp_user"
    FTP_PATH = "ftp_path"
    SOURCE_PATH = "source_path"
    FTP_EXCLUDE_FOLDERS = "ftp_exclude_folders"

    # Path Configuration
    TEMP_PATH = "temp_path"
    OUTPUT_PATH = "output_path"

    # Processing Configuration
    FFMPEG_PATH = "ffmpeg_path"
    FFPROBE_PATH = "ffprobe_path"

    # Worker Configuration
    MAX_WORKERS = "max_workers"
    WORKER_INTERVAL = "worker_interval"

    # Discovery Configuration
    DISCOVERY_ENABLED = "discovery_enabled"
    DISCOVERY_INTERVAL = "discovery_interval"

    # OneDrive / Cloud Sync
    ONEDRIVE_DETECTION_ENABLED = "onedrive_detection_enabled"
    ONEDRIVE_ROOT = "onedrive_root"

    # Auto-deletion Configuration
    AUTO_DELETE_ENABLED = "auto_delete_enabled"
    AUTO_DELETE_AGE_MONTHS = "auto_delete_age_months"

    # External Audio Export Configuration
    EXTERNAL_AUDIO_EXPORT_ENABLED = "external_audio_export_enabled"
    EXTERNAL_AUDIO_EXPORT_PATH = "external_audio_export_path"

    # Session Configuration
    CAMPUS = "campus"

    # AI Analytics Configuration
    PAUSE_ANALYTICS = "pause_analytics"
    RUN_ANALYTICS_WHEN_IDLE = "run_analytics_when_idle"

    # Network Configuration
    SERVER_HOST = "server_host"


class WebSocketConfig:
    """WebSocket configuration constants"""

    PING_INTERVAL_MS = 30_000  # 30 seconds
    RECONNECT_DELAY_MS = 3_000  # 3 seconds
    MAX_EVENTS = 100  # Maximum events to keep in memory
    CONNECTION_TIMEOUT_MS = 60_000  # 1 minute
    MAX_RECONNECT_ATTEMPTS = 5  # Maximum reconnection attempts before giving up


class FileStates:
    """File processing states"""

    DISCOVERED = "discovered"
    QUEUED = "queued"
    COPYING = "copying"
    COPIED = "copied"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class JobStates:
    """Job processing states"""

    PENDING = "pending"
    COPYING = "copying"
    COPIED = "copied"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class FTPDefaults:
    """Default values for FTP configuration"""

    HOST = "localhost"
    PORT = 21
    USERNAME = "anonymous"
    PASSWORD = ""
    SOURCE_PATH = "/"
    RECORDINGS_PATH = "/ATEM/recordings"


class FTPConfig:
    """FTP operation configuration constants"""

    CONNECTION_TIMEOUT_SECONDS = 10.0  # Timeout for FTP connection
    LOGIN_TIMEOUT_SECONDS = 10.0  # Timeout for FTP login
    LIST_TIMEOUT_SECONDS = 10.0  # Timeout for directory listing
    TRANSFER_CHUNK_SIZE = 8192  # Bytes per transfer chunk


class ProcessingDefaults:
    """Default values for processing configuration"""

    MAX_WORKERS = 4
    WORKER_INTERVAL_SECONDS = 5
    DISCOVERY_INTERVAL_SECONDS = 300  # 5 minutes

    # FFmpeg defaults
    VIDEO_CODEC = "libx264"
    AUDIO_CODEC = "aac"
    PRESET = "medium"
    CRF = 23


class JobConfig:
    """Job processing configuration constants"""

    MAX_RETRIES = 3  # Maximum retry attempts for failed jobs
    TIMEOUT_SECONDS = 300  # 5 minutes timeout for job execution
    CHECKPOINT_INTERVAL_SECONDS = 60  # Save checkpoint every 60 seconds
    CLEANUP_RETENTION_DAYS = 7  # Keep completed job data for 7 days
    BATCH_SIZE = 50  # Number of jobs to process in a batch
    QUEUE_CHECK_INTERVAL_SECONDS = 5  # Check job queue every 5 seconds


class HTTPStatus:
    """HTTP status codes used throughout the application"""

    # Success
    OK = 200
    CREATED = 201
    ACCEPTED = 202
    NO_CONTENT = 204

    # Client Errors
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    CONFLICT = 409
    UNPROCESSABLE_ENTITY = 422

    # Server Errors
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
