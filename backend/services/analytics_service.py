"""
Analytics Service - Orchestrates AI analytics pipeline

Manages the flow from completed files to analytics jobs.
Only included when BUILD_WITH_AI is enabled.
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional

from models import File, Job, Session as SessionModel
from models_analytics import FileAnalytics

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Service that manages AI analytics pipeline.
    
    Responsibilities:
    - Monitor completed files and queue analytics jobs
    - Respect time-of-day scheduling
    - Filter eligible files (skip CAM, ISO, empty)
    - Prevent duplicate analytics for same file
    - Provide filtering logic for charts and drill-downs
    """
    
    def __init__(self, db: Session):
        self.db = db
        self.enabled = True
        
    def should_process_now(self) -> bool:
        """
        Check if current time is within scheduled analytics hours.
        
        Returns:
            True if analytics should run now, False otherwise
        """
        # Get schedule settings from database
        from models import Setting
        
        start_hour_setting = self.db.query(Setting).filter(
            Setting.key == 'analytics_start_hour'
        ).first()
        end_hour_setting = self.db.query(Setting).filter(
            Setting.key == 'analytics_end_hour'
        ).first()
        schedule_enabled_setting = self.db.query(Setting).filter(
            Setting.key == 'analytics_schedule_enabled'
        ).first()

        # If schedule is disabled, run 24/7
        if schedule_enabled_setting and schedule_enabled_setting.value.lower() != 'true':
            return True
        
        # Default: 8pm to 6am (20:00 to 06:00)
        start_hour = int(start_hour_setting.value) if start_hour_setting else 20
        end_hour = int(end_hour_setting.value) if end_hour_setting else 6
        
        current_hour = datetime.now().hour
        
        # Handle overnight schedules (e.g., 20:00 to 06:00)
        if start_hour > end_hour:
            return current_hour >= start_hour or current_hour < end_hour
        else:
            return start_hour <= current_hour < end_hour
    
    def is_file_eligible(self, file: File) -> bool:
        """
        Check if file is eligible for analytics.
        
        Criteria:
        - File is COMPLETED
        - File is program output (is_program_output = True)
        - File is not empty (is_empty = False)
        - File is not ISO (is_iso = False)
        - File is not CAM file (filename doesn't contain 'CAM')
        
        Args:
            file: File to check
            
        Returns:
            True if file should be analyzed, False otherwise
        """
        if file.state != 'COMPLETED':
            return False
        
        if not file.is_program_output:
            logger.debug(f"Skipping {file.filename}: not program output")
            return False
        
        if file.is_empty:
            logger.debug(f"Skipping {file.filename}: empty file")
            return False
        
        if file.is_iso:
            logger.debug(f"Skipping {file.filename}: ISO file")
            return False
        
        # Check for CAM in filename
        if 'CAM' in file.filename.upper():
            logger.debug(f"Skipping {file.filename}: CAM file")
            return False
        
        return True
    
    def queue_analytics_for_file(self, file: File) -> Optional[Job]:
        """
        Create TRANSCRIBE job for a file if eligible.
        
        Args:
            file: File to queue for analytics
            
        Returns:
            Created Job object, or None if not queued
        """
        # Check if file is eligible
        if not self.is_file_eligible(file):
            logger.debug(f"File {file.filename} not eligible for analytics")
            return None
        
        # Check if analytics already exists
        existing_analytics = self.db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file.id
        ).first()
        
        if existing_analytics:
            if existing_analytics.state in ['COMPLETED', 'TRANSCRIBING', 'ANALYZING']:
                logger.debug(f"Analytics already exists for {file.filename} (state: {existing_analytics.state})")
                return None
            elif existing_analytics.state == 'FAILED':
                # Don't retry failed analytics automatically
                logger.debug(f"Analytics previously failed for {file.filename}")
                return None
        
        # Check if TRANSCRIBE job already exists
        existing_job = self.db.query(Job).filter(
            Job.file_id == file.id,
            Job.kind == 'TRANSCRIBE',
            Job.state.in_(['QUEUED', 'RUNNING'])
        ).first()
        
        if existing_job:
            logger.debug(f"TRANSCRIBE job already queued for {file.filename}")
            return existing_job
        
        # Create analytics record if it doesn't exist
        if not existing_analytics:
            # Format duration string (e.g. "1h 30m")
            duration_str = None
            if file.duration:
                hours = int(file.duration // 3600)
                minutes = int((file.duration % 3600) // 60)
                seconds = int(file.duration % 60)
                if hours > 0:
                    duration_str = f"{hours}h {minutes}m"
                else:
                    duration_str = f"{minutes}m {seconds}s"

            analytics = FileAnalytics(
                file_id=file.id,
                filename=file.filename,
                state='PENDING',
                duration_seconds=int(file.duration) if file.duration else None,
                duration=duration_str
            )
            self.db.add(analytics)
        
        # Create TRANSCRIBE job
        job = Job(
            file_id=file.id,
            kind='TRANSCRIBE',
            state='QUEUED',
            priority=200,  # Lower priority than video processing
            max_retries=1  # Retry once on failure
        )
        self.db.add(job)
        self.db.commit()
        
        logger.info(f"🎤 Queued TRANSCRIBE job for {file.filename}")
        return job
    
    def queue_pending_analytics(self) -> int:
        """
        Queue analytics for all eligible completed files that don't have analytics yet.
        
        Returns:
            Number of files queued
        """
        # Find completed files
        completed_files = self.db.query(File).filter(
            File.state == 'COMPLETED',
            File.is_program_output == True,
            File.is_empty == False,
            File.is_iso == False
        ).all()
        
        # Get set of file IDs that already have analytics
        existing_analytics_ids = {
            r[0] for r in self.db.query(FileAnalytics.file_id).all()
        }
        
        queued_count = 0
        for file in completed_files:
            # Skip CAM files
            if 'CAM' in file.filename.upper():
                continue
                
            # Skip if analytics already exists
            if file.id in existing_analytics_ids:
                continue
            
            # Try to queue (this will create the record and job)
            if self.queue_analytics_for_file(file):
                queued_count += 1
        
        if queued_count > 0:
            logger.info(f"📊 Queued {queued_count} files for analytics")
        
        return queued_count
    
    def get_analytics_stats(self) -> dict:
        """
        Get statistics about analytics processing.
        
        Returns:
            Dictionary with counts by state
        """
        stats = {}
        
        # Count by state
        state_counts = self.db.query(
            FileAnalytics.state,
            func.count(FileAnalytics.id)
        ).group_by(FileAnalytics.state).all()
        
        for state, count in state_counts:
            stats[state.lower()] = count
        
        # Count eligible files without analytics
        eligible_files = self.db.query(func.count(File.id)).filter(
            File.state == 'COMPLETED',
            File.is_program_output == True,
            File.is_empty == False,
            File.is_iso == False,
            ~File.filename.ilike('%CAM%')
        ).scalar()
        
        existing_analytics = self.db.query(func.count(FileAnalytics.id)).scalar()
        
        stats['eligible_without_analytics'] = eligible_files - (existing_analytics or 0)
        stats['total_eligible'] = eligible_files
        
        return stats
    
    def retry_failed_analytics(self, file_id: str) -> Optional[Job]:
        """
        Retry analytics for a file that failed.
        
        Args:
            file_id: ID of file to retry
            
        Returns:
            Created Job object, or None if cannot retry
        """
        analytics = self.db.query(FileAnalytics).filter(
            FileAnalytics.file_id == file_id
        ).first()
        
        if not analytics:
            logger.warning(f"No analytics found for file {file_id}")
            return None
        
        if analytics.state != 'FAILED':
            logger.warning(f"Analytics not in FAILED state for file {file_id}")
            return None
        
        # Reset state based on what failed
        if analytics.transcription_completed_at:
            # Transcription succeeded, analysis failed
            analytics.state = 'TRANSCRIBED'
            job_kind = 'ANALYZE'
        else:
            # Transcription failed
            analytics.state = 'PENDING'
            job_kind = 'TRANSCRIBE'
        
        analytics.error_message = None
        analytics.retry_count = 0
        
        # Create new job
        job = Job(
            file_id=file_id,
            kind=job_kind,
            state='QUEUED',
            priority=200,
            max_retries=1
        )
        self.db.add(job)
        self.db.commit()
        
        logger.info(f"🔄 Retrying {job_kind} for file {file_id}")
        return job


    def apply_time_filter(self, query, time_range: str):
        """
        Apply standard time range filtering to a query.
        Used by both Charts and Drill-down endpoints to ensure consistency.
        Expects query to be joined with SessionModel.
        """
        now = datetime.utcnow()
        start_date = None
        
        if time_range == "7d":
            start_date = now - timedelta(days=7)
        elif time_range == "30d":
            start_date = now - timedelta(days=30)
        elif time_range == "6m":
            start_date = now - timedelta(days=180)
        elif time_range == "12m":
            start_date = now - timedelta(days=365)
        elif time_range.isdigit() and len(time_range) == 4:
            # Year filter
            year = int(time_range)
            start_date = datetime(year, 1, 1)
            end_date = datetime(year, 12, 31, 23, 59, 59)
            # Apply both start and end for year
            query = query.filter(SessionModel.recording_date <= end_date.strftime("%Y-%m-%d"))
        
        if start_date:
            query = query.filter(SessionModel.recording_date >= start_date.strftime("%Y-%m-%d"))
            
        return query

    def apply_drilldown_filter(self, query, filter_type: str, filter_value: str):
        """
        Apply specific dimension filtering for drill-down.
        """
        if not filter_type or not filter_value:
            return query
            
        # Case-insensitive helpers
        val = filter_value.strip()
        
        if filter_type == 'faculty':
            query = query.filter(FileAnalytics.faculty == val)

        elif filter_type == 'campus':
            query = query.filter(SessionModel.campus == val)
            
        elif filter_type == 'content_type':
            query = query.filter(FileAnalytics.content_type == val)

        elif filter_type == 'language':
            query = query.filter(FileAnalytics.detected_language == val)
            
        elif filter_type == 'speaker' or filter_type == 'speaker_type':
            # Handle "Staff" matching "Staff, Student"
            query = query.filter(FileAnalytics.speaker.ilike(f"%{val}%"))
            
        elif filter_type == 'audience':
            query = query.filter(FileAnalytics.audience.ilike(f"%{val}%"))
            
        elif filter_type == 'speaker_count':
            try:
                count = int(val)
                query = query.filter(FileAnalytics.speaker_count == count)
            except ValueError:
                pass
                
        elif filter_type == 'date':
            # Handle date filtering from the Volume chart
            # Value could be "2025-02-14" (Day) or "2025-W07" (Week)
            if 'W' in val:
                # Week Logic: YYYY-Www
                try:
                    parts = val.split('-W')
                    if len(parts) == 2:
                        year = int(parts[0])
                        week = int(parts[1])
                        # Filter by SQLite strftime for week number
                        # Note: SQLite %W is 00-53, %Y is year
                        # This is an approximation as SQL week logic varies, 
                        # but matches the chart aggregation grouping
                        query = query.filter(func.strftime('%Y-W%W', SessionModel.recording_date) == val)
                except Exception:
                    logger.warning(f"Invalid week format for drilldown: {val}")
            else:
                # Specific Day Logic: YYYY-MM-DD
                query = query.filter(SessionModel.recording_date == val)

        elif filter_type == 'duration_range':
            # Handle duration buckets: "0-30s", "30s-1m", "1-5m", etc.
            # Use coalesce to fallback to File.duration if FileAnalytics.duration_seconds is null
            duration_col = func.coalesce(FileAnalytics.duration_seconds, File.duration, 0)
            
            if val == "0-30s":
                query = query.filter(duration_col < 30)
            elif val == "30s-1m":
                query = query.filter(duration_col >= 30, duration_col < 60)
            elif val == "1-5m":
                query = query.filter(duration_col >= 60, duration_col < 300)
            elif val == "5-10m":
                query = query.filter(duration_col >= 300, duration_col < 600)
            elif val == "10-20m":
                query = query.filter(duration_col >= 600, duration_col < 1200)
            elif val == "20-30m":
                query = query.filter(duration_col >= 1200, duration_col < 1800)
                
        return query

    def update_local_cache(self, file_id: str = None) -> dict:
        """
        Update local analytics cache with existing .mp3 files and thumbnails.
        
        Scans for COMPLETED files that don't have external_export_path set.
        Copies .mp3 and thumbnail to the configured cache directory.
        
        Args:
            file_id: Optional file ID to process only one file
            
        Returns:
            Dictionary with summary of processed files
        """
        from models import Setting
        import shutil
        from pathlib import Path
        
        # Get cache settings
        cache_enabled = self.db.query(Setting).filter(
            Setting.key == 'external_audio_export_enabled'
        ).first()
        
        cache_path_setting = self.db.query(Setting).filter(
            Setting.key == 'external_audio_export_path'
        ).first()
        
        if not cache_enabled or str(cache_enabled.value).lower() != 'true':
            return {'error': 'Local analytics cache is not enabled'}
            
        if not cache_path_setting or not cache_path_setting.value:
            return {'error': 'Local cache path is not configured'}
            
        cache_root = Path(cache_path_setting.value)
        if not cache_root.exists():
            try:
                cache_root.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return {'error': f'Could not create cache directory: {e}'}
                
        # Find eligible files
        query = self.db.query(File).filter(
            File.state == 'COMPLETED',
            File.is_program_output == True,
            File.is_empty == False,
            File.is_iso == False,
            File.external_export_path == None
        )
        
        if file_id:
            query = query.filter(File.id == file_id)
            
        files = query.all()
        
        stats = {
            'processed': 0,
            'skipped': 0,
            'failed': 0,
            'total': len(files)
        }
        
        logger.info(f"Starting cache update for {len(files)} files")
        
        for file in files:
            try:
                # Determine source paths
                if not file.path_final:
                    stats['skipped'] += 1
                    continue
                    
                final_path = Path(file.path_final)
                if not final_path.exists():
                    logger.warning(f"File not found: {final_path}")
                    stats['skipped'] += 1
                    continue
                    
                # Look for MP3 in "Source Files" subdirectory
                # Structure: .../Day/Filename.mp4 -> .../Day/Source Files/SessionName/Filename.mp3
                # Or if ISO: .../Day/Source Files/SessionName/Filename.mp4 -> .../Day/Source Files/SessionName/Filename.mp3
                
                mp3_path = None
                
                # Try standard location first
                session_folder = file.session_folder or (file.session.name if file.session else None) or 'unknown'
                
                # Check adjacent "Source Files" folder
                possible_mp3_dir = final_path.parent / "Source Files" / session_folder
                possible_mp3 = possible_mp3_dir / f"{file.session.name if file.session else final_path.stem}.mp3"
                
                if possible_mp3.exists():
                    mp3_path = possible_mp3
                else:
                    # Try finding any mp3 in that folder
                    if possible_mp3_dir.exists():
                        mp3s = list(possible_mp3_dir.glob("*.mp3"))
                        if mp3s:
                            mp3_path = mp3s[0]
                            
                if not mp3_path or not mp3_path.exists():
                    logger.debug(f"MP3 not found for {file.filename} at {possible_mp3}")
                    stats['skipped'] += 1
                    continue
                    
                # Create cache directory for this file
                file_cache_dir = cache_root / file.id
                file_cache_dir.mkdir(parents=True, exist_ok=True)
                
                # Copy MP3
                dest_mp3 = file_cache_dir / mp3_path.name
                if not dest_mp3.exists():
                    shutil.copy2(str(mp3_path), str(dest_mp3))
                    logger.info(f"Cached MP3 for {file.filename}")
                
                # Copy Thumbnail if available
                if file.thumbnail_path:
                    thumb_path = Path(file.thumbnail_path)
                    if thumb_path.exists():
                        dest_thumb = file_cache_dir / f"{file.session.name if file.session else final_path.stem}{thumb_path.suffix}"
                        if not dest_thumb.exists():
                            shutil.copy2(str(thumb_path), str(dest_thumb))
                            logger.info(f"Cached thumbnail for {file.filename}")
                            
                # Update database
                file.external_export_path = str(file_cache_dir)
                self.db.commit()
                stats['processed'] += 1
                
            except Exception as e:
                logger.error(f"Failed to cache {file.filename}: {e}")
                stats['failed'] += 1
                
        return stats