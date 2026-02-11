"""
Migration: Add Failure Recovery Tracking Fields

Adds columns to the files table to support intelligent failure recovery:
- failure_category: Categorizes the type of failure for recovery logic
- failure_job_kind: Which pipeline stage failed (COPY, PROCESS, ORGANIZE)
- failed_at: Timestamp when the failure occurred
- retry_after: Earliest time to retry (for backoff logic)
- recovery_attempts: Counter for recovery orchestrator attempts

Run this migration manually:
    cd backend
    python migrate_add_recovery_fields.py
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from database import engine, SessionLocal
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a table (SQLite)"""
    result = conn.execute(text(f"PRAGMA table_info({table})"))
    columns = [row[1] for row in result.fetchall()]
    return column in columns


def upgrade():
    """Add failure recovery tracking columns to files table"""
    logger.info("Starting migration: add_recovery_fields")
    
    conn = engine.connect()
    
    try:
        # Check and add failure_category
        if not check_column_exists(conn, 'files', 'failure_category'):
            logger.info("Adding column: failure_category")
            conn.execute(text(
                "ALTER TABLE files ADD COLUMN failure_category VARCHAR(50)"
            ))
        else:
            logger.info("Column failure_category already exists")
        
        # Check and add failure_job_kind
        if not check_column_exists(conn, 'files', 'failure_job_kind'):
            logger.info("Adding column: failure_job_kind")
            conn.execute(text(
                "ALTER TABLE files ADD COLUMN failure_job_kind VARCHAR(20)"
            ))
        else:
            logger.info("Column failure_job_kind already exists")
        
        # Check and add failed_at
        if not check_column_exists(conn, 'files', 'failed_at'):
            logger.info("Adding column: failed_at")
            conn.execute(text(
                "ALTER TABLE files ADD COLUMN failed_at DATETIME"
            ))
        else:
            logger.info("Column failed_at already exists")
        
        # Check and add retry_after
        if not check_column_exists(conn, 'files', 'retry_after'):
            logger.info("Adding column: retry_after")
            conn.execute(text(
                "ALTER TABLE files ADD COLUMN retry_after DATETIME"
            ))
        else:
            logger.info("Column retry_after already exists")
        
        # Check and add recovery_attempts
        if not check_column_exists(conn, 'files', 'recovery_attempts'):
            logger.info("Adding column: recovery_attempts")
            conn.execute(text(
                "ALTER TABLE files ADD COLUMN recovery_attempts INTEGER DEFAULT 0"
            ))
        else:
            logger.info("Column recovery_attempts already exists")
        
        conn.commit()
        logger.info("✅ Migration completed successfully")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def backfill_existing_failures():
    """
    Backfill failure_category for existing FAILED files.
    
    Uses heuristics based on error_message to classify existing failures.
    """
    logger.info("Backfilling existing FAILED files...")
    
    db = SessionLocal()
    
    try:
        from models import File
        from services.failure_classifier import FailureClassifier
        from constants.failure_categories import FailureCategory
        from datetime import datetime
        
        # Get all failed files without failure_category
        failed_files = db.query(File).filter(
            File.state == 'FAILED',
            File.failure_category == None
        ).all()
        
        if not failed_files:
            logger.info("No failed files to backfill")
            return
        
        logger.info(f"Found {len(failed_files)} failed files to backfill")
        
        for file in failed_files:
            # Try to determine failure category from error message
            if file.error_message:
                # Create a mock exception to classify
                mock_error = Exception(file.error_message)
                
                # Guess the job kind based on file state history
                # Files that never got a path_local probably failed during COPY
                if not file.path_local:
                    job_kind = 'COPY'
                elif not file.path_processed:
                    job_kind = 'PROCESS'
                else:
                    job_kind = 'ORGANIZE'
                
                category, _ = FailureClassifier.classify(mock_error, job_kind)
                
                file.failure_category = category.value
                file.failure_job_kind = job_kind
                file.failed_at = file.updated_at or datetime.utcnow()
                file.recovery_attempts = 0
                
                logger.info(f"Backfilled {file.filename}: {category.value} ({job_kind})")
            else:
                # No error message - classify as UNKNOWN
                file.failure_category = FailureCategory.UNKNOWN.value
                file.failure_job_kind = 'COPY'  # Assume earliest stage
                file.failed_at = file.updated_at or datetime.utcnow()
                file.recovery_attempts = 0
                
                logger.info(f"Backfilled {file.filename}: UNKNOWN (no error message)")
        
        db.commit()
        logger.info(f"✅ Backfilled {len(failed_files)} files")
        
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Add failure recovery tracking fields")
    parser.add_argument("--backfill", action="store_true", help="Also backfill existing failed files")
    args = parser.parse_args()
    
    upgrade()
    
    if args.backfill:
        backfill_existing_failures()
    else:
        logger.info("Tip: Run with --backfill to categorize existing FAILED files")
