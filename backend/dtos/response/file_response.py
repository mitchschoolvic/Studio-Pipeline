"""
File Response DTOs

DTOs for file-related API responses.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class FileResponse(BaseModel):
    """
    Response DTO for file information.

    This DTO separates the API response from the database model,
    allowing them to evolve independently.
    """

    id: int = Field(description="File ID")
    name: str = Field(description="File name")
    path: str = Field(description="File path")
    size: int = Field(description="File size in bytes")
    size_formatted: str = Field(description="Human-readable file size")
    state: str = Field(description="Current file state")
    session_id: str = Field(description="Associated session ID")
    discovered_at: datetime = Field(description="Discovery timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    class Config:
        """Pydantic configuration."""
        from_attributes = True  # Allow creation from ORM models


class FileListResponse(BaseModel):
    """
    Response DTO for list of files.

    Includes pagination and summary information.
    """

    files: List[FileResponse] = Field(description="List of files")
    total_count: int = Field(description="Total number of files")
    filtered_count: int = Field(description="Number of files after filtering")
    total_size: int = Field(description="Total size of all files in bytes")

    class Config:
        """Pydantic configuration."""
        from_attributes = True


class FileStatsResponse(BaseModel):
    """
    Response DTO for file statistics.

    Aggregated statistics about files in the system.
    """

    total_files: int = Field(description="Total number of files")
    files_by_state: dict = Field(description="Count of files by state")
    total_size_bytes: int = Field(description="Total size of all files")
    completed_size_bytes: int = Field(description="Size of completed files")
    average_file_size: float = Field(description="Average file size")

    class Config:
        """Pydantic configuration."""
        from_attributes = True
