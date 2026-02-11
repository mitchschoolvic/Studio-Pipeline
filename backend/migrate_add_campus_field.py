#!/usr/bin/env python3
"""
Migration script to add 'campus' field to Session table.
Defaults to 'Keysborough' for all existing sessions.
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
    """Run migration to add campus field"""
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    
    try:
        # Check and add campus column
        if not column_exists(conn, 'sessions', 'campus'):
            print("  Adding sessions.campus column...")
            conn.execute("""
                ALTER TABLE sessions 
                ADD COLUMN campus TEXT DEFAULT 'Keysborough'
            """)
            # Backfill existing sessions (though DEFAULT should handle it for new inserts, 
            # existing rows get the default value when adding a column in SQLite usually,
            # but explicit update ensures it).
            conn.execute("UPDATE sessions SET campus = 'Keysborough' WHERE campus IS NULL")
            print("    ✓ Added campus (default='Keysborough' for existing sessions)")
        else:
            print("  ✓ sessions.campus already exists")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
        # Show summary
        cursor = conn.execute("SELECT COUNT(*) FROM sessions")
        session_count = cursor.fetchone()[0]
        print(f"\nDatabase summary:")
        print(f"  Total sessions: {session_count}")
        
        cursor = conn.execute("SELECT COUNT(*) FROM sessions WHERE campus = 'Keysborough'")
        keysborough_sessions = cursor.fetchone()[0]
        print(f"  Keysborough sessions: {keysborough_sessions}")
        
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
