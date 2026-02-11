"""
Analytics Scheduler - Time-based job processing

Controls when analytics workers process jobs based on schedule.
Only included when BUILD_WITH_AI is enabled.
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy.orm import Session

from database import get_db
from services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)


class AnalyticsScheduler:
    """
    Background service that controls when analytics workers run.
    
    Features:
    - Time-of-day scheduling (e.g., 8pm-6am)
    - Automatic queue discovery
    - Graceful pause/resume of analytics processing
    - Configurable via GUI settings
    """
    
    def __init__(self):
        self.running = False
        self.task: asyncio.Task = None
        self.analytics_enabled = True  # Can be toggled to pause analytics
        
    def start(self):
        """Start the scheduler background task"""
        if self.running:
            logger.warning("Scheduler already running")
            return
        
        self.running = True
        self.task = asyncio.create_task(self._run())
        logger.info("✅ Analytics scheduler started")
    
    def stop(self):
        """Stop the scheduler background task"""
        if not self.running:
            return
        
        self.running = False
        if self.task:
            self.task.cancel()
        logger.info("🛑 Analytics scheduler stopped")
    
    def pause_analytics(self):
        """Pause analytics processing (without stopping scheduler)"""
        self.analytics_enabled = False
        logger.info("⏸️ Analytics processing paused")
    
    def resume_analytics(self):
        """Resume analytics processing"""
        self.analytics_enabled = True
        logger.info("▶️ Analytics processing resumed")
    
    async def _run(self):
        """
        Main scheduler loop.
        
        Checks every 5 minutes:
        1. Is it within scheduled hours?
        2. Are there files waiting for analytics?
        3. Queue analytics jobs if appropriate
        """
        check_interval = 300  # 5 minutes
        
        logger.info("📊 Analytics scheduler running...")
        
        while self.running:
            try:
                await self._check_and_queue()
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                logger.info("Scheduler task cancelled")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}", exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(check_interval)
    
    async def _check_and_queue(self):
        """
        Check if we should queue analytics and do so if appropriate.
        """
        if not self.analytics_enabled:
            return
        
        # Get database session
        db = next(get_db())
        try:
            analytics_service = AnalyticsService(db)
            
            # Check if we're in scheduled hours
            if not analytics_service.should_process_now():
                logger.debug("Outside scheduled analytics hours")
                return
            
            # Check if there are pending files
            stats = analytics_service.get_analytics_stats()
            pending_count = stats.get('eligible_without_analytics', 0)
            
            if pending_count > 0:
                logger.info(f"📊 Found {pending_count} files eligible for analytics")
                
                # Queue pending analytics
                queued = analytics_service.queue_pending_analytics()
                
                if queued > 0:
                    logger.info(f"✅ Queued {queued} analytics jobs")
            else:
                logger.debug("No pending files for analytics")
                
        finally:
            db.close()
    
    def get_status(self) -> dict:
        """
        Get scheduler status information.
        
        Returns:
            Dictionary with scheduler state
        """
        db = next(get_db())
        try:
            analytics_service = AnalyticsService(db)
            
            return {
                'running': self.running,
                'enabled': self.analytics_enabled,
                'in_scheduled_hours': analytics_service.should_process_now(),
                'current_hour': datetime.now().hour,
                'stats': analytics_service.get_analytics_stats()
            }
        finally:
            db.close()


# Global scheduler instance
scheduler = AnalyticsScheduler()


def start_scheduler():
    """Start the analytics scheduler (call on app startup)"""
    scheduler.start()


def stop_scheduler():
    """Stop the analytics scheduler (call on app shutdown)"""
    scheduler.stop()


def get_scheduler() -> AnalyticsScheduler:
    """Get the global scheduler instance"""
    return scheduler
