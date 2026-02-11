"""
Migration: Add waveform tracking fields

Adds fields to the files table for tracking waveform generation status
for kiosk video playback feature.
"""

import logging
from sqlalchemy import text
from database import engine

logger = logging.getLogger(__name__)


def run_migration():
    """Add waveform tracking columns to files table."""
    
    new_columns = [
        ("waveform_path", "VARCHAR"),
        ("waveform_state", "VARCHAR DEFAULT 'PENDING'"),
        ("waveform_generated_at", "DATETIME"),
        ("waveform_error", "TEXT"),
    ]
    
    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            try:
                conn.execute(text(f"ALTER TABLE files ADD COLUMN {col_name} {col_type}"))
                conn.commit()
                logger.info(f"✅ Added column: files.{col_name}")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"Column files.{col_name} already exists")
                else:
                    logger.warning(f"Could not add files.{col_name}: {e}")
    
    logger.info("Waveform migration complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
