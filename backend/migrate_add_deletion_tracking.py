"""
Database migration: Add deletion tracking fields to files table

Adds to files table:
- marked_for_deletion_at (DATETIME)
- deleted_at (DATETIME)
- deletion_error (TEXT)
- deletion_attempted_at (DATETIME)

Usage:
    python backend/migrate_add_deletion_tracking.py
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
        if "marked_for_deletion_at" not in columns:
            migrations.append("ALTER TABLE files ADD COLUMN marked_for_deletion_at DATETIME")
        if "deleted_at" not in columns:
            migrations.append("ALTER TABLE files ADD COLUMN deleted_at DATETIME")
        if "deletion_error" not in columns:
            migrations.append("ALTER TABLE files ADD COLUMN deletion_error TEXT")
        if "deletion_attempted_at" not in columns:
            migrations.append("ALTER TABLE files ADD COLUMN deletion_attempted_at DATETIME")

        if not migrations:
            logger.info("✅ Deletion tracking columns already exist; no migration needed")
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
