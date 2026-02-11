"""
Error handling decorators and utilities for API endpoints.

This module implements the DRY principle by centralizing error handling
logic that was previously duplicated across multiple endpoints.
"""

from functools import wraps
from typing import Callable
from fastapi import HTTPException
import logging

from constants import HTTPStatus
from exceptions import (
    ConfigurationError,
    ValidationError,
    FTPConnectionError,
    FileProcessingError,
    DatabaseError,
    WorkerError,
    DiscoveryError,
    ApplicationError
)

logger = logging.getLogger(__name__)


def handle_api_errors(operation_name: str):
    """
    Decorator to handle common API errors consistently across endpoints.

    This decorator catches various application exceptions and converts them
    to appropriate HTTPException responses with consistent error messages.

    Args:
        operation_name: Human-readable name of the operation (e.g., "Discovery trigger")

    Returns:
        Decorated function that handles errors uniformly

    Example:
        @router.post("/scan")
        @handle_api_errors("Discovery scan")
        async def trigger_discovery(...):
            return await service.scan()
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ConfigurationError as e:
                logger.warning(f"{operation_name} - Configuration error: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=e.message
                )
            except ValidationError as e:
                logger.warning(f"{operation_name} - Validation error: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=e.message
                )
            except FTPConnectionError as e:
                logger.error(f"{operation_name} - FTP connection error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                    detail=f"FTP connection failed: {e.message}"
                )
            except FileProcessingError as e:
                logger.error(f"{operation_name} - File processing error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"File processing failed: {e.message}"
                )
            except DatabaseError as e:
                logger.error(f"{operation_name} - Database error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"Database operation failed: {e.message}"
                )
            except WorkerError as e:
                logger.error(f"{operation_name} - Worker error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"Worker operation failed: {e.message}"
                )
            except DiscoveryError as e:
                logger.error(f"{operation_name} - Discovery error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"Discovery operation failed: {e.message}"
                )
            except ApplicationError as e:
                logger.error(f"{operation_name} - Application error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"{operation_name} failed: {e.message}"
                )
            except HTTPException:
                # Re-raise HTTPException as-is to preserve status code and detail
                raise
            except Exception as e:
                logger.error(f"{operation_name} - Unexpected error: {e}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"{operation_name} failed. Please check server logs or contact support."
                )

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ConfigurationError as e:
                logger.warning(f"{operation_name} - Configuration error: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=e.message
                )
            except ValidationError as e:
                logger.warning(f"{operation_name} - Validation error: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=e.message
                )
            except FTPConnectionError as e:
                logger.error(f"{operation_name} - FTP connection error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                    detail=f"FTP connection failed: {e.message}"
                )
            except FileProcessingError as e:
                logger.error(f"{operation_name} - File processing error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"File processing failed: {e.message}"
                )
            except DatabaseError as e:
                logger.error(f"{operation_name} - Database error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"Database operation failed: {e.message}"
                )
            except WorkerError as e:
                logger.error(f"{operation_name} - Worker error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"Worker operation failed: {e.message}"
                )
            except DiscoveryError as e:
                logger.error(f"{operation_name} - Discovery error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"Discovery operation failed: {e.message}"
                )
            except ApplicationError as e:
                logger.error(f"{operation_name} - Application error: {e.message}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"{operation_name} failed: {e.message}"
                )
            except HTTPException:
                # Re-raise HTTPException as-is to preserve status code and detail
                raise
            except Exception as e:
                logger.error(f"{operation_name} - Unexpected error: {e}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    detail=f"{operation_name} failed. Please check server logs or contact support."
                )

        # Return appropriate wrapper based on whether the function is async
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
