"""
Structured Logging Utilities

Provides utilities for adding structured context to log messages,
improving observability and debugging.
"""

import logging
from typing import Any, Dict, Optional
from contextvars import ContextVar
from functools import wraps


# Context variable for request-scoped logging context
_logging_context: ContextVar[Dict[str, Any]] = ContextVar('logging_context', default={})


class StructuredLogger:
    """
    Wrapper around standard logger that adds structured context.

    Usage:
        logger = StructuredLogger(__name__)
        logger.info("User logged in", extra={
            "user_id": user.id,
            "operation": "login",
            "ip_address": request.client.host
        })
    """

    def __init__(self, name: str):
        """
        Initialize structured logger.

        Args:
            name: Logger name (typically __name__)
        """
        self.logger = logging.getLogger(name)

    def _add_context(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Add context from ContextVar to extra dict.

        Args:
            extra: Additional context dict

        Returns:
            Merged context dict
        """
        context = _logging_context.get().copy()
        if extra:
            context.update(extra)
        return context

    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log debug message with structured context."""
        self.logger.debug(message, extra=self._add_context(extra))

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log info message with structured context."""
        self.logger.info(message, extra=self._add_context(extra))

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log warning message with structured context."""
        self.logger.warning(message, extra=self._add_context(extra))

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None, exc_info: bool = False):
        """Log error message with structured context."""
        self.logger.error(message, extra=self._add_context(extra), exc_info=exc_info)

    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None, exc_info: bool = False):
        """Log critical message with structured context."""
        self.logger.critical(message, extra=self._add_context(extra), exc_info=exc_info)


def set_logging_context(**kwargs):
    """
    Set logging context for the current request/operation.

    This context will be automatically included in all log messages
    within the current context (typically a request).

    Args:
        **kwargs: Key-value pairs to add to context

    Example:
        set_logging_context(
            request_id="abc-123",
            user_id=42,
            operation="file_upload"
        )
    """
    context = _logging_context.get().copy()
    context.update(kwargs)
    _logging_context.set(context)


def clear_logging_context():
    """Clear the logging context."""
    _logging_context.set({})


def log_operation(operation_name: str):
    """
    Decorator to automatically log operation start/end with structured context.

    Args:
        operation_name: Name of the operation

    Example:
        @log_operation("process_file")
        async def process_file(file_id: int):
            # Operation automatically logged
            pass
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = StructuredLogger(func.__module__)

            # Extract common identifiers from arguments
            context = {"operation": operation_name}

            # Try to extract IDs from kwargs
            for key in ["file_id", "job_id", "session_id", "user_id"]:
                if key in kwargs:
                    context[key] = kwargs[key]

            logger.info(f"Starting {operation_name}", extra=context)

            try:
                result = await func(*args, **kwargs)
                logger.info(f"Completed {operation_name}", extra=context)
                return result
            except Exception as e:
                context["error"] = str(e)
                context["error_type"] = type(e).__name__
                logger.error(f"Failed {operation_name}", extra=context, exc_info=True)
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = StructuredLogger(func.__module__)

            # Extract common identifiers from arguments
            context = {"operation": operation_name}

            # Try to extract IDs from kwargs
            for key in ["file_id", "job_id", "session_id", "user_id"]:
                if key in kwargs:
                    context[key] = kwargs[key]

            logger.info(f"Starting {operation_name}", extra=context)

            try:
                result = func(*args, **kwargs)
                logger.info(f"Completed {operation_name}", extra=context)
                return result
            except Exception as e:
                context["error"] = str(e)
                context["error_type"] = type(e).__name__
                logger.error(f"Failed {operation_name}", extra=context, exc_info=True)
                raise

        # Return appropriate wrapper based on whether the function is async
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# Example usage in application code:
"""
from utils.logging_utils import StructuredLogger, set_logging_context, log_operation

logger = StructuredLogger(__name__)

@log_operation("file_processing")
async def process_file(file_id: int):
    logger.info("Processing started", extra={
        "file_id": file_id,
        "operation": "process",
        "worker_type": "process_worker"
    })

    # ... processing logic ...

    logger.info("Processing completed", extra={
        "file_id": file_id,
        "processing_time_seconds": elapsed_time
    })
"""
