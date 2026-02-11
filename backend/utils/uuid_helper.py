"""
UUID generation helper for the application.

Provides consistent UUID generation across all models.
"""
import uuid


def generate_uuid() -> str:
    """
    Generate a new UUID string.

    Returns:
        str: A new UUID4 string
    """
    return str(uuid.uuid4())
