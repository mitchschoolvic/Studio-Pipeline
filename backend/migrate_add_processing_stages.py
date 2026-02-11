#!/usr/bin/env python3
"""
Migration: Add processing stage tracking fields to files table.

This migration adds:
- processing_stage: Current substep being executed
- processing_stage_progress: Progress within current substep (0-100)
- processing_detail: Human-readable detail about current operation

Run with: python migrate_add_processing_stages.py
"""

import sqlite3
from pathlib import Path

def migrate():
    # Database path
    db_path = Path(__file__).parent / "studio_pipeline.db"
    
    if not db_path.exists():
        print(f"Database not found at {db_path}")
        print("No migration needed - database will be created with new schema.")
        return
    
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(files)")
        columns = [col[1] for col in cursor.fetchall()]
        
        changes_made = False
        
        # Add processing_stage column if it doesn't exist
        if 'processing_stage' not in columns:
            print("Adding processing_stage column...")
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN processing_stage TEXT
            """)
            changes_made = True
        else:
            print("processing_stage column already exists")
        
        # Add processing_stage_progress column if it doesn't exist
        if 'processing_stage_progress' not in columns:
            print("Adding processing_stage_progress column...")
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN processing_stage_progress INTEGER DEFAULT 0
            """)
            changes_made = True
        else:
            print("processing_stage_progress column already exists")
        
        # Add processing_detail column if it doesn't exist
        if 'processing_detail' not in columns:
            print("Adding processing_detail column...")
            cursor.execute("""
                ALTER TABLE files 
                ADD COLUMN processing_detail TEXT
            """)
            changes_made = True
        else:
            print("processing_detail column already exists")
        
        if changes_made:
            conn.commit()
            print("\n✅ Migration completed successfully!")
            print("New columns added:")
            print("  - processing_stage (TEXT)")
            print("  - processing_stage_progress (INTEGER, default 0)")
            print("  - processing_detail (TEXT)")
        else:
            print("\n✅ All columns already exist - no migration needed")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
