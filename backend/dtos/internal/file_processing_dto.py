"""
Internal File Processing DTOs

DTOs for service-to-service communication about file processing.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class FileProcessingContext:
    """
    Internal DTO for file processing context.

    Used when passing file information between services.
    """

    file_id: int
    file_name: str
    file_path: str
    file_size: int
    session_id: str
    temp_path: str
    output_path: str
    current_state: str
    retry_count: int = 0
    last_error: Optional[str] = None
    checkpoint_data: Optional[dict] = None


@dataclass
class ProcessingResult:
    """
    Internal DTO for processing results.

    Used when services return processing outcomes.
    """

    success: bool
    file_id: int
    new_state: str
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    checkpoint_data: Optional[dict] = None


@dataclass
class CopyProgress:
    """
    Internal DTO for copy progress tracking.

    Used by copy workers to report progress.
    """

    file_id: int
    bytes_copied: int
    total_bytes: int
    percentage: float
    speed_mbps: float
    estimated_time_remaining_seconds: Optional[float] = None
    timestamp: datetime = None

    def __post_init__(self):
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
