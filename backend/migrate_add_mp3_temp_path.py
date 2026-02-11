"""
Migration: Add mp3_temp_path field to File model for MP3 export tracking

This migration adds a new field to track temporary MP3 file paths
during the processing pipeline before they're organized to the final location.

Usage:
    python migrate_add_mp3_temp_path.py
"""

import sqlite3
from pathlib import Path

def migrate():
    # Get database path (same as in database.py)
    db_path = Path.home() / "Library/Application Support/StudioPipeline/pipeline.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return False

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'mp3_temp_path' in columns:
            print("⚠️  Column 'mp3_temp_path' already exists in files table")
            return True

        # Add the new column
        print("Adding 'mp3_temp_path' column to files table...")
        cursor.execute("""
            ALTER TABLE files
            ADD COLUMN mp3_temp_path TEXT
        """)

        conn.commit()
        print("✅ Migration completed successfully")
        print("   - Added 'mp3_temp_path' column to files table")

        # Verify the column was added
        cursor.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'mp3_temp_path' in columns:
            print("✅ Verified: Column exists in database")
        else:
            print("❌ Error: Column not found after migration")
            return False

        return True

    except sqlite3.Error as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

def rollback():
    """
    Rollback migration by removing the mp3_temp_path column.
    Note: SQLite doesn't support DROP COLUMN directly, so this requires table recreation.
    """
    db_path = Path.home() / "Library/Application Support/StudioPipeline/pipeline.db"

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return False

    print(f"Rolling back migration for: {db_path}")
    print("⚠️  SQLite doesn't support DROP COLUMN directly.")
    print("   To rollback, you would need to recreate the table without this column.")
    print("   This is typically not necessary for adding nullable columns.")
    return False

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'rollback':
        success = rollback()
    else:
        success = migrate()

    sys.exit(0 if success else 1)
