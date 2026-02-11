"""
Backfill duration for existing files

This script extracts video duration for files that were copied before
the duration field was added. It processes files that have path_local
set but duration is NULL.
"""

import sys
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from database import SessionLocal
from models import File
from utils.video_metadata import get_video_duration

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def backfill_durations():
    """Extract and save duration for existing files"""
    db = SessionLocal()
    
    try:
        # Find files that don't have duration but have been copied or completed
        # Check for path_local, path_processed, or path_final
        files = db.query(File).filter(
            File.duration.is_(None),
            File.state.in_(['COPIED', 'PROCESSED', 'COMPLETED'])
        ).all()
        
        if not files:
            logger.info("✅ No files need duration backfill")
            return
        
        logger.info(f"Found {len(files)} files needing duration extraction")
        
        success_count = 0
        fail_count = 0
        
        for file in files:
            try:
                # Find the first available local path
                local_path = None
                
                if file.path_local and Path(file.path_local).exists():
                    local_path = file.path_local
                elif file.path_processed and Path(file.path_processed).exists():
                    local_path = file.path_processed
                elif file.path_final and Path(file.path_final).exists():
                    local_path = file.path_final
                
                if not local_path:
                    logger.warning(f"⏭️  Skipping {file.filename} - no accessible file found")
                    fail_count += 1
                    continue
                
                # Extract duration
                duration = get_video_duration(local_path)
                
                if duration:
                    file.duration = duration
                    db.commit()
                    
                    # Calculate bitrate for logging
                    bitrate_kbps = (file.size * 8) / (duration * 1000) if duration > 0 else 0
                    logger.info(
                        f"✅ {file.filename}: {duration:.2f}s "
                        f"({bitrate_kbps:.0f} kbps)"
                    )
                    success_count += 1
                else:
                    logger.warning(f"❌ Could not extract duration for {file.filename}")
                    fail_count += 1
                    
            except Exception as e:
                logger.error(f"❌ Error processing {file.filename}: {e}")
                fail_count += 1
        
        logger.info(f"\n✅ Backfill complete: {success_count} succeeded, {fail_count} failed")
        
    except Exception as e:
        logger.error(f"❌ Backfill failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    backfill_durations()
