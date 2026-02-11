"""
Discovery Orchestrator Service

This service orchestrates discovery operations, separating business logic
from API endpoint concerns (SRP principle).
"""
from sqlalchemy.orm import Session
from fastapi import BackgroundTasks
from services.interfaces import IDiscoveryService
from services.ftp_config_service import FTPConfigService
from services.config_validator import ConfigValidator
from services.discovery import DiscoveryService
from exceptions import ConfigurationError
import logging

logger = logging.getLogger(__name__)


class DiscoveryResult:
    """Result object for discovery operations"""

    def __init__(self, sessions_discovered: int, files_discovered: int, message: str):
        self.sessions_discovered = sessions_discovered
        self.files_discovered = files_discovered
        self.message = message


class DiscoveryOrchestrator(IDiscoveryService):
    """Orchestrates discovery scan operations"""

    async def trigger_scan(
        self,
        db: Session,
        request: object | None,
        background_tasks: BackgroundTasks
    ) -> DiscoveryResult:
        """
        Orchestrate discovery scan trigger.

        This method handles the business logic for triggering a discovery scan,
        including configuration retrieval, validation, and task queuing.

        Args:
            db: Database session
            request: Optional DiscoveryRequest with FTP overrides
            background_tasks: FastAPI BackgroundTasks for async execution

        Returns:
            DiscoveryResult: Result object with scan initiation details

        Raises:
            ConfigurationError: If FTP configuration is invalid or missing
        """
        # Get FTP configuration (from settings or request override)
        config = FTPConfigService.get_ftp_config(db, request)

        # Validate configuration
        ConfigValidator.validate_ftp_config(config)

        # Queue background discovery task
        background_tasks.add_task(
            self._run_discovery_task,
            db,
            config
        )

        logger.info(f"Discovery scan queued for {config['host']}:{config['port']}")

        return DiscoveryResult(
            sessions_discovered=0,  # Will be known after task completes
            files_discovered=0,
            message=f"Discovery scan started for {config['host']}:{config['port']}"
        )

    async def verify_scan(
        self,
        db: Session,
        request: object | None
    ) -> DiscoveryResult:
        """
        Run discovery scan synchronously and return results.

        This method runs the discovery immediately (awaits completion) so the
        caller receives immediate feedback about discovered files.

        Args:
            db: Database session
            request: Optional DiscoveryRequest with FTP overrides

        Returns:
            DiscoveryResult: Result object with actual discovered file counts

        Raises:
            ConfigurationError: If FTP configuration is invalid or missing
        """
        # Get and validate FTP configuration
        config = FTPConfigService.get_ftp_config(db, request)
        ConfigValidator.validate_ftp_config(config)

        # Run discovery synchronously
        service = DiscoveryService(db, config)
        files_discovered = await service.discover_and_create_files()

        logger.info(
            f"Discovery verification completed: {files_discovered} files discovered "
            f"from {config['host']}:{config['port']}"
        )

        return DiscoveryResult(
            sessions_discovered=0,  # Service doesn't return session count
            files_discovered=files_discovered,
            message=f"Verification completed, {files_discovered} new files discovered"
        )

    async def _run_discovery_task(self, db: Session, ftp_config: dict):
        """
        Background task to run discovery.

        This is the actual discovery execution that runs in the background.

        Args:
            db: Database session
            ftp_config: Validated FTP configuration dict
        """
        try:
            service = DiscoveryService(db, ftp_config)
            files_discovered = await service.discover_and_create_files()

            logger.info(
                f"Discovery completed: {files_discovered} new files discovered "
                f"from {ftp_config['host']}:{ftp_config['port']}"
            )
        except Exception as e:
            logger.error(
                f"Discovery failed for {ftp_config['host']}:{ftp_config['port']}: {e}",
                exc_info=True
            )
