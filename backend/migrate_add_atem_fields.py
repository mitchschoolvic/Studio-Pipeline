#!/usr/bin/env python3
"""
Migration script to add ATEM session support fields to existing database.

Adds:
- files.is_program_output (Boolean, default=True)
- files.folder_path (Text, nullable=True)

Safe to run multiple times (checks if columns exist first).
"""

import sqlite3
from pathlib import Path
import sys

def get_db_path():
    """Get database path from Application Support or local directory"""
    app_support = Path.home() / "Library" / "Application Support" / "StudioPipeline"
    db_path = app_support / "pipeline.db"
    
    if not db_path.exists():
        # Fallback to local directory
        db_path = Path(__file__).parent / "pipeline.db"
    
    return db_path

def column_exists(conn, table: str, column: str) -> bool:
    """Check if a column exists in a table"""
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns

def migrate(db_path: Path):
    """Run migration to add ATEM fields"""
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    
    try:
        # Check and add is_program_output column
        if not column_exists(conn, 'files', 'is_program_output'):
            print("  Adding files.is_program_output column...")
            conn.execute("""
                ALTER TABLE files 
                ADD COLUMN is_program_output BOOLEAN DEFAULT 1
            """)
            # Set existing files to True (they were all treated as program output before)
            conn.execute("UPDATE files SET is_program_output = 1 WHERE is_program_output IS NULL")
            print("    ✓ Added is_program_output (default=True for existing files)")
        else:
            print("  ✓ files.is_program_output already exists")
        
        # Check and add folder_path column
        if not column_exists(conn, 'files', 'folder_path'):
            print("  Adding files.folder_path column...")
            conn.execute("""
                ALTER TABLE files 
                ADD COLUMN folder_path TEXT
            """)
            print("    ✓ Added folder_path")
        else:
            print("  ✓ files.folder_path already exists")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        # Show summary
        cursor = conn.execute("SELECT COUNT(*) FROM files")
        file_count = cursor.fetchone()[0]
        print(f"\nDatabase summary:")
        print(f"  Total files: {file_count}")
        
        cursor = conn.execute("SELECT COUNT(*) FROM files WHERE is_program_output = 1")
        program_files = cursor.fetchone()[0]
        print(f"  Program output files: {program_files}")
        
        cursor = conn.execute("SELECT COUNT(*) FROM files WHERE is_iso = 1")
        iso_files = cursor.fetchone()[0]
        print(f"  ISO files: {iso_files}")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    db_path = get_db_path()
    
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}", file=sys.stderr)
        print("   Please run init_db.py first or start the application once.", file=sys.stderr)
        sys.exit(1)
    
    migrate(db_path)
