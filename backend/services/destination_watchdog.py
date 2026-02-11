"""
Destination Watchdog Service

Watches the output directory for file create/delete/move events and
broadcasts destination presence changes over WebSocket so the UI updates live.

Requires dependency: watchdog
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional
import logging

from sqlalchemy.orm import Session

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except Exception:  # pragma: no cover
    Observer = None
    FileSystemEventHandler = object  # type: ignore

from database import SessionLocal
from models import File
from services.websocket import manager

logger = logging.getLogger(__name__)


def _canon(p: str | Path) -> str:
    try:
        return str(Path(p).expanduser().resolve())
    except Exception:
        return str(Path(p).expanduser())


class _PresenceHandler(FileSystemEventHandler):
    def __init__(self, root: Path, loop, debounce_ms: int = 150):
        super().__init__()
        self.root = root
        self.loop = loop
        self._recent: set[str] = set()
        self._lock = threading.Lock()
        self._debounce_ms = debounce_ms

    def _touch(self, path: str) -> bool:
        # Debounce bursts for same path
        with self._lock:
            if path in self._recent:
                return False
            self._recent.add(path)
        def _clear():
            with self._lock:
                self._recent.discard(path)
        timer = threading.Timer(self._debounce_ms / 1000.0, _clear)
        timer.daemon = True
        timer.start()
        return True

    def _handle_path(self, abs_path: str, exists_now: bool):
        if not abs_path.lower().endswith(('.mp4', '.mov', '.mkv', '.m4v')):
            return
        if not self._touch(abs_path):
            logger.debug(f"🔇 Debounced: {abs_path}")
            return
        logger.info(f"📂 Handling path: {abs_path}, exists={exists_now}")
        # Lookup file by path_final
        db: Session = SessionLocal()
        try:
            file: Optional[File] = db.query(File).filter(File.path_final == abs_path).first()
            if not file:
                logger.debug(f"📭 No file found in DB for: {abs_path}")
                return
            logger.info(f"📡 Broadcasting destination_presence_change for file_id={file.id}, final_exists={exists_now}")
            # Broadcast to clients
            payload = {
                "type": "destination_presence_change",
                "data": {
                    "file_id": file.id,
                    "final_exists": bool(exists_now),
                },
            }
            # Use loop thread-safe call
            import asyncio
            asyncio.run_coroutine_threadsafe(manager.broadcast(payload), self.loop)
        except Exception as e:
            logger.warning(f"Watchdog handler error for {abs_path}: {e}")
        finally:
            db.close()

    # Created or modified file
    def on_created(self, event):  # type: ignore
        if event.is_directory:
            return
        # Ignore hidden dotfiles (e.g., OneDrive .write_test)
        try:
            if Path(event.src_path).name.startswith('.'):
                return
        except Exception:
            pass
        abs_path = _canon(event.src_path)
        self._handle_path(abs_path, True)

    def on_moved(self, event):  # type: ignore
        if event.is_directory:
            return
        try:
            if Path(event.dest_path).name.startswith('.') or Path(event.src_path).name.startswith('.'):
                return
        except Exception:
            pass
        dest_path = _canon(event.dest_path)
        self._handle_path(dest_path, True)
        # Source moved away; mark old path as missing too
        src_path = _canon(event.src_path)
        self._handle_path(src_path, Path(src_path).exists())

    def on_deleted(self, event):  # type: ignore
        if event.is_directory:
            return
        try:
            if Path(event.src_path).name.startswith('.'):
                return
        except Exception:
            pass
        abs_path = _canon(event.src_path)
        self._handle_path(abs_path, False)


class DestinationWatchdog:
    def __init__(self, output_root: str):
        self.output_root = Path(output_root).expanduser()
        self.observer: Optional[Observer] = None
        self._thread: Optional[threading.Thread] = None
        self._loop = None

    async def start(self):
        if Observer is None:
            logger.warning("watchdog not installed; destination presence will not update live")
            return
        if not self.output_root.exists():
            try:
                self.output_root.mkdir(parents=True, exist_ok=True)
            except Exception:
                logger.warning(f"Output root does not exist and cannot be created: {self.output_root}")
        # Capture current loop for cross-thread notifications
        import asyncio
        self._loop = asyncio.get_running_loop()

        handler = _PresenceHandler(self.output_root, self._loop)
        self.observer = Observer()
        self.observer.schedule(handler, str(self.output_root), recursive=True)
        self.observer.start()
        logger.info(f"DestinationWatchdog started on {self.output_root}")

    async def stop(self):
        try:
            if self.observer:
                self.observer.stop()
                self.observer.join(timeout=3)
                logger.info("DestinationWatchdog stopped")
        except Exception as e:
            logger.warning(f"Failed to stop DestinationWatchdog: {e}")
        finally:
            self.observer = None
            self._loop = None


# Factory to create from DB settings
async def start_destination_watchdog_from_db() -> DestinationWatchdog | None:
    """Create and start the watchdog using OUTPUT_PATH from settings."""
    db = SessionLocal()
    try:
        from models import Setting
        from constants import SettingKeys
        setting = db.query(Setting).filter(Setting.key == SettingKeys.OUTPUT_PATH).first()
        output_root = setting.value if setting and setting.value else str(Path.home() / 'Videos' / 'StudioPipeline')
    finally:
        db.close()

    watcher = DestinationWatchdog(output_root)
    await watcher.start()
    return watcher
