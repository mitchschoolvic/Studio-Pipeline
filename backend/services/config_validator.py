"""
Configuration Validator Service

This service provides validation logic for various configuration types,
separating validation concerns from business logic.
"""
from exceptions import ConfigurationError, ValidationError
import logging

logger = logging.getLogger(__name__)


class ConfigValidator:
    """Validator for application configurations"""

    @staticmethod
    def validate_ftp_config(config: dict) -> None:
        """
        Validate FTP configuration dictionary.

        Args:
            config: FTP configuration dict with host, port, username, password, source_path

        Raises:
            ConfigurationError: If required configuration is missing or invalid
            ValidationError: If configuration values are invalid
        """
        required_keys = ['host', 'port', 'username', 'password', 'source_path']
        missing_keys = [key for key in required_keys if key not in config]

        if missing_keys:
            raise ConfigurationError(
                f"FTP configuration is missing required keys: {', '.join(missing_keys)}",
                missing_keys=missing_keys
            )

        # Validate host
        if not config.get('host') or config['host'].strip() == '':
            raise ConfigurationError("FTP host cannot be empty")

        # Validate port
        port = config.get('port')
        if not isinstance(port, int):
            raise ValidationError(
                "FTP port must be an integer",
                invalid_fields={'port': f"Expected int, got {type(port).__name__}"}
            )

        if not (1 <= port <= 65535):
            raise ValidationError(
                "FTP port must be between 1 and 65535",
                invalid_fields={'port': port}
            )

        # Validate source_path
        if not config.get('source_path'):
            raise ConfigurationError("FTP source_path cannot be empty")

        logger.debug(f"FTP configuration validated successfully for {config['host']}:{config['port']}")

    @staticmethod
    def validate_processing_config(config: dict) -> None:
        """
        Validate processing configuration.

        Args:
            config: Processing configuration dict

        Raises:
            ConfigurationError: If required configuration is missing
            ValidationError: If configuration values are invalid
        """
        required_keys = ['temp_path', 'output_path']
        missing_keys = [key for key in required_keys if key not in config]

        if missing_keys:
            raise ConfigurationError(
                f"Processing configuration is missing required keys: {', '.join(missing_keys)}",
                missing_keys=missing_keys
            )

        # Validate paths are not empty
        for key in required_keys:
            if not config.get(key) or config[key].strip() == '':
                raise ConfigurationError(f"Processing {key} cannot be empty")

        logger.debug("Processing configuration validated successfully")

    @staticmethod
    def validate_worker_config(config: dict) -> None:
        """
        Validate worker configuration.

        Args:
            config: Worker configuration dict with max_workers, worker_interval

        Raises:
            ValidationError: If configuration values are invalid
        """
        if 'max_workers' in config:
            max_workers = config['max_workers']
            if not isinstance(max_workers, int):
                raise ValidationError(
                    "max_workers must be an integer",
                    invalid_fields={'max_workers': f"Expected int, got {type(max_workers).__name__}"}
                )
            if max_workers < 1:
                raise ValidationError(
                    "max_workers must be at least 1",
                    invalid_fields={'max_workers': max_workers}
                )

        if 'worker_interval' in config:
            interval = config['worker_interval']
            if not isinstance(interval, (int, float)):
                raise ValidationError(
                    "worker_interval must be a number",
                    invalid_fields={'worker_interval': f"Expected number, got {type(interval).__name__}"}
                )
            if interval < 0:
                raise ValidationError(
                    "worker_interval must be non-negative",
                    invalid_fields={'worker_interval': interval}
                )

        logger.debug("Worker configuration validated successfully")
