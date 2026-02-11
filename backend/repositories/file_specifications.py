"""
File-specific Specifications

Concrete specifications for querying files.
"""

from datetime import datetime
from typing import Optional
from models import File
from .specifications import Specification


class FilesByStateSpec(Specification[File]):
    """Specification for files in a specific state."""

    def __init__(self, state: str):
        """
        Initialize specification.

        Args:
            state: File state to filter by
        """
        self.state = state

    def is_satisfied_by(self, file: File) -> bool:
        """Check if file is in the specified state."""
        return file.state == self.state

    def to_sql_filter(self):
        """Convert to SQL filter."""
        return File.state == self.state


class FilesBySessionSpec(Specification[File]):
    """Specification for files belonging to a specific session."""

    def __init__(self, session_id: str):
        """
        Initialize specification.

        Args:
            session_id: Session ID to filter by
        """
        self.session_id = session_id

    def is_satisfied_by(self, file: File) -> bool:
        """Check if file belongs to the specified session."""
        return file.session_id == self.session_id

    def to_sql_filter(self):
        """Convert to SQL filter."""
        return File.session_id == self.session_id


class FilesCreatedAfterSpec(Specification[File]):
    """Specification for files created after a specific date."""

    def __init__(self, date: datetime):
        """
        Initialize specification.

        Args:
            date: Minimum creation date
        """
        self.date = date

    def is_satisfied_by(self, file: File) -> bool:
        """Check if file was created after the specified date."""
        return file.discovered_at > self.date

    def to_sql_filter(self):
        """Convert to SQL filter."""
        return File.discovered_at > self.date


class FilesCreatedBeforeSpec(Specification[File]):
    """Specification for files created before a specific date."""

    def __init__(self, date: datetime):
        """
        Initialize specification.

        Args:
            date: Maximum creation date
        """
        self.date = date

    def is_satisfied_by(self, file: File) -> bool:
        """Check if file was created before the specified date."""
        return file.discovered_at < self.date

    def to_sql_filter(self):
        """Convert to SQL filter."""
        return File.discovered_at < self.date


class FilesByNamePatternSpec(Specification[File]):
    """Specification for files matching a name pattern."""

    def __init__(self, pattern: str):
        """
        Initialize specification.

        Args:
            pattern: SQL LIKE pattern (use % for wildcards)
        """
        self.pattern = pattern

    def is_satisfied_by(self, file: File) -> bool:
        """Check if file name matches pattern."""
        import re
        # Convert SQL LIKE pattern to regex
        regex_pattern = self.pattern.replace('%', '.*').replace('_', '.')
        return bool(re.match(regex_pattern, file.name))

    def to_sql_filter(self):
        """Convert to SQL filter."""
        return File.name.like(self.pattern)


class FilesBySizeRangeSpec(Specification[File]):
    """Specification for files within a size range."""

    def __init__(self, min_size: Optional[int] = None, max_size: Optional[int] = None):
        """
        Initialize specification.

        Args:
            min_size: Minimum file size in bytes (None for no minimum)
            max_size: Maximum file size in bytes (None for no maximum)
        """
        self.min_size = min_size
        self.max_size = max_size

    def is_satisfied_by(self, file: File) -> bool:
        """Check if file size is within range."""
        if self.min_size is not None and file.size < self.min_size:
            return False
        if self.max_size is not None and file.size > self.max_size:
            return False
        return True

    def to_sql_filter(self):
        """Convert to SQL filter."""
        from sqlalchemy import and_
        filters = []
        if self.min_size is not None:
            filters.append(File.size >= self.min_size)
        if self.max_size is not None:
            filters.append(File.size <= self.max_size)
        return and_(*filters) if filters else True


class FilesInActiveStateSpec(Specification[File]):
    """Specification for files in active processing states."""

    def __init__(self):
        """Initialize specification."""
        self.active_states = ['copying', 'processing']

    def is_satisfied_by(self, file: File) -> bool:
        """Check if file is in an active state."""
        return file.state in self.active_states

    def to_sql_filter(self):
        """Convert to SQL filter."""
        return File.state.in_(self.active_states)


class FilesInTerminalStateSpec(Specification[File]):
    """Specification for files in terminal states (completed or failed)."""

    def __init__(self):
        """Initialize specification."""
        self.terminal_states = ['completed', 'failed']

    def is_satisfied_by(self, file: File) -> bool:
        """Check if file is in a terminal state."""
        return file.state in self.terminal_states

    def to_sql_filter(self):
        """Convert to SQL filter."""
        return File.state.in_(self.terminal_states)


# Example usage:
"""
from repositories.file_specifications import (
    FilesByStateSpec,
    FilesBySessionSpec,
    FilesCreatedAfterSpec,
    FilesBySizeRangeSpec
)
from datetime import datetime, timedelta

# Simple specification
spec = FilesByStateSpec('processing')
files = file_repo.find(spec)

# Composed specifications using AND
spec = FilesByStateSpec('completed') & FilesCreatedAfterSpec(
    datetime.now() - timedelta(days=7)
)
recent_completed_files = file_repo.find(spec)

# Complex composition using AND, OR, NOT
spec = (
    FilesBySessionSpec('session-123') &
    (FilesByStateSpec('completed') | FilesByStateSpec('failed')) &
    FilesBySizeRangeSpec(min_size=1024*1024)  # >= 1 MB
)
large_terminal_files = file_repo.find(spec)

# Using NOT
spec = ~FilesInTerminalStateSpec()  # All non-terminal files
active_files = file_repo.find(spec)
"""
