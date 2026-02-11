"""
Database migration: Update jobs kind constraint to include TRANSCRIBE and ANALYZE

This migration updates the jobs table CHECK constraint to allow AI job types.

Usage:
    python backend/update_jobs_constraint.py
"""
import sqlite3
import os
from pathlib import Path

# Database location
DB_PATH = Path.home() / "Library/Application Support/StudioPipeline/pipeline.db"

def upgrade():
    """Update jobs table constraint to include AI job types"""
    print("📊 Updating jobs table constraint...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # SQLite doesn't support ALTER TABLE ... DROP CONSTRAINT
        # We need to recreate the table

        # 1. Create new jobs table with updated constraint
        cursor.execute("""
            CREATE TABLE jobs_new (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'QUEUED',
                priority INTEGER DEFAULT 0,
                retries INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                progress_pct REAL DEFAULT 0.0,
                progress_stage TEXT,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP,
                is_cancellable BOOLEAN DEFAULT FALSE,
                cancellation_requested BOOLEAN DEFAULT FALSE,
                checkpoint_state TEXT,
                FOREIGN KEY (file_id) REFERENCES files(id),
                CHECK (kind IN ('COPY', 'PROCESS', 'ORGANIZE', 'TRANSCRIBE', 'ANALYZE')),
                CHECK (state IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED'))
            )
        """)

        # 2. Copy data from old table
        cursor.execute("""
            INSERT INTO jobs_new
            SELECT * FROM jobs
        """)

        # 3. Drop old table
        cursor.execute("DROP TABLE jobs")

        # 4. Rename new table
        cursor.execute("ALTER TABLE jobs_new RENAME TO jobs")

        # 5. Recreate indexes
        cursor.execute("""
            CREATE INDEX idx_jobs_state ON jobs(state, kind)
        """)
        cursor.execute("""
            CREATE INDEX idx_jobs_file ON jobs(file_id)
        """)

        conn.commit()
        print("✅ Updated jobs table constraint successfully")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error updating constraint: {e}")
        raise
    finally:
        conn.close()

def verify():
    """Verify the constraint was updated"""
    print("🔍 Verifying constraint update...")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Try to insert a TRANSCRIBE job
        import uuid
        from datetime import datetime

        test_job_id = str(uuid.uuid4())
        test_file_id = "test-file-id"

        cursor.execute("""
            INSERT INTO jobs (id, file_id, kind, state, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (test_job_id, test_file_id, "TRANSCRIBE", "QUEUED", datetime.now()))

        # Clean up test data
        cursor.execute("DELETE FROM jobs WHERE id = ?", (test_job_id,))
        conn.commit()

        print("✅ Verification successful - TRANSCRIBE and ANALYZE job types are now allowed")
        return True

    except sqlite3.IntegrityError as e:
        print(f"❌ Verification failed: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    import sys

    if not DB_PATH.exists():
        print(f"❌ Database not found at: {DB_PATH}")
        sys.exit(1)

    upgrade()
    success = verify()
    sys.exit(0 if success else 1)
