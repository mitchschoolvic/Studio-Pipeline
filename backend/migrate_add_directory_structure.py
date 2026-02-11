#!/usr/bin/env python3
"""
Database migration: Add directory structure preservation fields

Adds:
- session_folder: The top-level folder name (e.g., "Haileybury Studio 11")
- relative_path: Path relative to session folder (e.g., "Video ISO Files/CAM 1 01.mp4")
- parent_file_id: Foreign key linking ISO files to their main video file
"""

import sqlite3
from pathlib import Path
import sys

DB_PATH = Path.home() / "Library/Application Support/StudioPipeline/pipeline.db"


def migrate():
    """Execute migration to add directory structure fields"""
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("🔄 Starting migration: Add directory structure fields...")
        
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(files)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        columns_to_add = []
        if 'session_folder' not in existing_columns:
            columns_to_add.append('session_folder')
        if 'relative_path' not in existing_columns:
            columns_to_add.append('relative_path')
        if 'parent_file_id' not in existing_columns:
            columns_to_add.append('parent_file_id')
        
        if not columns_to_add:
            print("✅ All columns already exist, migration not needed")
            return
        
        # Add new columns
        for col in columns_to_add:
            if col == 'parent_file_id':
                cursor.execute(f"ALTER TABLE files ADD COLUMN {col} VARCHAR REFERENCES files(id)")
            else:
                cursor.execute(f"ALTER TABLE files ADD COLUMN {col} TEXT")
            print(f"  ✓ Added column: {col}")
        
        # Backfill existing files with data from path_remote
        # path_remote format: /J-USB/<session_folder>/<relative_path>
        # or: /J-USB/<session_folder>/Video ISO Files/<filename>
        print("\n🔄 Backfilling existing file records...")
        
        cursor.execute("""
            UPDATE files 
            SET 
                session_folder = CASE
                    WHEN path_remote LIKE '/J-USB/%' THEN
                        SUBSTR(
                            path_remote, 
                            8,  -- Skip '/J-USB/'
                            INSTR(SUBSTR(path_remote, 8), '/') - 1
                        )
                    ELSE
                        NULL
                END,
                relative_path = CASE
                    WHEN path_remote LIKE '/J-USB/%' THEN
                        SUBSTR(
                            path_remote,
                            8 + INSTR(SUBSTR(path_remote, 8), '/')
                        )
                    ELSE
                        filename
                END
            WHERE session_folder IS NULL
        """)
        
        backfilled = cursor.rowcount
        print(f"  ✓ Backfilled {backfilled} file records")
        
        # Link ISO files to parent files (will be more accurately done in discovery worker)
        # For now, just mark files as potentially having parents if they're in subfolders
        print("\n🔄 Marking ISO files for parent linking...")
        
        cursor.execute("""
            UPDATE files
            SET is_iso = 1
            WHERE (filename LIKE '%CAM%' OR relative_path LIKE '%/%')
              AND is_iso IS NOT 1
        """)
        
        marked_iso = cursor.rowcount
        print(f"  ✓ Marked {marked_iso} ISO files")
        
        conn.commit()
        
        # Verify migration
        print("\n🔍 Verifying migration...")
        cursor.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cursor.fetchall()]
        
        required_columns = {'session_folder', 'relative_path', 'parent_file_id'}
        if required_columns.issubset(set(columns)):
            print("✅ Migration successful!")
            print(f"\n📊 Added columns: {', '.join(columns_to_add)}")
        else:
            missing = required_columns - set(columns)
            print(f"❌ Migration incomplete. Missing columns: {missing}")
            sys.exit(1)
        
        # Show sample data
        print("\n📋 Sample migrated data:")
        cursor.execute("""
            SELECT filename, session_folder, relative_path, is_iso
            FROM files
            LIMIT 5
        """)
        
        for row in cursor.fetchall():
            filename, session_folder, relative_path, is_iso = row
            iso_marker = " [ISO]" if is_iso else ""
            print(f"  • {filename}{iso_marker}")
            print(f"    Session: {session_folder}")
            print(f"    Relative: {relative_path}")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()
