"""
FileSize Value Object

Immutable representation of a file size with formatting capabilities.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileSize:
    """
    Immutable file size value object.

    Provides human-readable formatting and validation.
    """

    bytes: int

    def __post_init__(self):
        """Validate file size."""
        if self.bytes < 0:
            raise ValueError(f"File size cannot be negative: {self.bytes}")

    def to_human_readable(self) -> str:
        """
        Format size in human-readable format.

        Returns:
            String like "1.5 MB" or "256 KB"
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if self.bytes < 1024.0:
                return f"{self.bytes:.1f} {unit}"
            self.bytes /= 1024.0
        return f"{self.bytes:.1f} PB"

    def to_megabytes(self) -> float:
        """Convert to megabytes."""
        return self.bytes / (1024 * 1024)

    def to_gigabytes(self) -> float:
        """Convert to gigabytes."""
        return self.bytes / (1024 * 1024 * 1024)

    @classmethod
    def from_megabytes(cls, mb: float) -> "FileSize":
        """Create FileSize from megabytes."""
        return cls(bytes=int(mb * 1024 * 1024))

    @classmethod
    def from_gigabytes(cls, gb: float) -> "FileSize":
        """Create FileSize from gigabytes."""
        return cls(bytes=int(gb * 1024 * 1024 * 1024))

    def __str__(self) -> str:
        """String representation."""
        return self.to_human_readable()

    def __add__(self, other: "FileSize") -> "FileSize":
        """Add two file sizes."""
        if not isinstance(other, FileSize):
            raise TypeError(f"Cannot add FileSize and {type(other)}")
        return FileSize(bytes=self.bytes + other.bytes)

    def __lt__(self, other: "FileSize") -> bool:
        """Compare file sizes."""
        if not isinstance(other, FileSize):
            raise TypeError(f"Cannot compare FileSize and {type(other)}")
        return self.bytes < other.bytes
