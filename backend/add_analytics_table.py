"""
Database migration: Add file_analytics table (Idempotent)

This migration safely creates the analytics table with existence checks.
Only run if BUILD_WITH_AI is enabled.

Usage:
    python migrations/add_analytics_table.py
"""
from sqlalchemy import create_engine, text, inspect
from database import engine as db_engine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def table_exists(engine, table_name: str) -> bool:
    """
    Check if a table exists in the database.
    
    Args:
        engine: SQLAlchemy engine
        table_name: Name of table to check
        
    Returns:
        True if table exists, False otherwise
    """
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def upgrade():
    """Create file_analytics table if it doesn't exist"""
    engine = db_engine
    
    # Check if table already exists
    if table_exists(engine, 'file_analytics'):
        logger.info("✅ file_analytics table already exists - skipping migration")
        return
    
    logger.info("📊 Creating file_analytics table...")
    
    with engine.connect() as conn:
        # Create the analytics table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS file_analytics (
                id TEXT PRIMARY KEY,
                file_id TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL DEFAULT 'PENDING',
                transcript TEXT,
                analysis_json TEXT,
                
                -- LLM Provenance (for version tracking)
                llm_model_version TEXT,
                llm_prompt_version TEXT,
                whisper_model_version TEXT,
                
                -- CSV Export Fields (17 fields)
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
                language TEXT,
                detected_language TEXT,
                speaker_count INTEGER,
                video_url TEXT,
                
                -- Processing metadata
                transcription_started_at TIMESTAMP,
                transcription_completed_at TIMESTAMP,
                transcription_duration_seconds INTEGER,
                analysis_started_at TIMESTAMP,
                analysis_completed_at TIMESTAMP,
                analysis_duration_seconds INTEGER,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                manual_retry_required BOOLEAN DEFAULT FALSE,
                
                -- Timestamps
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                CHECK (state IN ('PENDING', 'TRANSCRIBING', 'TRANSCRIBED', 'ANALYZING', 'COMPLETED', 'FAILED', 'SKIPPED'))
            )
        """))
        
        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analytics_state ON file_analytics(state)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analytics_file_id ON file_analytics(file_id)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analytics_created_at ON file_analytics(created_at)
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_analytics_manual_retry ON file_analytics(manual_retry_required) 
            WHERE manual_retry_required = TRUE
        """))
        
        conn.commit()
        logger.info("✅ Created file_analytics table and indexes")


def downgrade():
    """Drop file_analytics table"""
    engine = db_engine
    
    if not table_exists(engine, 'file_analytics'):
        logger.info("ℹ️ file_analytics table does not exist - nothing to drop")
        return
    
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS file_analytics"))
        conn.commit()
        logger.info("✅ Dropped file_analytics table")


def verify():
    """Verify migration was successful"""
    engine = db_engine
    
    if not table_exists(engine, 'file_analytics'):
        logger.error("❌ Verification failed: file_analytics table does not exist")
        return False
    
    # Check that all expected columns exist
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('file_analytics')]
    
    required_columns = [
        'id', 'file_id', 'state', 'transcript', 'analysis_json',
        'llm_model_version', 'llm_prompt_version', 'whisper_model_version',
        'title', 'description', 'duration', 'duration_seconds',
        'manual_retry_required'
    ]
    
    missing = [col for col in required_columns if col not in columns]
    if missing:
        logger.error(f"❌ Verification failed: missing columns: {missing}")
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
            print("Usage: python add_analytics_table.py [upgrade|downgrade|verify]")
            sys.exit(1)
    else:
        upgrade()
        verify()
