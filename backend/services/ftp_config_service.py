"""
FTP Configuration Service

This service centralizes FTP configuration retrieval and building logic,
eliminating duplication across the codebase.
"""
from sqlalchemy.orm import Session
from models import Setting
from constants import SettingKeys, FTPDefaults
from exceptions import ConfigurationError
from typing import TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FTPConfigService:
    """Service to manage FTP configuration retrieval and building"""

    @staticmethod
    def get_ftp_config(
        db: Session,
        override: object | None = None
    ) -> dict:
        """
        Build FTP config from settings with optional override.

        This method eliminates the DRY violation by centralizing the logic
        for retrieving FTP configuration from database settings or using
        provided overrides.

        Args:
            db: Database session
            override: Optional object with ftp_host, ftp_port, ftp_path attributes to override settings

        Returns:
            dict: FTP configuration with keys: host, port, username, password, source_path

        Raises:
            ConfigurationError: If required FTP settings are missing and no override provided
        """
        # If override provided with host, use override values
        if override and hasattr(override, 'ftp_host') and override.ftp_host:
            return {
                'host': override.ftp_host,
                'port': override.ftp_port or FTPDefaults.PORT,
                'username': FTPDefaults.USERNAME,
                'password': FTPDefaults.PASSWORD,
                'source_path': override.ftp_path or FTPConfigService._get_setting_value(
                    db, SettingKeys.SOURCE_PATH, FTPDefaults.SOURCE_PATH
                ),
                'exclude_folders': FTPConfigService._get_setting_value(
                    db, SettingKeys.FTP_EXCLUDE_FOLDERS, ''
                )
            }

        # Otherwise, retrieve from settings
        return {
            'host': FTPConfigService._get_setting_value(
                db, SettingKeys.FTP_HOST, FTPDefaults.HOST
            ),
            'port': int(FTPConfigService._get_setting_value(
                db, SettingKeys.FTP_PORT, str(FTPDefaults.PORT)
            )),
            'username': FTPConfigService._get_setting_value(
                db, SettingKeys.FTP_USERNAME, FTPDefaults.USERNAME
            ),
            'password': FTPConfigService._get_setting_value(
                db, SettingKeys.FTP_PASSWORD, FTPDefaults.PASSWORD
            ),
            'source_path': FTPConfigService._get_setting_value(
                db, SettingKeys.SOURCE_PATH, FTPDefaults.SOURCE_PATH
            ),
            'exclude_folders': FTPConfigService._get_setting_value(
                db, SettingKeys.FTP_EXCLUDE_FOLDERS, ''
            )
        }

    @staticmethod
    def _get_setting_value(db: Session, key: str, default: str) -> str:
        """
        Retrieve single setting value with default fallback.

        Args:
            db: Database session
            key: Setting key to retrieve
            default: Default value if setting not found

        Returns:
            str: Setting value or default
        """
        setting = db.query(Setting).filter(Setting.key == key).first()
        return setting.value if setting and setting.value else default

    @staticmethod
    def is_ftp_configured(db: Session) -> bool:
        """
        Check if FTP is properly configured.

        Args:
            db: Database session

        Returns:
            bool: True if FTP host is configured, False otherwise
        """
        ftp_host = db.query(Setting).filter(
            Setting.key == SettingKeys.FTP_HOST
        ).first()
        return bool(ftp_host and ftp_host.value)

    @staticmethod
    def get_ftp_status(db: Session) -> dict:
        """
        Get FTP configuration status for display/debugging.

        Args:
            db: Database session

        Returns:
            dict: FTP configuration status including host, port, user, path
        """
        ftp_host = db.query(Setting).filter(
            Setting.key == SettingKeys.FTP_HOST
        ).first()
        ftp_port = db.query(Setting).filter(
            Setting.key == SettingKeys.FTP_PORT
        ).first()
        ftp_user = db.query(Setting).filter(
            Setting.key == SettingKeys.FTP_USER
        ).first()
        ftp_path = db.query(Setting).filter(
            Setting.key == SettingKeys.FTP_PATH
        ).first()

        return {
            "ftp_configured": bool(ftp_host and ftp_host.value),
            "ftp_host": ftp_host.value if ftp_host else None,
            "ftp_port": int(ftp_port.value) if ftp_port and ftp_port.value else FTPDefaults.PORT,
            "ftp_user": ftp_user.value if ftp_user else FTPDefaults.USERNAME,
            "ftp_path": ftp_path.value if ftp_path else FTPDefaults.RECORDINGS_PATH,
        }
