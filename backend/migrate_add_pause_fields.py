"""
Database migration: Add pause/cancellation tracking fields to jobs table

Adds:
- is_cancellable: Boolean flag indicating if job is currently running and can be cancelled
- cancellation_requested: Boolean flag set when user requests pause during execution
- checkpoint_state: String storing the target state to reset to if cancelled

Usage:
    python backend/migrate_add_pause_fields.py
"""
import sqlite3
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add pause/cancellation fields to jobs table"""
    # Use same path as database.py
    db_path = Path.home() / "Library/Application Support/StudioPipeline/pipeline.db"
    
    if not db_path.exists():
        logger.warning(f"Database not found at {db_path}, creating directory and initializing...")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Database will be created when the app starts, so we'll just note this
        logger.info("Database will be created on first run with new schema")
        return True
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in cursor.fetchall()]
        
        migrations_needed = []
        
        if 'is_cancellable' not in columns:
            migrations_needed.append(
                "ALTER TABLE jobs ADD COLUMN is_cancellable BOOLEAN DEFAULT 0"
            )
        
        if 'cancellation_requested' not in columns:
            migrations_needed.append(
                "ALTER TABLE jobs ADD COLUMN cancellation_requested BOOLEAN DEFAULT 0"
            )
        
        if 'checkpoint_state' not in columns:
            migrations_needed.append(
                "ALTER TABLE jobs ADD COLUMN checkpoint_state TEXT"
            )
        
        if not migrations_needed:
            logger.info("✅ All columns already exist, no migration needed")
            return True
        
        # Execute migrations
        for sql in migrations_needed:
            logger.info(f"Executing: {sql}")
            cursor.execute(sql)
        
        conn.commit()
        logger.info(f"✅ Successfully added {len(migrations_needed)} column(s) to jobs table")
        
        # Verify
        cursor.execute("PRAGMA table_info(jobs)")
        columns = [row[1] for row in cursor.fetchall()]
        logger.info(f"Jobs table now has columns: {', '.join(columns)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        return False
    
    finally:
        conn.close()

if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
