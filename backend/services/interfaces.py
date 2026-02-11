"""
Service Interfaces

Abstract base classes for service layer following Dependency Inversion Principle.
This allows for dependency injection and easier testing/mocking.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks


class IDiscoveryScanner(ABC):
    """
    Interface for discovery scanning operations.

    Focused on the core scanning functionality following Interface Segregation Principle.
    This interface handles the actual FTP scanning and file discovery.
    """

    @abstractmethod
    async def trigger_scan(
        self,
        db: Session,
        request: object | None,
        background_tasks: BackgroundTasks
    ) -> Any:
        """
        Trigger a discovery scan in the background.

        Args:
            db: Database session
            request: Optional discovery request with FTP overrides
            background_tasks: FastAPI BackgroundTasks for async execution

        Returns:
            DiscoveryResult object

        Raises:
            ConfigurationError: If FTP configuration is invalid
        """
        pass

    @abstractmethod
    async def verify_scan(
        self,
        db: Session,
        request: object | None
    ) -> Any:
        """
        Run discovery scan synchronously and return results.

        Args:
            db: Database session
            request: Optional discovery request with FTP overrides

        Returns:
            DiscoveryResult object with actual file counts

        Raises:
            ConfigurationError: If FTP configuration is invalid
        """
        pass


class IDiscoveryService(ABC):
    """
    Legacy interface for backward compatibility.

    DEPRECATED: Use IDiscoveryScanner instead.
    This interface is maintained for backward compatibility with existing code.
    New code should use the focused interfaces (IDiscoveryScanner).
    """

    @abstractmethod
    async def trigger_scan(
        self,
        db: Session,
        request: object | None,
        background_tasks: BackgroundTasks
    ) -> Any:
        """See IDiscoveryScanner.trigger_scan"""
        pass

    @abstractmethod
    async def verify_scan(
        self,
        db: Session,
        request: object | None
    ) -> Any:
        """See IDiscoveryScanner.verify_scan"""
        pass


class IJobService(ABC):
    """
    Abstract interface for job management services.
    """

    @abstractmethod
    def get_active_jobs_summary(self) -> Dict[str, Any]:
        """
        Get count and details of currently running jobs.

        Returns:
            Dictionary containing count and jobs list
        """
        pass

    @abstractmethod
    def cancel_active_jobs(self) -> Dict[str, Any]:
        """
        Mark all active jobs for cancellation.

        Returns:
            Dictionary containing cancelled count and message
        """
        pass

    @abstractmethod
    def cancel_job(self, job_id: str) -> Dict[str, Any]:
        """
        Cancel a specific job.

        Args:
            job_id: Job UUID

        Returns:
            Dictionary containing success status and message
        """
        pass

    @abstractmethod
    def retry_job(self, job_id: str) -> Any:
        """
        Retry a failed job.

        Args:
            job_id: Job UUID

        Returns:
            New Job object

        Raises:
            ValueError: If job cannot be retried
        """
        pass

    @abstractmethod
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Dictionary containing job statistics
        """
        pass


class IFileCleanupService(ABC):
    """
    Abstract interface for file cleanup services.
    """

    @staticmethod
    @abstractmethod
    def delete_missing_files(db: Session) -> Dict[str, Any]:
        """
        Delete all files marked as missing.

        Args:
            db: Database session

        Returns:
            Dictionary containing deletion statistics
        """
        pass


class IConfigValidator(ABC):
    """
    Abstract interface for configuration validation services.
    """

    @staticmethod
    @abstractmethod
    def validate_ftp_config(config: Dict[str, Any]) -> None:
        """
        Validate FTP configuration.

        Args:
            config: FTP configuration dictionary

        Raises:
            ConfigurationError: If configuration is invalid
        """
        pass

    @staticmethod
    @abstractmethod
    def validate_paths(temp_path: str, output_path: str) -> Dict[str, Any]:
        """
        Validate directory paths.

        Args:
            temp_path: Temporary directory path
            output_path: Output directory path

        Returns:
            Validation result dictionary
        """
        pass


class IFTPConfigService(ABC):
    """
    Abstract interface for FTP configuration services.
    """

    @staticmethod
    @abstractmethod
    def get_ftp_config(db: Session, request: object | None = None) -> Dict[str, Any]:
        """
        Get FTP configuration from settings or request override.

        Args:
            db: Database session
            request: Optional request with FTP overrides

        Returns:
            FTP configuration dictionary

        Raises:
            ConfigurationError: If configuration is missing or invalid
        """
        pass
