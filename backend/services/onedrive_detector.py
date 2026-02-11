"""
OneDrive Upload Detector (macOS)

Determines if a file under the OneDrive File Provider has been uploaded to cloud
by invoking `fileproviderctl evaluate <path>` and parsing flags:
- isUploaded: 1 when server has most recent version
- isUploading: 1 when an upload is in progress
- isDownloaded: 1 when a local copy is present (may be 0 after "Free Up Space")

We persist status on the File record and broadcast changes over WebSocket.
This runs only on macOS and only when enabled via setting `onedrive_detection_enabled`.
"""
from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from database import SessionLocal
from models import File, Setting
from constants import SettingKeys
from services.websocket import manager

logger = logging.getLogger(__name__)

_EVAL_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*([01])\s*;?\s*$")


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _parse_fileprovider_output(output: str) -> dict:
    flags: dict[str, int] = {}
    for line in output.splitlines():
        m = _EVAL_RE.match(line)
        if m:
            key, val = m.group(1), int(m.group(2))
            flags[key] = val
    return flags


def _run_evaluate(path: str, timeout: float = 5.0) -> Optional[dict]:
    try:
        cmd = ["/usr/bin/fileproviderctl", "evaluate", path]
        logger.debug(f"Running: {' '.join(shlex.quote(c) for c in cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.warning(f"fileproviderctl returned {result.returncode}: {result.stderr.strip()}")
            return None
        return _parse_fileprovider_output(result.stdout)
    except FileNotFoundError:
        logger.error("fileproviderctl not found; OneDrive detection unavailable on this system")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("fileproviderctl evaluate timed out")
        return None
    except Exception as e:
        logger.error(f"Error running fileproviderctl: {e}")
        return None


class OneDriveDetector:
    """Polls completed files for OneDrive upload status and persists updates."""

    def __init__(self, interval_seconds: float = 15.0):
        self.interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def _is_enabled_and_root(self, db: Session) -> Tuple[bool, Optional[str]]:
        enabled_setting = db.query(Setting).filter(Setting.key == SettingKeys.ONEDRIVE_DETECTION_ENABLED).first()
        if enabled_setting and enabled_setting.value.lower() == "false":
            return False, None
        # Enabled by default
        root_setting = db.query(Setting).filter(Setting.key == SettingKeys.ONEDRIVE_ROOT).first()
        onedrive_root = root_setting.value if root_setting and root_setting.value else None
        return True, onedrive_root

    def _is_in_onedrive(self, file: File, onedrive_root: Optional[str]) -> bool:
        if not file.path_final:
            return False
        if not onedrive_root:
            # If not configured, assume OneDrive when path includes CloudStorage/OneDrive-
            return "Library/CloudStorage/OneDrive-" in file.path_final
        try:
            return Path(file.path_final).resolve().as_posix().startswith(Path(onedrive_root).resolve().as_posix())
        except Exception:
            return False

    def _status_label(self, flags: Optional[dict]) -> Tuple[str, str]:
        if not flags:
            return "UNKNOWN", "Unknown"
        is_uploaded = flags.get("isUploaded", 0) == 1
        is_uploading = flags.get("isUploading", 0) == 1
        is_downloaded = flags.get("isDownloaded", 0) == 1
        if is_uploading and not is_uploaded:
            return "UPLOADING", "Uploading"
        if is_uploaded:
            # Downloaded may be 0 when user frees up space
            return "UPLOADED", ("Uploaded (local copy freed)" if not is_downloaded else "Uploaded")
        return "NOT_UPLOADED", "Not uploaded"

    async def _check_once(self):
        if not _is_macos():
            logger.debug("OneDriveDetector disabled: not macOS")
            return
        db = SessionLocal()
        try:
            enabled, onedrive_root = self._is_enabled_and_root(db)
            if not enabled:
                logger.debug("OneDriveDetector disabled via setting")
                return

            # Poll recent COMPLETED files that either have never been confirmed, or were checked recently
            # Limit to avoid load
            q = (
                db.query(File)
                .filter(File.state == "COMPLETED", File.path_final.isnot(None))
                .order_by(File.onedrive_uploaded_at.is_(None).desc(), File.updated_at.desc())
            )
            files = q.limit(50).all()

            for f in files:
                if not self._is_in_onedrive(f, onedrive_root):
                    continue
                flags = _run_evaluate(f.path_final)
                code, label = self._status_label(flags)
                is_uploaded = flags.get("isUploaded", 0) == 1 if flags else None
                is_downloaded = flags.get("isDownloaded", 0) == 1 if flags else None

                changed = (
                    f.onedrive_status_code != code or f.onedrive_status_label != label or
                    (is_uploaded and f.onedrive_uploaded_at is None)
                )

                f.onedrive_status_code = code
                f.onedrive_status_label = label
                f.onedrive_last_checked_at = datetime.utcnow()
                if is_uploaded and f.onedrive_uploaded_at is None:
                    f.onedrive_uploaded_at = datetime.utcnow()

                if changed:
                    db.add(f)
                    db.commit()
                    await manager.send_onedrive_status_update(
                        file_id=f.id,
                        status_code=code,
                        status_label=label,
                        is_uploaded=is_uploaded,
                        is_downloaded=is_downloaded,
                        uploaded_at_iso=f.onedrive_uploaded_at.isoformat() if f.onedrive_uploaded_at else None,
                    )
                    logger.info(
                        f"OneDrive status updated for {f.filename}: {code} ({label}); "
                        f"uploaded_at={f.onedrive_uploaded_at}"
                    )
        except Exception:
            logger.exception("OneDriveDetector check failed")
        finally:
            db.close()

    async def start(self):
        if self._running:
            return
        self._running = True
        logger.info("OneDriveDetector starting")
        # Initial small delay to let app settle
        await asyncio.sleep(0.5)
        try:
            while self._running:
                await self._check_once()
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            logger.info("OneDriveDetector cancelled")
        finally:
            self._running = False

    async def stop(self):
        self._running = False
        logger.info("OneDriveDetector stopped")


# Global instance
onedrive_detector = OneDriveDetector(interval_seconds=15.0)
