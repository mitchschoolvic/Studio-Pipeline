"""
Reconciler Service

Periodically checks the database for new Event records and broadcasts them
to WebSocket clients. Also performs periodic FTP file reconciliation to detect
missing files. This ensures events created by workers (which may not have async
context) are still delivered to the frontend in real-time.
"""
import asyncio
import json
from sqlalchemy.orm import Session
from sqlalchemy import and_
from database import get_db
from models import Event, File, Job, Setting, Session as SessionModel
from services.websocket import manager
from services.ftp_config_service import FTPConfigService
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class Reconciler:
    """
    Service that polls the database for new events and broadcasts them
    via WebSocket to connected clients.
    
    Also performs periodic FTP file reconciliation to detect missing files.
    This is needed because workers run in their own async contexts and
    may create Event records without direct access to the WebSocket manager.
    """
    
    def __init__(self, poll_interval: float = 0.5, ftp_check_interval: float = 5):
        """
        Initialize reconciler

        Args:
            poll_interval: How often to check for new events (seconds)
            ftp_check_interval: How often to check FTP for missing files (seconds, default 5 seconds)
        """
        self.poll_interval = poll_interval
        self.ftp_check_interval = ftp_check_interval
        self.last_event_id = None
        self.last_ftp_check = None
        self.last_ftp_status_check = None
        self.last_ftp_connected = None  # Track last known FTP connection state
        self.last_time_broadcast = None  # Track last server time broadcast
        self.running = False
    
    async def start(self):
        """Start the reconciler service"""
        self.running = True
        
        # Read FTP check interval from database settings if available
        db = next(get_db())
        try:
            ftp_interval_setting = db.query(Setting).filter(Setting.key == "ftp_check_interval").first()
            if ftp_interval_setting:
                try:
                    self.ftp_check_interval = float(ftp_interval_setting.value)
                except ValueError:
                    logger.warning(f"Invalid ftp_check_interval setting: {ftp_interval_setting.value}, using default")
        finally:
            db.close()
        
        logger.info(f"Reconciler started (polling every {self.poll_interval}s, FTP check every {self.ftp_check_interval}s)")
        
        loop_count = 0
        while self.running:
            loop_count += 1
            if loop_count % 10 == 1:  # Log every 10th iteration
                logger.info(f"Reconciler loop iteration {loop_count}, running={self.running}")
            
            try:
                await self._process_new_events()

                # Broadcast server time every second for debugging
                now = datetime.now()
                if self.last_time_broadcast is None or (now - self.last_time_broadcast).total_seconds() >= 1:
                    await manager.broadcast({
                        'type': 'server_time',
                        'data': {
                            'time': now.strftime('%H:%M:%S'),
                            'timestamp': now.isoformat()
                        }
                    })
                    self.last_time_broadcast = now

                # Check if it's time for FTP connection status check (every 30 seconds)
                if self.last_ftp_status_check is None or (now - self.last_ftp_status_check).total_seconds() >= 30:
                    await self._check_ftp_connection_status()
                    self.last_ftp_status_check = now

                # Check if it's time for FTP reconciliation
                if self.last_ftp_check is None or (now - self.last_ftp_check).total_seconds() >= self.ftp_check_interval:
                    logger.info(f"Triggering FTP reconciliation (iteration {loop_count})")
                    await self._reconcile_missing_files()
                    self.last_ftp_check = now

            except Exception as e:
                logger.error(f"Reconciler error: {e}", exc_info=True)
            
            await asyncio.sleep(self.poll_interval)
    
    async def stop(self):
        """Stop the reconciler service"""
        self.running = False
        logger.info("Reconciler stopped")
    
    async def _process_new_events(self):
        """
        Check for new events and broadcast them
        """
        # Get a database session
        db = next(get_db())
        
        try:
            # Query for events created after last processed event
            query = db.query(Event).order_by(Event.created_at, Event.id)
            
            if self.last_event_id:
                # Get events after last processed ID
                query = query.filter(Event.id > self.last_event_id)
            else:
                # First run - only get events from last 10 seconds to avoid flooding
                cutoff_time = datetime.utcnow() - timedelta(seconds=10)
                query = query.filter(Event.created_at >= cutoff_time)
            
            events = query.limit(100).all()  # Process in batches
            
            if not events:
                return
            
            # Process each event
            for event in events:
                await self._broadcast_event(db, event)
                self.last_event_id = event.id
            
            logger.debug(f"Processed {len(events)} events")
        
        finally:
            db.close()
    
    async def _broadcast_event(self, db: Session, event: Event):
        """
        Broadcast a single event to WebSocket clients
        
        Args:
            db: Database session
            event: Event model instance
        """
        event_type = event.event_type
        
        # Parse JSON payload
        try:
            payload = json.loads(event.payload_json) if event.payload_json else {}
        except json.JSONDecodeError:
            logger.error(f"Failed to parse event payload JSON for event {event.id}")
            payload = {}
        
        try:
            if event_type == 'file_state_change':
                # Get current file state
                file = db.query(File).get(event.file_id)
                if file:
                    # Incremental analytics state piggyback if available
                    analytics_state = None
                    if hasattr(file, 'analytics') and file.analytics:
                        # Handle case where relationship returns a list (InstrumentedList)
                        if isinstance(file.analytics, list) or hasattr(file.analytics, '__iter__'):
                            analytics_obj = file.analytics[0] if len(file.analytics) > 0 else None
                        else:
                            analytics_obj = file.analytics
                        
                        if analytics_obj:
                            analytics_state = analytics_obj.state
                    
                    await manager.send_file_update(
                        file_id=str(file.id),
                        state=file.state,
                        session_id=str(file.session_id) if file.session_id else payload.get('session_id'),
                        progress_pct=payload.get('progress_pct'),
                        error_message=file.error_message,
                        progress_stage=payload.get('progress_stage'),
                        copy_speed_mbps=payload.get('copy_speed_mbps'),
                        filename=file.filename
                    )
                    if analytics_state:
                        await manager.send_analytics_state(file.id, file.filename, analytics_state)
            
            elif event_type == 'job_progress':
                # Get current job state
                job_id = payload.get('job_id')
                if job_id:
                    job = db.query(Job).get(job_id)
                    if job:
                        await manager.send_job_progress(
                            job_id=str(job.id),
                            progress_pct=job.progress_pct or payload.get('progress_pct', 0),
                            stage=job.progress_stage or payload.get('stage')
                        )
            
            elif event_type == 'session_discovered':
                # Broadcast session_discovered so frontend can add new sessions to the list
                session_id = payload.get('session_id')
                # Get session data if available
                session_data = None
                if session_id:
                    session = db.query(SessionModel).get(session_id)
                    if session:
                        session_data = {
                            'id': session.id,
                            'name': session.name,
                            'file_count': session.file_count or 0,
                            'recording_date': session.recording_date.isoformat() if session.recording_date else None,
                            'recording_time': session.recording_time.isoformat() if session.recording_time else None,
                            'discovered_at': session.discovered_at.isoformat() if session.discovered_at else None,
                            'total_size': session.total_size or 0
                        }
                
                await manager.broadcast({
                    'type': 'session_discovered',
                    'data': {
                        'session_id': session_id,
                        'session_name': payload.get('session_name'),
                        'filename': payload.get('filename'),
                        'file_count': payload.get('file_count', 0),
                        'session': session_data  # Include full session data for frontend
                    }
                })
            
            elif event_type == 'error':
                await manager.send_error(
                    error_type=payload.get('error_type', 'unknown'),
                    error_message=payload.get('error_message', 'Unknown error'),
                    context=payload
                )
            
            elif event_type == 'file_missing':
                logger.info(f"📤 Broadcasting file_missing event for file {event.file_id}")
                await manager.send_file_missing(
                    file_id=event.file_id,
                    filename=payload.get('filename', 'unknown'),
                    session_id=payload.get('session_id', '')
                )
            
            elif event_type == 'file_reappeared':
                logger.info(f"📤 Broadcasting file_reappeared event for file {event.file_id}")
                await manager.send_file_reappeared(
                    file_id=event.file_id,
                    filename=payload.get('filename', 'unknown'),
                    session_id=payload.get('session_id', '')
                )
            
            else:
                logger.warning(f"Unknown event type: {event_type}")
        
        except Exception as e:
            logger.error(f"Failed to broadcast event {event.id}: {e}", exc_info=True)
    
    async def _check_ftp_connection_status(self):
        """
        Check FTP server connection status and broadcast updates if status changes.
        This runs periodically to keep the frontend informed about FTP connectivity.
        """
        db = next(get_db())

        try:
            # Check if FTP is configured
            if not FTPConfigService.is_ftp_configured(db):
                logger.debug("FTP not configured, skipping connection status check")
                return

            # Get FTP configuration
            ftp_config = FTPConfigService.get_ftp_config(db)
            host = ftp_config.get('host')
            port = ftp_config.get('port', 21)

            # Try to connect to FTP
            try:
                from workers.ftp_client import FTPClient
                ftp_client = FTPClient(
                    host=host,
                    port=port,
                    username=ftp_config.get('username', 'anonymous'),
                    password=ftp_config.get('password', '')
                )

                # Attempt connection with timeout
                await asyncio.wait_for(ftp_client.connect(), timeout=10)
                await ftp_client.disconnect()

                # Connection successful
                is_connected = True
                error_message = None
                logger.debug(f"FTP connection check: Connected to {host}:{port}")

            except asyncio.TimeoutError:
                is_connected = False
                error_message = f"Connection timeout to {host}:{port}"
                logger.warning(f"FTP connection check: {error_message}")

            except Exception as e:
                is_connected = False
                error_message = str(e)
                logger.warning(f"FTP connection check: Failed - {error_message}")

            # Only broadcast if status changed
            if self.last_ftp_connected is None or self.last_ftp_connected != is_connected:
                logger.info(f"🔌 FTP connection status changed: {'Connected' if is_connected else 'Disconnected'}")
                await manager.send_ftp_connection_status(
                    connected=is_connected,
                    host=host,
                    port=port,
                    error_message=error_message
                )
                self.last_ftp_connected = is_connected

        except Exception as e:
            logger.error(f"Failed to check FTP connection status: {e}", exc_info=True)
        finally:
            db.close()

    async def _reconcile_missing_files(self):
        """
        Check FTP server and mark files as missing if they no longer exist.
        This runs periodically to keep the database in sync with FTP reality.

        Skips reconciliation if there are active copy jobs to avoid interfering
        with file transfers.
        """
        db = next(get_db())

        try:
            # Check if there are any active copy jobs
            active_copy_jobs = db.query(Job).filter(
                Job.kind == 'COPY',
                Job.state == 'RUNNING'
            ).count()

            if active_copy_jobs > 0:
                logger.debug(f"Skipping FTP reconciliation - {active_copy_jobs} active copy job(s) in progress")
                return

            # Check if FTP is configured
            if not FTPConfigService.is_ftp_configured(db):
                logger.debug("FTP not configured, skipping missing file check")
                return

            # Get FTP configuration using centralized service
            ftp_config = FTPConfigService.get_ftp_config(db)

            # Import here to avoid circular dependency
            from services.discovery import DiscoveryService

            # Create discovery service and run reconciliation
            discovery = DiscoveryService(db, ftp_config)
            await discovery.discover_and_create_files()

            logger.debug("Missing file reconciliation completed")

        except (OSError, ConnectionRefusedError, asyncio.TimeoutError) as e:
            # Broadcast connection error to frontend
            logger.error(f"FTP connection failed during reconciliation: {e}")
            
            # Get host/port for the error message if possible
            host = "unknown"
            port = 21
            try:
                if 'ftp_config' in locals():
                    host = ftp_config.get('host', 'unknown')
                    port = ftp_config.get('port', 21)
            except:
                pass

            await manager.send_ftp_connection_status(
                connected=False,
                host=host,
                port=port,
                error_message=str(e)
            )

        except Exception as e:
            logger.error(f"Failed to reconcile missing files: {e}", exc_info=True)
        finally:
            db.close()
    
    def get_status(self) -> dict:
        """Get reconciler status including last scan times"""
        return {
            'running': self.running,
            'ftp_check_interval': self.ftp_check_interval,
            'last_ftp_scan': self.last_ftp_check.isoformat() if self.last_ftp_check else None,
            'last_ftp_status_check': self.last_ftp_status_check.isoformat() if self.last_ftp_status_check else None,
            'ftp_connected': self.last_ftp_connected,
        }


# Global reconciler instance
reconciler = Reconciler(poll_interval=0.5, ftp_check_interval=5)
_reconciler_task = None


def get_reconciler_status() -> dict:
    """Get the current reconciler status (for API endpoints)"""
    return reconciler.get_status()


async def start_reconciler():
    """Start the reconciler service (call from FastAPI startup)"""
    global _reconciler_task
    _reconciler_task = asyncio.create_task(reconciler.start())
    logger.info("Reconciler service started")


async def stop_reconciler():
    """Stop the reconciler service (call from FastAPI shutdown)"""
    global _reconciler_task
    await reconciler.stop()
    if _reconciler_task:
        _reconciler_task.cancel()
        try:
            await _reconciler_task
        except asyncio.CancelledError:
            pass
    logger.info("Reconciler service stopped")
