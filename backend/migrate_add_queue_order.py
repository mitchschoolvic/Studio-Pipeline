"""
Database migration: Add queue_order column to files table
"""
from sqlalchemy import text, inspect
from database import engine as db_engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def column_exists(engine, table_name, column_name):
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def upgrade():
    """Add queue_order column to files table"""
    engine = db_engine
    
    if column_exists(engine, 'files', 'queue_order'):
        logger.info("✅ queue_order column already exists in files table")
        return

    logger.info("➕ Adding queue_order column to files table...")
    
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE files ADD COLUMN queue_order INTEGER"))
        conn.commit()
        
    logger.info("✅ Added queue_order column")

if __name__ == "__main__":
    upgrade()
