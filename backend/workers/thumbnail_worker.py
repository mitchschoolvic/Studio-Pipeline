"""
Thumbnail Worker

Background worker for generating video thumbnails in batches.
Processes files without blocking the main pipeline.
"""

import asyncio
import logging
import time
from datetime import datetime
from sqlalchemy.orm import Session
from database import get_db
from models import File
from services.thumbnail_generator import ThumbnailGenerator
from services.websocket import manager
from sqlalchemy import or_

logger = logging.getLogger(__name__)


class ThumbnailWorker:
    """
    Background worker for generating thumbnails.
    
    Processes files in batches to avoid overwhelming the system.
    Prioritizes completed files for immediate display.
    """
    
    def __init__(
        self, 
        thumbnail_dir: str, 
        batch_size: int = 5, 
        delay: float = 3.0,
        max_cpu_percent: float = 80.0
    ):
        """
        Initialize thumbnail worker.
        
        Args:
            thumbnail_dir: Directory for storing thumbnails
            batch_size: Number of thumbnails to generate per batch
            delay: Seconds to wait between batches
            max_cpu_percent: Maximum CPU usage before pausing (default 80%)
        """
        self.generator = ThumbnailGenerator(thumbnail_dir)
        self.batch_size = batch_size
        self.delay = delay
        self.max_cpu_percent = max_cpu_percent
        self.running = False
        
        # Metrics
        self.metrics = {
            'generated': 0,
            'failed': 0,
            'skipped': 0,
            'total_time': 0,
            'batches_processed': 0,
            'last_batch_time': None
        }
    
    async def start(self):
        """Start the thumbnail worker."""
        self.running = True
        logger.info("🎬 Thumbnail worker started")
        logger.info(f"   Batch size: {self.batch_size}")
        logger.info(f"   Delay between batches: {self.delay}s")
        
        while self.running:
            try:
                await self._process_batch()
                await asyncio.sleep(self.delay)
            except Exception as e:
                logger.error(f"Thumbnail worker error: {e}", exc_info=True)
                await asyncio.sleep(10)  # Wait longer on error
    
    async def stop(self):
        """Stop the thumbnail worker."""
        self.running = False
        logger.info("🛑 Thumbnail worker stopped")
        self._log_metrics()
    
    async def _process_batch(self):
        """Process a batch of files needing thumbnails."""
        # Check CPU usage before processing
        if not self._check_system_resources():
            return
        
        db = next(get_db())
        try:
            # Find files that need thumbnails
            # Priority order: COMPLETED > PROCESSED > COPIED > DISCOVERED
            pending_files = self._get_pending_files(db)
            
            if not pending_files:
                return
            
            logger.info(f"📸 Processing {len(pending_files)} thumbnails in this batch")
            
            batch_start = time.time()
            
            for file in pending_files:
                if not self.running:
                    break
                
                file_start = time.time()
                
                # Determine which path to use (prefer final > processed > local)
                video_path = file.path_final or file.path_processed or file.path_local
                
                if not video_path:
                    # Don't permanently fail when the file isn't available locally yet.
                    # Keep it PENDING so we can retry once a local/processed/final path appears.
                    logger.info(f"⏭️  Path not ready for {file.filename} (state={file.state}), will retry later")
                    file.thumbnail_state = 'PENDING'
                    file.thumbnail_error = "Awaiting local/processed/final path"
                    db.commit()
                    self.metrics['skipped'] += 1
                    continue
                
                # Generate thumbnail (run in executor to not block event loop)
                success = await asyncio.get_event_loop().run_in_executor(
                    None,
                    self.generator.generate_thumbnail,
                    file.id,
                    video_path,
                    db
                )
                
                file_elapsed = time.time() - file_start
                
                if success:
                    self.metrics['generated'] += 1
                    logger.info(f"   ✅ {file.filename} ({file_elapsed:.2f}s)")
                    # Re-load file to ensure we have latest fields from DB
                    try:
                        db.refresh(file)
                    except Exception:
                        pass
                    # Notify clients that thumbnail is ready
                    try:
                        etag = None
                        if file.thumbnail_generated_at:
                            etag = f"{file.id}-{int(file.thumbnail_generated_at.timestamp())}"
                        await manager.send_thumbnail_update(
                            file_id=str(file.id),
                            thumbnail_state=str(file.thumbnail_state or 'READY'),
                            etag=etag,
                            thumbnail_path=file.thumbnail_path
                        )
                    except Exception as notify_err:
                        logger.warning(f"Failed to broadcast thumbnail update: {notify_err}")
                else:
                    self.metrics['failed'] += 1
                    logger.warning(f"   ❌ {file.filename} failed")
                    # Notify clients of failure so they can stop waiting
                    try:
                        await manager.send_thumbnail_update(
                            file_id=str(file.id),
                            thumbnail_state='FAILED',
                            error=file.thumbnail_error
                        )
                    except Exception as notify_err:
                        logger.warning(f"Failed to broadcast thumbnail failure: {notify_err}")
            
            batch_elapsed = time.time() - batch_start
            self.metrics['total_time'] += batch_elapsed
            self.metrics['batches_processed'] += 1
            self.metrics['last_batch_time'] = datetime.utcnow()
            
            logger.info(f"📊 Batch completed in {batch_elapsed:.2f}s")
            
        finally:
            db.close()
    
    def _get_pending_files(self, db: Session) -> list:
        """
        Get files that need thumbnails, prioritized by state.
        
        Priority:
        1. COMPLETED files (most important - ready for viewing)
        2. PROCESSED files (almost done)
        3. COPIED files (downloaded, waiting for processing)
        4. DISCOVERED files (lowest priority)
        
        Returns:
            List of File objects needing thumbnails
        """
        # Build query with priority ordering
        # Only pick items where we have something to work with
        query = db.query(File).filter(
            File.thumbnail_state == 'PENDING',
            or_(
                File.is_empty == True,  # Placeholder can be generated immediately
                File.path_final.isnot(None),
                File.path_processed.isnot(None),
                File.path_local.isnot(None),
            )
        )
        
        # Order by state priority (custom ordering)
        # Use CASE statement for ordering
        from sqlalchemy import case
        
        state_priority = case(
            (File.state == 'COMPLETED', 1),
            (File.state == 'PROCESSED', 2),
            (File.state == 'COPIED', 3),
            (File.state == 'DISCOVERED', 4),
            else_=5
        )
        
        query = query.order_by(state_priority, File.created_at.desc())
        
        return query.limit(self.batch_size).all()
    
    def _check_system_resources(self) -> bool:
        """
        Check if system has enough resources to process thumbnails.
        
        Returns:
            True if resources available, False if system is too busy
        """
        try:
            import psutil
            
            cpu_percent = psutil.cpu_percent(interval=1)
            
            if cpu_percent > self.max_cpu_percent:
                logger.info(f"⚠️ High CPU usage ({cpu_percent:.1f}%), skipping batch")
                return False
            
            # Check available memory
            memory = psutil.virtual_memory()
            if memory.percent > 90:
                logger.warning(f"⚠️ High memory usage ({memory.percent:.1f}%), skipping batch")
                return False
            
            return True
            
        except ImportError:
            # psutil not available, assume resources are OK
            return True
        except Exception as e:
            logger.warning(f"Could not check system resources: {e}")
            return True
    
    def _log_metrics(self):
        """Log summary metrics."""
        logger.info("📊 Thumbnail Worker Metrics:")
        logger.info(f"   Generated: {self.metrics['generated']}")
        logger.info(f"   Failed: {self.metrics['failed']}")
        logger.info(f"   Batches: {self.metrics['batches_processed']}")
        
        if self.metrics['batches_processed'] > 0:
            avg_time = self.metrics['total_time'] / self.metrics['batches_processed']
            logger.info(f"   Avg batch time: {avg_time:.2f}s")
        
        if self.metrics['last_batch_time']:
            logger.info(f"   Last batch: {self.metrics['last_batch_time']}")
    
    def get_stats(self) -> dict:
        """
        Get worker statistics.
        
        Returns:
            Dictionary with current metrics
        """
        return {
            **self.metrics,
            'running': self.running,
            'batch_size': self.batch_size,
            'delay': self.delay
        }


# Singleton instance (will be initialized by worker pool)
thumbnail_worker = None

def get_thumbnail_worker() -> ThumbnailWorker:
    """Get the thumbnail worker instance."""
    global thumbnail_worker
    return thumbnail_worker

def init_thumbnail_worker(thumbnail_dir: str, **kwargs) -> ThumbnailWorker:
    """
    Initialize the thumbnail worker.
    
    Args:
        thumbnail_dir: Directory for thumbnails
        **kwargs: Additional worker configuration
        
    Returns:
        ThumbnailWorker instance
    """
    global thumbnail_worker
    thumbnail_worker = ThumbnailWorker(thumbnail_dir, **kwargs)
    return thumbnail_worker
