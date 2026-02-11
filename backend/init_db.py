from database import engine, Base, SessionLocal
from models import Setting
from constants import SettingKeys
from pathlib import Path
from config.ai_config import AI_ENABLED
from sqlalchemy import inspect, text
import logging

logger = logging.getLogger(__name__)


def _check_column_exists(inspector, table: str, column: str) -> bool:
    """Check if a column exists in a table"""
    try:
        columns = [col['name'] for col in inspector.get_columns(table)]
        return column in columns
    except Exception:
        return False


def _add_column_if_missing(inspector, table: str, column: str, column_def: str):
    """Add a column to a table if it doesn't exist"""
    if not _check_column_exists(inspector, table, column):
        logger.info(f"Running migration: Adding '{column}' column to {table} table...")
        with engine.connect() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}"))
            conn.commit()
        logger.info(f"✅ Migration complete: '{column}' column added to {table}")
        return True
    return False


def _run_essential_migrations():
    """
    Run essential schema migrations that are required for the app to function.
    These migrations are safe to run automatically on startup.
    
    This function checks for all required columns and adds any that are missing,
    ensuring older databases are automatically upgraded to the current schema.
    """
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    migrations_run = 0
    
    # ============================================================
    # Sessions table migrations
    # ============================================================
    if 'sessions' in tables:
        # Migration: Add 'campus' column (added: v1.2)
        if _add_column_if_missing(inspector, 'sessions', 'campus', "TEXT DEFAULT 'Keysborough'"):
            migrations_run += 1
    
    # ============================================================
    # Files table migrations
    # ============================================================
    if 'files' in tables:
        # Migration: Add 'queue_order' column (added: v1.1)
        if _add_column_if_missing(inspector, 'files', 'queue_order', "INTEGER"):
            migrations_run += 1
        
        # Migration: Add 'duration' column for bitrate calculation (added: v1.2)
        if _add_column_if_missing(inspector, 'files', 'duration', "REAL"):
            migrations_run += 1
        
        # Migration: Add directory structure fields (added: v1.2)
        if _add_column_if_missing(inspector, 'files', 'session_folder', "TEXT"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'relative_path', "TEXT"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'parent_file_id', "VARCHAR"):
            migrations_run += 1
        
        # Migration: Add thumbnail fields (added: v1.3)
        if _add_column_if_missing(inspector, 'files', 'thumbnail_path', "VARCHAR"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'thumbnail_state', "VARCHAR DEFAULT 'PENDING'"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'thumbnail_generated_at', "DATETIME"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'thumbnail_error', "TEXT"):
            migrations_run += 1
        
        # Migration: Add processing stage tracking fields (added: v1.3)
        if _add_column_if_missing(inspector, 'files', 'processing_stage', "TEXT"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'processing_stage_progress', "INTEGER DEFAULT 0"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'processing_detail', "TEXT"):
            migrations_run += 1
        
        # Migration: Add OneDrive verification fields (added: v1.4)
        if _add_column_if_missing(inspector, 'files', 'onedrive_status_code', "TEXT"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'onedrive_status_label', "TEXT"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'onedrive_uploaded_at', "DATETIME"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'onedrive_last_checked_at', "DATETIME"):
            migrations_run += 1
        
        # Migration: Add deletion tracking fields (added: v1.4)
        if _add_column_if_missing(inspector, 'files', 'marked_for_deletion_at', "DATETIME"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'deleted_at', "DATETIME"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'deletion_error', "TEXT"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'deletion_attempted_at', "DATETIME"):
            migrations_run += 1
        
        # Migration: Add MP3 temp path field (added: v1.5)
        if _add_column_if_missing(inspector, 'files', 'mp3_temp_path', "TEXT"):
            migrations_run += 1
        
        # Migration: Add external export path field (added: v1.6)
        if _add_column_if_missing(inspector, 'files', 'external_export_path', "TEXT"):
            migrations_run += 1
        
        # Migration: Add gesture trim tracking fields (added: v1.8)
        if _add_column_if_missing(inspector, 'files', 'gesture_trimmed', "BOOLEAN DEFAULT 0"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'gesture_trim_skipped', "BOOLEAN DEFAULT 0"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'gesture_trim_point', "REAL"):
            migrations_run += 1
        
        # Migration: Add failure recovery tracking fields (added: v1.7)
        if _add_column_if_missing(inspector, 'files', 'failure_category', "VARCHAR(50)"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'failure_job_kind', "VARCHAR(20)"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'failed_at', "DATETIME"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'retry_after', "DATETIME"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'recovery_attempts', "INTEGER DEFAULT 0"):
            migrations_run += 1
        
        # Migration: Add waveform tracking fields for kiosk view (added: v1.9)
        if _add_column_if_missing(inspector, 'files', 'waveform_path', "VARCHAR"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'waveform_state', "VARCHAR DEFAULT 'PENDING'"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'waveform_generated_at', "DATETIME"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'files', 'waveform_error', "TEXT"):
            migrations_run += 1
    
    # ============================================================
    # Jobs table migrations
    # ============================================================
    if 'jobs' in tables:
        # Migration: Add pause/cancellation tracking fields (added: v1.3)
        if _add_column_if_missing(inspector, 'jobs', 'is_cancellable', "BOOLEAN DEFAULT 0"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'jobs', 'cancellation_requested', "BOOLEAN DEFAULT 0"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'jobs', 'checkpoint_state', "TEXT"):
            migrations_run += 1
        
        # Migration: Add heartbeat tracking fields for stale job detection (added: v1.8)
        if _add_column_if_missing(inspector, 'jobs', 'last_heartbeat', "DATETIME"):
            migrations_run += 1
        if _add_column_if_missing(inspector, 'jobs', 'worker_id', "VARCHAR(50)"):
            migrations_run += 1
    
    if migrations_run > 0:
        logger.info(f"✅ Database schema updated: {migrations_run} migration(s) applied")
    else:
        logger.debug("Database schema is up to date")
    
    return migrations_run


def init_database():
    """Create all tables and insert default settings"""
    Base.metadata.create_all(bind=engine)

    # Run essential migrations that are safe to auto-apply
    try:
        _run_essential_migrations()
    except Exception as e:
        logger.warning(f"Migration warning (non-fatal): {e}")

    db = SessionLocal()
    try:
        # Insert default settings if not exists
        defaults = {
            'ftp_host': 'atem.studio.local',
            'ftp_port': '21',
            'ftp_anonymous': 'true',
            'ftp_username': 'anonymous',
            'ftp_password_encrypted': '',
            'source_path': '/ATEM/recordings',
            SettingKeys.FTP_EXCLUDE_FOLDERS: '',  # Comma-separated list of folders to exclude
            'temp_path': '/tmp/pipeline',
            'output_path': '~/Videos/StudioPipeline',
            'max_concurrent_copy': '1',
            'max_concurrent_process': '1',
            'ftp_check_interval': '5',  # Check FTP every 5 seconds for new/missing files
            # Pause processing pipeline (when 'true', PROCESS and ORGANIZE workers should not start new jobs)
            'pause_processing': 'false',
            # Minimum ISO file size in MB (files smaller than this will be skipped)
            'iso_min_size_mb': '50',
            # Minimum bitrate in kbps for valid files (files below this will be marked as empty)
            'bitrate_threshold_kbps': '500',
            # Session defaults
            SettingKeys.CAMPUS: 'Keysborough',
            # OneDrive detection defaults
            SettingKeys.ONEDRIVE_DETECTION_ENABLED: 'true',
            # Common macOS default; can be overridden by user in settings
            SettingKeys.ONEDRIVE_ROOT: str((Path.home() / 'Library/CloudStorage').resolve()),
            # Auto-deletion defaults
            SettingKeys.AUTO_DELETE_ENABLED: 'false',
            SettingKeys.AUTO_DELETE_AGE_MONTHS: '12',
            # External audio export defaults
            SettingKeys.EXTERNAL_AUDIO_EXPORT_ENABLED: 'false',
            SettingKeys.EXTERNAL_AUDIO_EXPORT_PATH: '',
            # AI Analytics defaults
            SettingKeys.PAUSE_ANALYTICS: 'false',  # Unpaused by default
            SettingKeys.RUN_ANALYTICS_WHEN_IDLE: 'true',  # Only run when pipeline is idle
            # Network defaults
            SettingKeys.SERVER_HOST: '0.0.0.0',  # Listen on all interfaces by default
        }
        
        for key, value in defaults.items():
            existing = db.query(Setting).filter(Setting.key == key).first()
            if not existing:
                db.add(Setting(key=key, value=value))
        
        db.commit()

        # Initialize AI config defaults if AI is enabled
        if AI_ENABLED:
            try:
                from services.ai_config_service import AIConfigService
                ai_config = AIConfigService(db)
                ai_config.initialize_defaults()
                logger.info("✅ AI configuration defaults initialized")
            except Exception as e:
                logger.warning(f"AI config initialization failed: {e}")

        print("✅ Database initialized successfully")
    finally:
        db.close()

if __name__ == "__main__":
    init_database()
