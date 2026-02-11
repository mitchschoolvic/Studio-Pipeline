#!/usr/bin/env python3
"""
Migration: Remove language column from file_analytics table

The language column is redundant with detected_language (from Whisper).
We're keeping only detected_language going forward.
"""
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_path() -> Path:
    """Get database path from standard location"""
    db_path = Path.home() / "Library" / "Application Support" / "StudioPipeline" / "pipeline.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found at {db_path}")
    return db_path

def remove_language_column():
    """Remove language column from file_analytics table"""
    db_path = get_db_path()
    logger.info(f"📂 Using database: {db_path}")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # Check if language column exists
        cursor.execute("PRAGMA table_info(file_analytics)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]

        if 'language' not in column_names:
            logger.info("✅ Column 'language' does not exist - nothing to do")
            return

        logger.info("🔧 Removing 'language' column from file_analytics table")

        # SQLite doesn't support DROP COLUMN directly for all versions
        # We need to recreate the table without the language column

        # Step 1: Create new table without language column
        cursor.execute("""
            CREATE TABLE file_analytics_new (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL DEFAULT 'PENDING',
                transcript TEXT,
                analysis_json TEXT,
                llm_model_version TEXT,
                llm_prompt_version TEXT,
                whisper_model_version TEXT,
                title TEXT,
                description TEXT,
                duration TEXT,
                duration_seconds INTEGER,
                content_type TEXT,
                faculty TEXT,
                speaker_type TEXT,
                audience_type TEXT,
                speaker_confidence TEXT,
                rationale_short TEXT,
                timestamp TEXT,
                timestamp_sort TEXT,
                thumbnail_url TEXT,
                filename TEXT,
                studio_location TEXT,
                detected_language TEXT,
                speaker_count INTEGER,
                video_url TEXT,
                transcription_started_at DATETIME,
                transcription_completed_at DATETIME,
                transcription_duration_seconds INTEGER,
                analysis_started_at DATETIME,
                analysis_completed_at DATETIME,
                analysis_duration_seconds INTEGER,
                llm_prompt_tokens INTEGER,
                llm_completion_tokens INTEGER,
                llm_total_tokens INTEGER,
                llm_peak_memory_mb REAL,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                manual_retry_required BOOLEAN DEFAULT 0,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                CHECK (state IN ('PENDING', 'TRANSCRIBING', 'TRANSCRIBED', 'ANALYZING', 'COMPLETED', 'FAILED', 'SKIPPED'))
            )
        """)

        # Step 2: Copy data from old table to new table (excluding language column)
        cursor.execute("""
            INSERT INTO file_analytics_new
            SELECT
                id, file_id, state, transcript, analysis_json,
                llm_model_version, llm_prompt_version, whisper_model_version,
                title, description, duration, duration_seconds,
                content_type, faculty, speaker_type, audience_type,
                speaker_confidence, rationale_short, timestamp, timestamp_sort,
                thumbnail_url, filename, studio_location,
                detected_language, speaker_count, video_url,
                transcription_started_at, transcription_completed_at, transcription_duration_seconds,
                analysis_started_at, analysis_completed_at, analysis_duration_seconds,
                llm_prompt_tokens, llm_completion_tokens, llm_total_tokens, llm_peak_memory_mb,
                error_message, retry_count, manual_retry_required,
                created_at, updated_at
            FROM file_analytics
        """)

        # Step 3: Drop old table
        cursor.execute("DROP TABLE file_analytics")

        # Step 4: Rename new table to original name
        cursor.execute("ALTER TABLE file_analytics_new RENAME TO file_analytics")

        # Step 5: Recreate indexes
        cursor.execute("CREATE INDEX idx_analytics_state ON file_analytics(state)")
        cursor.execute("CREATE INDEX idx_analytics_file_id ON file_analytics(file_id)")
        cursor.execute("CREATE INDEX idx_analytics_created_at ON file_analytics(created_at)")
        cursor.execute("CREATE INDEX idx_analytics_manual_retry ON file_analytics(manual_retry_required)")

        conn.commit()
        logger.info("✅ Successfully removed 'language' column from file_analytics")

        # Verify the change
        cursor.execute("PRAGMA table_info(file_analytics)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        logger.info(f"📋 Updated columns: {', '.join(column_names)}")

    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    remove_language_column()
    logger.info("🎉 Migration complete!")
