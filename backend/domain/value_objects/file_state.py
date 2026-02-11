"""
FileState Value Object

Immutable representation of a file's state in the processing pipeline.
"""

from enum import Enum
from typing import Set


class FileState(str, Enum):
    """
    Immutable file state enum.

    This replaces the magic strings scattered throughout the codebase
    with a type-safe value object.
    """

    DISCOVERED = "discovered"
    QUEUED = "queued"
    COPYING = "copying"
    COPIED = "copied"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"

    def is_terminal(self) -> bool:
        """Check if this state is terminal (no further transitions)."""
        return self in {FileState.COMPLETED, FileState.FAILED}

    def is_active(self) -> bool:
        """Check if this state represents active work."""
        return self in {FileState.COPYING, FileState.PROCESSING}

    def can_transition_to(self, new_state: "FileState") -> bool:
        """
        Check if transition to new state is valid.

        Args:
            new_state: Target state

        Returns:
            True if transition is allowed
        """
        valid_transitions = {
            FileState.DISCOVERED: {FileState.QUEUED, FileState.FAILED},
            FileState.QUEUED: {FileState.COPYING, FileState.PAUSED, FileState.FAILED},
            FileState.COPYING: {FileState.COPIED, FileState.PAUSED, FileState.FAILED},
            FileState.COPIED: {FileState.PROCESSING, FileState.FAILED},
            FileState.PROCESSING: {FileState.COMPLETED, FileState.PAUSED, FileState.FAILED},
            FileState.PAUSED: {FileState.QUEUED, FileState.COPYING, FileState.PROCESSING},
            FileState.FAILED: {FileState.QUEUED},  # Can retry
            FileState.COMPLETED: set(),  # Terminal state
        }

        return new_state in valid_transitions.get(self, set())

    @classmethod
    def from_string(cls, value: str) -> "FileState":
        """
        Create FileState from string value.

        Args:
            value: String representation

        Returns:
            FileState instance

        Raises:
            ValueError: If value is not a valid state
        """
        try:
            return cls(value)
        except ValueError:
            raise ValueError(f"Invalid file state: {value}")
