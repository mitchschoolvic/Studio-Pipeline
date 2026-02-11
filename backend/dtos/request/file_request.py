"""
File Request DTOs

DTOs for file-related API requests.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional


class FileFilterRequest(BaseModel):
    """
    Request DTO for filtering files.

    Provides a clear contract for file filtering parameters.
    """

    state: Optional[str] = Field(None, description="Filter by file state")
    session_id: Optional[str] = Field(None, description="Filter by session ID")
    name_pattern: Optional[str] = Field(None, description="Filter by name pattern (wildcard)")
    min_size: Optional[int] = Field(None, description="Minimum file size in bytes")
    max_size: Optional[int] = Field(None, description="Maximum file size in bytes")
    limit: int = Field(100, description="Maximum number of results")
    offset: int = Field(0, description="Offset for pagination")

    @validator("limit")
    def validate_limit(cls, v):
        """Ensure limit is within reasonable bounds."""
        if v < 1 or v > 1000:
            raise ValueError("Limit must be between 1 and 1000")
        return v

    @validator("offset")
    def validate_offset(cls, v):
        """Ensure offset is non-negative."""
        if v < 0:
            raise ValueError("Offset must be non-negative")
        return v


class FileRetryRequest(BaseModel):
    """
    Request DTO for retrying a failed file.

    Clear contract for retry operations.
    """

    file_id: int = Field(description="ID of file to retry")
    reset_progress: bool = Field(True, description="Whether to reset progress to beginning")

    class Config:
        """Pydantic configuration."""
        json_schema_extra = {
            "example": {
                "file_id": 123,
                "reset_progress": True
            }
        }
