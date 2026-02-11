"""
Custom exception classes for the application.

This module defines domain-specific exceptions that provide better error handling
and clearer error messages throughout the application.
"""


class ApplicationError(Exception):
    """Base exception for all application errors"""

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ConfigurationError(ApplicationError):
    """Raised when there's a configuration issue"""

    def __init__(self, message: str, missing_keys: list[str] | None = None):
        details = {"missing_keys": missing_keys} if missing_keys else {}
        super().__init__(message, details)


class FTPConnectionError(ApplicationError):
    """Raised when FTP connection fails"""

    def __init__(self, host: str, port: int, message: str | None = None):
        details = {"host": host, "port": port}
        msg = message or f"Failed to connect to FTP server at {host}:{port}"
        super().__init__(msg, details)


class FileProcessingError(ApplicationError):
    """Raised when file processing fails"""

    def __init__(self, file_id: int, operation: str, message: str):
        details = {"file_id": file_id, "operation": operation}
        super().__init__(message, details)


class ValidationError(ApplicationError):
    """Raised when validation fails"""

    def __init__(self, message: str, invalid_fields: dict | None = None):
        details = {"invalid_fields": invalid_fields} if invalid_fields else {}
        super().__init__(message, details)


class DatabaseError(ApplicationError):
    """Raised when database operations fail"""

    def __init__(self, operation: str, message: str):
        details = {"operation": operation}
        super().__init__(message, details)


class WorkerError(ApplicationError):
    """Raised when worker operations fail"""

    def __init__(self, worker_type: str, message: str):
        details = {"worker_type": worker_type}
        super().__init__(message, details)


class DiscoveryError(ApplicationError):
    """Raised when discovery operations fail"""

    def __init__(self, message: str, ftp_host: str | None = None):
        details = {"ftp_host": ftp_host} if ftp_host else {}
        super().__init__(message, details)
