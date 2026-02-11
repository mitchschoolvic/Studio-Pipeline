"""
Database migration: Add OneDrive verification fields to files table

Adds to files table:
- onedrive_status_code (TEXT)
- onedrive_status_label (TEXT)
- onedrive_uploaded_at (DATETIME)
- onedrive_last_checked_at (DATETIME)

Usage:
    python backend/migrate_add_onedrive_fields.py
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate() -> bool:
    # Use the same DB location as database.py
    db_path = Path.home() / "Library/Application Support/StudioPipeline/pipeline.db"

    if not db_path.exists():
        logger.warning(f"Database not found at {db_path}, creating directory and initializing...")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info("Database will be created on first run with new schema")
        return True

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(files)")
        columns = {row[1] for row in cursor.fetchall()}

        migrations: list[str] = []
        if "onedrive_status_code" not in columns:
            migrations.append("ALTER TABLE files ADD COLUMN onedrive_status_code TEXT")
        if "onedrive_status_label" not in columns:
            migrations.append("ALTER TABLE files ADD COLUMN onedrive_status_label TEXT")
        if "onedrive_uploaded_at" not in columns:
            migrations.append("ALTER TABLE files ADD COLUMN onedrive_uploaded_at DATETIME")
        if "onedrive_last_checked_at" not in columns:
            migrations.append("ALTER TABLE files ADD COLUMN onedrive_last_checked_at DATETIME")

        if not migrations:
            logger.info("✅ OneDrive columns already exist; no migration needed")
            return True

        for sql in migrations:
            logger.info(f"Executing: {sql}")
            cursor.execute(sql)

        conn.commit()
        logger.info(f"✅ Successfully added {len(migrations)} column(s) to files table")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate()
    raise SystemExit(0 if success else 1)
