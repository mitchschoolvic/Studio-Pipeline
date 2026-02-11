"""
Migration: Add audience and speaker string fields to file_analytics table

This migration adds two new columns to support the schema mapping requirements:
- audience: Comma-separated string (e.g., "Student, Parent")
- speaker: Comma-separated string (e.g., "Staff, Student")

These fields are derived from the existing JSON array fields (audience_type, speaker_type)
but provide a simpler string format for external system integration.

Usage:
    python migrate_add_audience_speaker_fields.py
"""

import sys
import json
import logging
from pathlib import Path

# Add backend directory to Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from database import engine, SessionLocal

# Import models after database setup to avoid circular dependencies
import models  # This ensures File model is loaded
from models_analytics import FileAnalytics

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_columns_exist():
    """Check if the new columns already exist"""
    with engine.connect() as conn:
        # Get list of columns from pragma
        result = conn.execute(text("PRAGMA table_info(file_analytics)"))
        columns = [row[1] for row in result.fetchall()]
        
        has_audience = 'audience' in columns
        has_speaker = 'speaker' in columns
        
        return has_audience, has_speaker


def add_columns():
    """Add new columns to file_analytics table"""
    logger.info("🔧 Adding new columns to file_analytics table...")
    
    has_audience, has_speaker = check_columns_exist()
    
    with engine.connect() as conn:
        if not has_audience:
            logger.info("  → Adding 'audience' column")
            conn.execute(text('ALTER TABLE file_analytics ADD COLUMN audience VARCHAR'))
        else:
            logger.info("  ✓ 'audience' column already exists")
        
        if not has_speaker:
            logger.info("  → Adding 'speaker' column")
            conn.execute(text('ALTER TABLE file_analytics ADD COLUMN speaker VARCHAR'))
        else:
            logger.info("  ✓ 'speaker' column already exists")
        
        conn.commit()
    
    logger.info("✅ Columns added successfully")


def backfill_data():
    """Backfill existing records with data from JSON fields"""
    logger.info("🔄 Backfilling existing records...")
    
    db = SessionLocal()
    try:
        records = db.query(FileAnalytics).all()
        logger.info(f"  Found {len(records)} records to process")
        
        updated_count = 0
        error_count = 0
        
        for record in records:
            try:
                updated = False
                
                # Populate audience from audience_type JSON
                if not record.audience and record.audience_type:
                    try:
                        audience_list = json.loads(record.audience_type)
                        if audience_list:
                            record.audience = ', '.join(audience_list)
                            updated = True
                            logger.debug(f"  → {record.filename}: audience = '{record.audience}'")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"  ⚠️  Failed to parse audience_type for {record.filename}: {e}")
                        error_count += 1
                
                # Populate speaker from speaker_type JSON
                if not record.speaker and record.speaker_type:
                    try:
                        speaker_list = json.loads(record.speaker_type)
                        if speaker_list:
                            record.speaker = ', '.join(speaker_list)
                            updated = True
                            logger.debug(f"  → {record.filename}: speaker = '{record.speaker}'")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"  ⚠️  Failed to parse speaker_type for {record.filename}: {e}")
                        error_count += 1
                
                if updated:
                    updated_count += 1
            
            except Exception as e:
                logger.error(f"  ❌ Error processing record {record.id}: {e}")
                error_count += 1
                continue
        
        db.commit()
        logger.info(f"✅ Backfill complete: {updated_count} records updated, {error_count} errors")
    
    except Exception as e:
        logger.error(f"❌ Backfill failed: {e}")
        db.rollback()
        raise
    
    finally:
        db.close()


def verify_migration():
    """Verify the migration was successful"""
    logger.info("🔍 Verifying migration...")
    
    db = SessionLocal()
    try:
        # Check if columns exist and have data
        sample = db.query(FileAnalytics).filter(
            FileAnalytics.audience.isnot(None)
        ).first()
        
        if sample:
            logger.info(f"  ✓ Found record with audience: '{sample.audience}'")
            logger.info(f"  ✓ Found record with speaker: '{sample.speaker}'")
        else:
            logger.warning("  ⚠️  No records found with populated audience field")
        
        # Count records
        total = db.query(FileAnalytics).count()
        with_audience = db.query(FileAnalytics).filter(
            FileAnalytics.audience.isnot(None)
        ).count()
        with_speaker = db.query(FileAnalytics).filter(
            FileAnalytics.speaker.isnot(None)
        ).count()
        
        logger.info(f"  Total records: {total}")
        logger.info(f"  Records with audience: {with_audience}")
        logger.info(f"  Records with speaker: {with_speaker}")
        
        logger.info("✅ Migration verified successfully")
    
    finally:
        db.close()


def main():
    """Run the migration"""
    logger.info("=" * 70)
    logger.info("MIGRATION: Add audience and speaker fields to file_analytics")
    logger.info("=" * 70)
    
    try:
        # Step 1: Add columns
        add_columns()
        
        # Step 2: Backfill data
        backfill_data()
        
        # Step 3: Verify
        verify_migration()
        
        logger.info("=" * 70)
        logger.info("✅ MIGRATION COMPLETED SUCCESSFULLY")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error("=" * 70)
        logger.error(f"❌ MIGRATION FAILED: {e}")
        logger.error("=" * 70)
        sys.exit(1)


if __name__ == '__main__':
    main()
