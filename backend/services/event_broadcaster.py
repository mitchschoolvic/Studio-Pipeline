"""
Event Broadcasting Service

This service provides helper functions for workers to broadcast
state changes and progress updates via WebSocket to connected clients.
"""
from services.websocket import manager
from models import Event, Job, File
from sqlalchemy.orm import Session
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """
    Service for creating database Event records and broadcasting
    real-time updates to WebSocket clients.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def log_and_broadcast_file_state(
        self,
        file: File,
        new_state: str,
        message: str = None,
        progress_pct: float = None
    ):
        """
        Log a file state change to database and broadcast via WebSocket
        
        Args:
            file: File model instance
            new_state: New file state
            message: Optional event message
            progress_pct: Optional progress percentage
        """
        # Create event record
        event = Event(
            file_id=file.id,
            event_type='file_state_change',
            message=message or f"File state changed to {new_state}",
            metadata={
                'old_state': file.state,
                'new_state': new_state,
                'progress_pct': progress_pct
            }
        )
        self.db.add(event)
        self.db.commit()
        
        # Broadcast to WebSocket clients
        await manager.send_file_update(
            file_id=str(file.id),
            state=new_state,
            session_id=str(file.session_id),
            progress_pct=progress_pct,
            error_message=file.error_message,
            filename=file.filename
        )
        
        logger.info(f"File {file.filename} state: {file.state} → {new_state}")
    
    async def log_and_broadcast_job_progress(
        self,
        job: Job,
        progress_pct: float,
        stage: str = None,
        message: str = None
    ):
        """
        Log job progress to database and broadcast via WebSocket
        
        Args:
            job: Job model instance
            progress_pct: Progress percentage (0-100)
            stage: Optional stage description
            message: Optional event message
        """
        # Create event record
        event = Event(
            file_id=job.file_id,
            event_type='job_progress',
            message=message or f"{job.kind} job progress: {progress_pct:.1f}%",
            metadata={
                'job_id': str(job.id),
                'job_kind': job.kind,
                'progress_pct': progress_pct,
                'stage': stage
            }
        )
        self.db.add(event)
        self.db.commit()
        
        # Broadcast to WebSocket clients
        await manager.send_job_progress(
            job_id=str(job.id),
            progress_pct=progress_pct,
            stage=stage
        )
        
        logger.debug(f"Job {job.id} ({job.kind}): {progress_pct:.1f}% - {stage or 'in progress'}")
    
    async def log_and_broadcast_session_discovered(
        self,
        session_id: str,
        session_name: str,
        file_count: int
    ):
        """
        Broadcast new session discovery
        
        Args:
            session_id: UUID of the session
            session_name: Session name
            file_count: Number of files in session
        """
        await manager.send_session_discovered(
            session_id=session_id,
            session_name=session_name,
            file_count=file_count
        )
        
        logger.info(f"Session discovered: {session_name} ({file_count} files)")
    
    async def log_and_broadcast_error(
        self,
        error_type: str,
        error_message: str,
        file_id: str = None,
        job_id: str = None
    ):
        """
        Log error to database and broadcast via WebSocket
        
        Args:
            error_type: Type of error
            error_message: Error message
            file_id: Optional file UUID
            job_id: Optional job UUID
        """
        # Create event record if we have a file_id
        if file_id:
            event = Event(
                file_id=file_id,
                event_type='error',
                message=error_message,
                metadata={
                    'error_type': error_type,
                    'job_id': job_id
                }
            )
            self.db.add(event)
            self.db.commit()
        
        # Broadcast to WebSocket clients
        await manager.send_error(
            error_type=error_type,
            error_message=error_message,
            context={'file_id': file_id, 'job_id': job_id}
        )
        
        logger.error(f"Error broadcast: {error_type} - {error_message}")


# Convenience functions for workers (synchronous wrappers)
def create_file_state_event(db: Session, file: File, new_state: str, message: str = None):
    """
    Create a file state change event (synchronous)
    
    Note: This only creates the DB record. For real-time broadcasting,
    use EventBroadcaster.log_and_broadcast_file_state() in async context.
    """
    event = Event(
        file_id=file.id,
        event_type='file_state_change',
        message=message or f"File state changed to {new_state}",
        metadata={
            'old_state': file.state,
            'new_state': new_state
        }
    )
    db.add(event)
    db.commit()
    logger.debug(f"Event created: {event.event_type} for file {file.id}")


def create_job_progress_event(db: Session, job: Job, progress_pct: float, stage: str = None):
    """
    Create a job progress event (synchronous)
    
    Note: This only creates the DB record. For real-time broadcasting,
    use EventBroadcaster.log_and_broadcast_job_progress() in async context.
    """
    event = Event(
        file_id=job.file_id,
        event_type='job_progress',
        message=f"{job.kind} job progress: {progress_pct:.1f}%",
        metadata={
            'job_id': str(job.id),
            'job_kind': job.kind,
            'progress_pct': progress_pct,
            'stage': stage
        }
    )
    db.add(event)
    db.commit()
    logger.debug(f"Event created: {event.event_type} - {progress_pct:.1f}%")
