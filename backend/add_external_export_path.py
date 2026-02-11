"""
Database migration: Add external_export_path column to files table (Idempotent)

This migration safely adds the external_export_path column for tracking
AI analytics cache locations.

Usage:
    python backend/add_external_export_path.py
"""
from sqlalchemy import create_engine, text, inspect
from database import engine as db_engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def column_exists(engine, table_name: str, column_name: str) -> bool:
    """
    Check if a column exists in a table.

    Args:
        engine: SQLAlchemy engine
        table_name: Name of table to check
        column_name: Name of column to check

    Returns:
        True if column exists, False otherwise
    """
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    """Add external_export_path column to files table if it doesn't exist"""
    engine = db_engine

    # Check if column already exists
    if column_exists(engine, 'files', 'external_export_path'):
        logger.info("✅ external_export_path column already exists - skipping migration")
        return

    logger.info("📊 Adding external_export_path column to files table...")

    with engine.connect() as conn:
        # Add the column
        conn.execute(text("""
            ALTER TABLE files
            ADD COLUMN external_export_path TEXT
        """))

        conn.commit()
        logger.info("✅ Added external_export_path column to files table")


def downgrade():
    """Remove external_export_path column from files table"""
    engine = db_engine

    if not column_exists(engine, 'files', 'external_export_path'):
        logger.info("ℹ️ external_export_path column does not exist - nothing to remove")
        return

    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE files DROP COLUMN external_export_path"))
        conn.commit()
        logger.info("✅ Removed external_export_path column from files table")


def verify():
    """Verify migration was successful"""
    engine = db_engine

    if not column_exists(engine, 'files', 'external_export_path'):
        logger.error("❌ Verification failed: external_export_path column does not exist")
        return False

    logger.info("✅ Migration verification successful")
    return True


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'downgrade':
            downgrade()
        elif command == 'verify':
            success = verify()
            sys.exit(0 if success else 1)
        else:
            print(f"Unknown command: {command}")
            print("Usage: python add_external_export_path.py [upgrade|downgrade|verify]")
            sys.exit(1)
    else:
        upgrade()
        verify()
