"""
Dependency injection providers for FastAPI.

This module provides factory functions for creating repository and service instances,
following the Dependency Inversion Principle. This allows for easier testing
and better separation of concerns.
"""

from sqlalchemy.orm import Session
from fastapi import Depends
from database import get_db
from repositories.file_repository import FileRepository
from repositories.session_repository import SessionRepository
from repositories.job_repository import JobRepository
from services.interfaces import IDiscoveryService, IJobService
from services.discovery_orchestrator import DiscoveryOrchestrator
from services.job_service import JobService


def get_file_repository(db: Session) -> FileRepository:
    """
    Factory function for creating FileRepository instances.

    Args:
        db: Database session

    Returns:
        FileRepository instance
    """
    return FileRepository(db)


def get_session_repository(db: Session) -> SessionRepository:
    """
    Factory function for creating SessionRepository instances.

    Args:
        db: Database session

    Returns:
        SessionRepository instance
    """
    return SessionRepository(db)


def get_job_repository(db: Session) -> JobRepository:
    """
    Factory function for creating JobRepository instances.

    Args:
        db: Database session

    Returns:
        JobRepository instance
    """
    return JobRepository(db)


def get_discovery_service() -> IDiscoveryService:
    """
    Factory function for creating DiscoveryService instances.

    Returns:
        IDiscoveryService: Discovery service implementation

    Note: This can be easily swapped for a different implementation
    or a mock for testing purposes.
    """
    return DiscoveryOrchestrator()


def get_job_service(db: Session = Depends(get_db)) -> IJobService:
    """
    Factory function for creating JobService instances.

    Args:
        db: Database session (injected)

    Returns:
        IJobService: Job service implementation
    """
    return JobService(db)
