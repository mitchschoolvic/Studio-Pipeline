"""
Migration: Add index on files.path_final for fast presence lookups

We add a non-unique index `idx_files_path_final` to accelerate mapping
from filesystem events (destination watcher) to DB rows.
"""
from database import SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate():
    db = SessionLocal()
    try:
        # Check if index exists (SQLite)
        existing = db.execute(text("PRAGMA index_list('files')")).fetchall()
        index_names = {row[1] for row in existing} if existing else set()
        if 'idx_files_path_final' in index_names:
            logger.info("✅ Index idx_files_path_final already exists - skipping migration")
            return

        logger.info("Creating index idx_files_path_final on files(path_final)...")
        db.execute(text("CREATE INDEX idx_files_path_final ON files(path_final)"))
        db.commit()
        logger.info("✅ Successfully created index idx_files_path_final")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
