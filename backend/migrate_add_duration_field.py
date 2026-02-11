"""
Migration: Add duration field to files table

This adds a duration column to track video duration in seconds,
which is used to calculate bitrate for empty file detection.
"""

from database import engine, SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add duration column to files table"""
    db = SessionLocal()
    try:
        # Check if column already exists
        result = db.execute(text(
            "SELECT COUNT(*) FROM pragma_table_info('files') WHERE name='duration'"
        )).scalar()
        
        if result > 0:
            logger.info("✅ Duration column already exists - skipping migration")
            return
        
        # Add duration column
        logger.info("Adding duration column to files table...")
        db.execute(text(
            "ALTER TABLE files ADD COLUMN duration REAL"
        ))
        db.commit()
        
        logger.info("✅ Successfully added duration column")
        logger.info("   Files will now track video duration for bitrate calculation")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
