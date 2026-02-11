from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from database import Base, engine, get_db, SessionLocal
from init_db import init_database
from api import settings, sessions, files, discovery, jobs, thumbnails, workers, dev_queue
from api import waveforms, videos
from services.websocket import websocket_endpoint
from services.destination_watchdog import start_destination_watchdog_from_db
from services.onedrive_detector import onedrive_detector
from services.reconciler import reconciler
from services.worker_pool import worker_pool
from models import Job, File, Event
from config.ai_config import AI_ENABLED
from services.ai_mutex import set_shutting_down
from services.schema_validator import SchemaValidator
import signal

if AI_ENABLED:
    from api.analytics import router as analytics_router
    from services.analytics_scheduler import start_scheduler, stop_scheduler
from datetime import datetime, timedelta
import asyncio
import logging
from logging.handlers import RotatingFileHandler
import json
import os
import sys
from pathlib import Path

# Configure logging with rotating file handler
LOG_DIR = Path.home() / "Library/Application Support/StudioPipeline/logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "backend.log"

# Create formatters and handlers
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler with rotation (10MB per file, keep 5 backups)
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

# Configure root logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.info(f"Logging initialized: {LOG_FILE}")

# Initialize database on startup
init_database()

# Global task references
_reconciler_task = None
_worker_pool_task = None
_dest_watcher = None
_onedrive_task = None
_deletion_cleanup_task = None

# App State
class AppState:
    NORMAL = "NORMAL"
    MAINTENANCE = "MAINTENANCE"

CURRENT_APP_STATE = AppState.NORMAL
SCHEMA_STATUS = {"valid": True, "issues": []}


async def reset_stale_jobs():
    """
    Reset jobs that were left in RUNNING state from a previous run.
    This handles the case where the backend was interrupted mid-processing.
    """
    db = next(get_db())
    try:
        # Find all jobs stuck in RUNNING state
        stale_jobs = db.query(Job).filter(Job.state == 'RUNNING').all()

        if not stale_jobs:
            logger.info("No stale jobs found")
            return

        logger.warning(f"Found {len(stale_jobs)} stale job(s) in RUNNING state - resetting...")

        for job in stale_jobs:
            file = job.file

            # Reset job to QUEUED state
            job.state = 'QUEUED'
            job.progress_pct = 0
            job.progress_stage = None
            job.started_at = None

            # Reset file to appropriate state based on job kind
            if job.kind == 'COPY':
                file.state = 'DISCOVERED'
            elif job.kind == 'PROCESS':
                file.state = 'COPIED'
            elif job.kind == 'ORGANIZE':
                file.state = 'PROCESSED'

            logger.info(f"Reset stale {job.kind} job for file: {file.filename} (was at {job.progress_pct:.1f}%)")

            # Create event to notify frontend
            event = Event(
                file_id=file.id,
                event_type='file_state_change',
                payload_json=json.dumps({
                    'filename': file.filename,
                    'state': file.state,
                    'progress_pct': 0,
                    'message': 'Job reset after interruption'
                })
            )
            db.add(event)

        db.commit()
        logger.info(f"Successfully reset {len(stale_jobs)} stale job(s)")

    except Exception as e:
        logger.error(f"Error resetting stale jobs: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()


async def deletion_cleanup_loop():
    """
    Background task to delete files from FTP server that have been marked for 7+ days.
    Also marks old files for deletion based on age settings.
    Runs every hour.
    """
    from services.ftp_deletion_service import FTPDeletionService
    from services.auto_deletion_service import AutoDeletionService

    logger.info("Deletion cleanup service started - will run every hour")

    # Track when we last ran auto-deletion marking (run once per day)
    last_auto_mark_date = None

    while True:
        try:
            # Wait 1 hour between runs
            await asyncio.sleep(3600)  # 1 hour

            logger.info("Running scheduled deletion cleanup...")
            db = next(get_db())
            try:
                # Auto-mark old files once per day
                today = datetime.utcnow().date()
                if last_auto_mark_date != today:
                    logger.info("Running daily auto-deletion marking...")
                    auto_service = AutoDeletionService(db)
                    marked_count, enabled = auto_service.mark_old_files_for_deletion()

                    if enabled:
                        if marked_count > 0:
                            logger.info(f"Auto-deletion: marked {marked_count} old files for deletion")
                        else:
                            logger.info("Auto-deletion: no old files to mark")

                    last_auto_mark_date = today

                # Delete files marked for 7+ days
                deletion_service = FTPDeletionService(db)
                success_count, failure_count = deletion_service.delete_files_marked_for_days(days=7)

                if success_count > 0 or failure_count > 0:
                    logger.info(f"Deletion cleanup complete: {success_count} deleted, {failure_count} failed")
                else:
                    logger.info("Deletion cleanup complete: no files ready for deletion")

            except Exception as e:
                logger.error(f"Error during deletion cleanup: {e}", exc_info=True)
            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("Deletion cleanup service stopping...")
            break
        except Exception as e:
            logger.error(f"Unexpected error in deletion cleanup loop: {e}", exc_info=True)
            # Continue running despite errors
            await asyncio.sleep(60)  # Wait 1 minute before retrying



async def _backfill_waveforms():
    """Backfill waveforms for completed program files that are missing them."""
    from services.waveform_generator import WaveformGenerator
    from pathlib import Path
    
    # Small delay to let other services start first
    await asyncio.sleep(3)
    
    waveform_dir = Path.home() / "Library/Application Support/StudioPipeline/waveforms"
    waveform_dir.mkdir(parents=True, exist_ok=True)
    
    db = SessionLocal()
    try:
        # Also fix any READY files whose waveform_path no longer exists on disk
        ready_files = db.query(File).filter(
            File.waveform_state == 'READY',
            File.waveform_path.isnot(None),
        ).all()
        
        reset_count = 0
        for f in ready_files:
            if not Path(f.waveform_path).exists():
                f.waveform_state = 'PENDING'
                f.waveform_path = None
                f.waveform_error = None
                reset_count += 1
        if reset_count:
            db.commit()
            logger.info(f"Reset {reset_count} waveforms with missing files back to PENDING")
        
        # Find all files needing waveforms
        pending_files = db.query(File).filter(
            File.is_program_output == True,
            File.state == 'COMPLETED',
            File.waveform_state.in_(['PENDING', 'FAILED']),
        ).all()
        
        if not pending_files:
            logger.info("Waveform backfill: all waveforms up to date")
            return
        
        logger.info(f"Waveform backfill: {len(pending_files)} files need waveforms")
        generator = WaveformGenerator(str(waveform_dir))
        generated = 0
        skipped = 0
        
        for file in pending_files:
            audio_path = None
            for candidate in [file.path_final, file.path_processed]:
                if candidate and Path(candidate).exists():
                    audio_path = candidate
                    break
            
            if not audio_path:
                skipped += 1
                continue
            
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None, generator.generate_waveform, file.id, audio_path, db
            )
            if success:
                generated += 1
                # Send WebSocket update
                try:
                    from services.websocket import manager
                    await manager.send_waveform_update(file.id, 'READY')
                except Exception:
                    pass
            
            # Yield to event loop between files
            await asyncio.sleep(0.1)
        
        logger.info(f"✅ Waveform backfill complete: generated {generated}/{len(pending_files)} ({skipped} skipped - files not on disk)")
    except Exception as e:
        logger.error(f"Waveform backfill failed: {e}", exc_info=True)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown"""
    global _reconciler_task, _worker_pool_task, _onedrive_task, _deletion_cleanup_task

    # Startup
    logger.info("Starting background services...")

    # 1. Validate Database Schema
    global CURRENT_APP_STATE, SCHEMA_STATUS
    SCHEMA_STATUS = SchemaValidator.check()
    
    if not SCHEMA_STATUS["valid"]:
        logger.error("❌ Database schema validation failed - Entering MAINTENANCE MODE")
        CURRENT_APP_STATE = AppState.MAINTENANCE
        # In maintenance mode, we DO NOT start background workers to prevent crashes
    else:
        logger.info("✅ Database schema valid - Starting services")
        CURRENT_APP_STATE = AppState.NORMAL

        # Reset stale jobs before starting workers
        await reset_stale_jobs()

        # Pre-warm matplotlib font cache in background thread
        # MediaPipe imports matplotlib which triggers a ~14s font cache rebuild
        # on first use. Doing this at startup prevents stalling the first gesture detection.
        async def _prewarm_ml_dependencies():
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: __import__('matplotlib.font_manager', fromlist=['fontManager']).fontManager
                )
                logger.info("✅ Matplotlib font cache pre-warmed")
            except Exception as e:
                logger.debug(f"Matplotlib pre-warm skipped: {e}")

        asyncio.create_task(_prewarm_ml_dependencies())

        # Start reconciler in background
        _reconciler_task = asyncio.create_task(reconciler.start())

        # Start worker pool
        _worker_pool_task = asyncio.create_task(worker_pool.start())

        # Start destination filesystem watchdog for live presence updates
        global _dest_watcher
        try:
            _dest_watcher = await start_destination_watchdog_from_db()
        except Exception as e:
            logger.warning(f"Could not start destination watchdog: {e}")

        # Start OneDrive detector (macOS only; internally checks enable flag)
        try:
            _onedrive_task = asyncio.create_task(onedrive_detector.start())
        except Exception as e:
            logger.warning(f"Could not start OneDrive detector: {e}")

        # Start deletion cleanup service
        try:
            _deletion_cleanup_task = asyncio.create_task(deletion_cleanup_loop())
        except Exception as e:
            logger.warning(f"Could not start deletion cleanup service: {e}")

        # Backfill waveforms for completed files missing them
        try:
            asyncio.create_task(_backfill_waveforms())
        except Exception as e:
            logger.warning(f"Could not start waveform backfill: {e}")

        # Start analytics scheduler if enabled
        if AI_ENABLED:
            try:
                start_scheduler()
                logger.info("✅ Analytics scheduler started")
            except Exception as e:
                logger.warning(f"Could not start analytics scheduler: {e}")

    # Give them a moment to start
    await asyncio.sleep(0.1)
    if CURRENT_APP_STATE == AppState.MAINTENANCE:
        logger.warning("⚠️  Application started in MAINTENANCE MODE - Waiting for user action")
    else:
        logger.info("Application startup complete - all services running")

    # Keep application running
    yield

    # Signal shutdown early to prevent new GPU work
    try:
        set_shutting_down()
        logger.info("🔻 Shutdown signal set - blocking new GPU operations")
    except Exception as e:
        logger.warning(f"Failed to set shutdown signal: {e}")

    # Shutdown
    logger.info("Stopping background services...")

    # Stop reconciler
    await reconciler.stop()
    if _reconciler_task and not _reconciler_task.done():
        _reconciler_task.cancel()
        try:
            await _reconciler_task
        except asyncio.CancelledError:
            logger.info("Reconciler task cancelled successfully")

    # Stop worker pool
    await worker_pool.stop()
    if _worker_pool_task and not _worker_pool_task.done():
        _worker_pool_task.cancel()
        try:
            await _worker_pool_task
        except asyncio.CancelledError:
            logger.info("WorkerPool task cancelled successfully")

    # Stop destination watchdog
    if _dest_watcher:
        try:
            await _dest_watcher.stop()
        except Exception as e:
            logger.warning(f"Failed to stop destination watchdog: {e}")
        finally:
            _dest_watcher = None

    # Stop OneDrive detector
    if _onedrive_task and not _onedrive_task.done():
        _onedrive_task.cancel()
        try:
            await _onedrive_task
        except asyncio.CancelledError:
            logger.info("OneDrive detector task cancelled successfully")
    await onedrive_detector.stop()

    # Stop deletion cleanup service
    if _deletion_cleanup_task and not _deletion_cleanup_task.done():
        _deletion_cleanup_task.cancel()
        try:
            await _deletion_cleanup_task
        except asyncio.CancelledError:
            logger.info("Deletion cleanup task cancelled successfully")

    # Stop analytics scheduler if enabled
    if AI_ENABLED:
        try:
            stop_scheduler()
            logger.info("✅ Analytics scheduler stopped")
        except Exception as e:
            logger.warning(f"Failed to stop analytics scheduler: {e}")

    logger.info("Application shutdown complete")


app = FastAPI(
    title="Studio Pipeline API",
    description="Audio/Video processing pipeline for studio recordings",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS - allow all origins for network accessibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for LAN access
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(settings.router, prefix="/api", tags=["settings"])
app.include_router(sessions.router, prefix="/api", tags=["sessions"])
app.include_router(files.router, prefix="/api", tags=["files"])
app.include_router(discovery.router, prefix="/api/discovery", tags=["discovery"])
app.include_router(jobs.router, prefix="/api", tags=["jobs"])
app.include_router(thumbnails.router, prefix="/api", tags=["thumbnails"])
app.include_router(workers.router, tags=["workers"])
app.include_router(dev_queue.router, prefix="/api/dev-queue", tags=["dev-queue"])
app.include_router(waveforms.router, prefix="/api", tags=["waveforms"])
app.include_router(videos.router, prefix="/api", tags=["videos"])

# Analytics routes (if AI enabled)
if AI_ENABLED:
    app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
    logger.info("✅ Analytics API routes registered")


# System Status & Maintenance Endpoints

@app.get("/api/system/status")
def get_system_status():
    """Get current application state and schema status"""
    return {
        "state": CURRENT_APP_STATE,
        "schema_status": SCHEMA_STATUS
    }

@app.post("/api/maintenance/migrate")
def run_migration():
    """Run database migrations and restart services"""
    global CURRENT_APP_STATE, SCHEMA_STATUS
    
    try:
        logger.info("🔄 Starting manual migration...")
        
        # Run queue_order migration
        try:
            from migrate_add_queue_order import upgrade as upgrade_queue_order
            upgrade_queue_order()
            logger.info("✅ Queue order migration successful")
        except Exception as e:
            logger.error(f"Queue order migration failed: {e}")
            raise
            
        # Run analytics migration if enabled
        if AI_ENABLED:
            try:
                from add_analytics_table import upgrade as upgrade_analytics
                upgrade_analytics()
                logger.info("✅ Analytics migration successful")
            except Exception as e:
                logger.error(f"Analytics migration failed: {e}")
                raise
        
        # Re-validate schema
        SCHEMA_STATUS = SchemaValidator.check()
        
        if SCHEMA_STATUS["valid"]:
            logger.info("✅ Migration complete and verified. Please restart the application.")
            # We could try to hot-start services, but a restart is safer to ensure clean state
            # For now, we'll return success and let the frontend prompt for restart or just reload
            # Actually, we can try to update state to NORMAL, but services won't be running.
            # Best UX: Tell user to restart.
            return {"success": True, "message": "Migration successful. Please restart the application."}
        else:
            return {"success": False, "message": "Migration ran but schema is still invalid.", "issues": SCHEMA_STATUS["issues"]}
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise HTTPException(status_code=500, detail=f"Migration failed: {str(e)}")

@app.post("/api/maintenance/reset")
def reset_database_maintenance():
    """Clear database completely (Maintenance Mode version)"""
    # This is similar to the settings/clear endpoint but accessible during maintenance
    try:
        # We can reuse the logic from settings.clear_database, but we need to be careful about dependencies
        # Simpler approach: Just drop all tables and re-init
        Base.metadata.drop_all(bind=engine)
        init_database()
        
        # Run migrations on fresh DB
        from migrate_add_queue_order import upgrade as upgrade_queue_order
        upgrade_queue_order()
        
        if AI_ENABLED:
            from add_analytics_table import upgrade as upgrade_analytics
            upgrade_analytics()
            
        return {"success": True, "message": "Database reset successfully. Please restart the application."}
    except Exception as e:
        logger.error(f"Reset failed: {e}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")

@app.post("/api/maintenance/quit")
def quit_application():
    """Shutdown the application"""
    logger.info("👋 User requested shutdown from Maintenance Mode")
    
    # Schedule shutdown
    def shutdown():
        os.kill(os.getpid(), signal.SIGTERM)
        
    asyncio.get_event_loop().call_later(1, shutdown)
    return {"success": True, "message": "Shutting down..."}


@app.websocket("/api/ws")
async def websocket_route(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket_endpoint(websocket)


@app.get("/api/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "Studio Pipeline API",
        "version": "1.0.0"
    }


# Determine frontend directory path
def get_frontend_path():
    """Get the path to the frontend dist directory"""
    # Check if running from PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        base_path = Path(sys._MEIPASS)
        frontend_path = base_path / 'frontend'
    else:
        # Running in development
        base_path = Path(__file__).parent.parent
        frontend_path = base_path / 'frontend' / 'dist'

    if frontend_path.exists():
        logger.info(f"Frontend path found: {frontend_path}")
        return frontend_path
    else:
        logger.warning(f"Frontend path not found: {frontend_path}")
        return None


def get_swift_tools_path():
    """Get the path to the Swift tools directory"""
    # Check if running from PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        base_path = Path(sys._MEIPASS)
        swift_tools_path = base_path / 'swift_tools'
    else:
        # Running in development
        base_path = Path(__file__).parent.parent
        swift_tools_path = base_path / 'swift_tools'
    
    if swift_tools_path.exists():
        logger.info(f"Swift tools path found: {swift_tools_path}")
        return swift_tools_path
    else:
        logger.warning(f"Swift tools path not found: {swift_tools_path}")
        return None

# Mount static files if frontend exists
frontend_path = get_frontend_path()
if frontend_path:
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    @app.get("/")
    async def serve_frontend():
        """Serve the frontend index.html"""
        return FileResponse(str(frontend_path / "index.html"))
    
    @app.get("/kiosk")
    async def serve_kiosk():
        """Serve the frontend for kiosk route (SPA routing)"""
        return FileResponse(str(frontend_path / "index.html"))
else:
    @app.get("/")
    def root():
        """Root endpoint - API only mode"""
        return {
            "message": "Studio Pipeline API",
            "docs": "/docs",
            "health": "/api/health",
            "note": "Frontend not available - running in API-only mode"
        }

if __name__ == "__main__":
    import uvicorn
    import socket
    from constants import ServerConfig, SettingKeys
    from database import SessionLocal
    from models import Setting
    
    # Read bind host from database settings, fall back to ServerConfig.HOST
    def get_bind_host() -> str:
        try:
            db = SessionLocal()
            setting = db.query(Setting).filter(Setting.key == SettingKeys.SERVER_HOST).first()
            db.close()
            if setting and setting.value:
                return setting.value
        except Exception:
            pass
        return ServerConfig.HOST
    
    bind_host = get_bind_host()
    
    # Check if port is available
    def is_port_in_use(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((bind_host, port))
                return False
            except OSError:
                return True
    
    if is_port_in_use(ServerConfig.PORT):
        logger.error(f"❌ Port {ServerConfig.PORT} is already in use!")
        logger.error(f"   Another instance of Studio Pipeline may be running.")
        logger.error(f"   To fix: Run 'lsof -ti:{ServerConfig.PORT} | xargs kill -9'")
        sys.exit(1)
    
    logger.info(f"🚀 Starting Studio Pipeline on http://{bind_host}:{ServerConfig.PORT}...")
    uvicorn.run(app, host=bind_host, port=ServerConfig.PORT)
