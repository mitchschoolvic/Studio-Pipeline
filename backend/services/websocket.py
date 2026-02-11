"""
WebSocket connection manager for real-time updates

ARCHITECTURE NOTE: Non-blocking broadcast design
- Each connection has a dedicated send queue and sender task
- Broadcasts are non-blocking - messages are queued per-client
- Slow clients won't block fast clients
- Full queues result in dropped messages (logged) rather than blocking
"""
from fastapi import WebSocket
from typing import Set, Dict
import asyncio
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts messages to all connected clients.

    This service enables real-time updates to the frontend when:
    - Files change state (DISCOVERED → COPIED → PROCESSED → COMPLETED)
    - Jobs progress (0% → 100%)
    - New sessions are discovered
    - Errors occur

    Features non-blocking broadcast design to handle high message volumes.
    """

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.connection_metadata: Dict[WebSocket, dict] = {}
        self.send_queues: Dict[WebSocket, asyncio.Queue] = {}
        self.sender_tasks: Dict[WebSocket, asyncio.Task] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str = None):
        """
        Register a new WebSocket connection with non-blocking sender

        Args:
            websocket: FastAPI WebSocket connection
            client_id: Optional client identifier
        """
        await websocket.accept()
        self.active_connections.add(websocket)
        self.connection_metadata[websocket] = {
            'client_id': client_id or f"client-{id(websocket)}",
            'connected_at': datetime.utcnow().isoformat()
        }

        # Create dedicated send queue and sender task for this connection
        self.send_queues[websocket] = asyncio.Queue(maxsize=1000)
        self.sender_tasks[websocket] = asyncio.create_task(
            self._sender_loop(websocket)
        )

        logger.warning(f"✅ WebSocket client connected (ID: {self.connection_metadata[websocket]['client_id']}). Total connections: {len(self.active_connections)}")

        # Send welcome message
        await websocket.send_json({
            "type": "connection",
            "status": "connected",
            "message": "Connected to Studio Pipeline WebSocket"
        })
    
    def disconnect(self, websocket: WebSocket):
        """
        Unregister a WebSocket connection and cleanup resources

        Args:
            websocket: FastAPI WebSocket connection
        """
        client_id = self.connection_metadata.get(websocket, {}).get('client_id')

        # Cancel sender task
        if websocket in self.sender_tasks:
            self.sender_tasks[websocket].cancel()
            del self.sender_tasks[websocket]

        # Cleanup
        self.active_connections.discard(websocket)
        self.connection_metadata.pop(websocket, None)
        self.send_queues.pop(websocket, None)

        logger.warning(f"🔌 WebSocket client disconnected (ID: {client_id}). Total connections: {len(self.active_connections)}")

    async def _sender_loop(self, websocket: WebSocket):
        """
        Dedicated sender task for each connection.
        Pulls messages from queue and sends without blocking other connections.

        Args:
            websocket: WebSocket connection to send to
        """
        queue = self.send_queues[websocket]

        try:
            while True:
                # Wait for next message
                message = await queue.get()

                try:
                    if isinstance(message, dict):
                        message = json.dumps(message)
                    await websocket.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send to client: {e}")
                    # Connection is dead, will be cleaned up by disconnect()
                    break

        except asyncio.CancelledError:
            # Normal shutdown
            pass
        except Exception as e:
            logger.error(f"Error in sender loop: {e}", exc_info=True)

    async def broadcast(self, message: dict, exclude: Set[WebSocket] = None):
        """
        Non-blocking broadcast to all connections.
        Messages are queued per-connection and sent asynchronously.

        Args:
            message: Dictionary to be sent as JSON to all clients
            exclude: Optional set of connections to exclude from broadcast

        Message format:
        {
            "type": "file_state_change" | "job_progress" | "session_discovered" | "error",
            "data": {...}
        }
        """
        if not self.active_connections:
            logger.debug(f"No active connections to broadcast message type: {message.get('type')}")
            return

        exclude = exclude or set()

        # Add timestamp if not present
        if 'timestamp' not in message:
            message['timestamp'] = datetime.utcnow().isoformat()

        # Convert message to JSON string once
        json_message = json.dumps(message)

        queued_count = 0
        full_queues = 0

        for connection in list(self.active_connections):
            if connection in exclude:
                continue

            queue = self.send_queues.get(connection)
            if not queue:
                continue

            try:
                # Non-blocking put with immediate return if queue is full
                queue.put_nowait(json_message)
                queued_count += 1
            except asyncio.QueueFull:
                full_queues += 1
                logger.warning(
                    f"Send queue full for client "
                    f"{self.connection_metadata.get(connection, {}).get('client_id')}, "
                    f"dropping message type: {message.get('type')}"
                )

        if full_queues > 0:
            logger.warning(f"Dropped message to {full_queues} clients (full queues)")
        else:
            logger.debug(f"Queued {message.get('type')} to {queued_count} clients")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        Send message to specific connection

        Args:
            message: Dictionary to be sent as JSON
            websocket: Target WebSocket connection
        """
        queue = self.send_queues.get(websocket)
        if not queue:
            logger.warning("Cannot send to disconnected client")
            return

        # Add timestamp if not present
        if 'timestamp' not in message:
            message['timestamp'] = datetime.utcnow().isoformat()

        try:
            message_str = json.dumps(message) if isinstance(message, dict) else message
            await queue.put(message_str)
        except asyncio.QueueFull:
            logger.warning(f"Queue full, dropping personal message type: {message.get('type')}")

    async def send_file_update(
        self, 
        file_id: str, 
        state: str, 
        session_id: str = None,
        progress_pct: float = None, 
        error_message: str = None, 
        progress_stage: str = None, 
        copy_speed_mbps: float = None,
        filename: str = None
    ):
        """
        Broadcast a file state change
        
        Args:
            file_id: UUID of the file
            state: New file state (DISCOVERED, COPIED, PROCESSING, PROCESSED, ORGANIZING, COMPLETED, FAILED)
            session_id: UUID of the session (REQUIRED for frontend cache updates)
            progress_pct: Optional overall progress percentage
            error_message: Optional error message if state is FAILED
            progress_stage: Optional description of the current progress stage
            copy_speed_mbps: Optional copy speed in MB/s
            filename: Optional filename for logging/display
        """
        message = {
            "type": "file_state_change",
            "data": {
                "file_id": file_id,
                "session_id": session_id,
                "state": state,
                "progress_pct": progress_pct,
                "error_message": error_message,
                "progress_stage": progress_stage,
                "copy_speed_mbps": copy_speed_mbps,
                "filename": filename
            }
        }
        await self.broadcast(message)

    async def send_onedrive_status_update(
        self,
        file_id: str,
        status_code: str,
        status_label: str | None = None,
        is_uploaded: bool | None = None,
        is_downloaded: bool | None = None,
        uploaded_at_iso: str | None = None,
    ):
        """
        Broadcast OneDrive upload status update for a file.

        Message type: onedrive_status_change
        """
        message = {
            "type": "onedrive_status_change",
            "data": {
                "file_id": file_id,
                "status_code": status_code,
                "status_label": status_label,
                "is_uploaded": is_uploaded,
                "is_downloaded": is_downloaded,
                "uploaded_at": uploaded_at_iso,
            },
        }
        await self.broadcast(message)
    
    async def send_job_progress(self, job_id: str, progress_pct: float, stage: str = None):
        """
        Broadcast job progress update
        
        Args:
            job_id: UUID of the job
            progress_pct: Progress percentage (0-100)
            stage: Optional stage description (e.g., "Extracting audio", "Denoising")
        """
        message = {
            "type": "job_progress",
            "data": {
                "job_id": job_id,
                "progress_pct": progress_pct,
                "stage": stage
            }
        }
        await self.broadcast(message)

    async def send_thumbnail_update(self, file_id: str, thumbnail_state: str, etag: str | None = None, thumbnail_path: str | None = None, error: str | None = None):
        """
        Broadcast thumbnail state update for a file.

        Args:
            file_id: UUID of the file
            thumbnail_state: PENDING | GENERATING | READY | FAILED | SKIPPED
            etag: Optional ETag/version hint for cache busting on the client
            thumbnail_path: Optional server-side path (for debugging/diagnostics)
            error: Optional error message when FAILED
        """
        message = {
            "type": "thumbnail_update",
            "data": {
                "file_id": file_id,
                "thumbnail_state": thumbnail_state,
                "etag": etag,
                "error": error,
                # Path omitted from UI logic; included only for potential diagnostics
                "_thumbnail_path": thumbnail_path,
            }
        }
        await self.broadcast(message)

    async def send_waveform_update(self, file_id: str, waveform_state: str, error: str | None = None):
        """
        Broadcast waveform generation state update for a file.

        Args:
            file_id: UUID of the file
            waveform_state: PENDING | GENERATING | READY | FAILED
            error: Optional error message when FAILED
        """
        message = {
            "type": "waveform_update",
            "data": {
                "file_id": file_id,
                "waveform_state": waveform_state,
                "error": error,
            }
        }
        await self.broadcast(message)
    
    async def send_session_discovered(self, session_id: str, session_name: str, file_count: int):
        """
        Broadcast new session discovery
        
        Args:
            session_id: UUID of the session
            session_name: Session name (e.g., "HyperDeck")
            file_count: Number of files in the session
        """
        message = {
            "type": "session_discovered",
            "data": {
                "session_id": session_id,
                "session_name": session_name,
                "file_count": file_count
            }
        }
        await self.broadcast(message)

    async def send_analytics_state(self, file_id: str, filename: str, state: str, extra: dict | None = None):
        """Broadcast analytics state change for a file.

        States: TRANSCRIBING, TRANSCRIBED, ANALYZING, COMPLETED, FAILED
        """
        payload = {
            "type": "analytics.state",
            "data": {
                "file_id": file_id,
                "filename": filename,
                "state": state
            }
        }
        if extra:
            payload["data"].update(extra)
        await self.broadcast(payload)
    
    async def send_error(self, error_type: str, error_message: str, context: dict = None):
        """
        Broadcast error notification
        
        Args:
            error_type: Type of error (e.g., "ftp_connection_failed", "processing_failed")
            error_message: Human-readable error message
            context: Optional additional context (file_id, job_id, etc.)
        """
        message = {
            "type": "error",
            "data": {
                "error_type": error_type,
                "error_message": error_message,
                "context": context or {}
            }
        }
        await self.broadcast(message)
    
    async def send_file_missing(self, file_id: str, filename: str, session_id: str):
        """
        Broadcast file missing notification
        
        Args:
            file_id: UUID of the missing file
            filename: Name of the file that went missing
            session_id: Session ID the file belongs to
        """
        message = {
            "type": "file_missing",
            "data": {
                "file_id": file_id,
                "filename": filename,
                "session_id": session_id
            }
        }
        await self.broadcast(message)
    
    async def send_file_reappeared(self, file_id: str, filename: str, session_id: str):
        """
        Broadcast file reappeared notification
        
        Args:
            file_id: UUID of the file that reappeared
            filename: Name of the file
            session_id: Session ID the file belongs to
        """
        message = {
            "type": "file_reappeared",
            "data": {
                "file_id": file_id,
                "filename": filename,
                "session_id": session_id
            }
        }
        await self.broadcast(message)
    
    async def send_processing_substep_update(
        self,
        file_id: str,
        substep: str,
        substep_progress: int,
        session_id: str = None,
        detail: str = None
    ):
        """
        Broadcast processing substep progress update

        This enables detailed UI visualization of processing stages:
        - extract: Extracting audio tracks
        - boost: Boosting audio levels
        - denoise: Applying noise reduction
        - convert: Converting to high-quality format
        - remux: Remuxing video with enhanced audio
        - quadsplit: Creating quad-split view

        Args:
            file_id: UUID of the file being processed
            substep: Current processing substep ('extract', 'boost', 'denoise', etc.)
            substep_progress: Progress within this substep (0-100)
            session_id: UUID of the session (for frontend cache updates)
            detail: Optional human-readable detail (e.g., "Applying noise reduction to audio track 2 of 4")
        """
        message = {
            "type": "processing_substep",
            "data": {
                "file_id": file_id,
                "session_id": session_id,
                "substep": substep,
                "progress": substep_progress,
                "detail": detail
            }
        }
        await self.broadcast(message)

    async def send_ftp_connection_status(self, connected: bool, host: str = None, port: int = None, error_message: str = None):
        """
        Broadcast FTP connection status update

        Args:
            connected: Whether FTP is connected
            host: FTP server host
            port: FTP server port
            error_message: Error message if connection failed
        """
        message = {
            "type": "ftp_connection_status",
            "data": {
                "connected": connected,
                "host": host,
                "port": port,
                "error_message": error_message
            }
        }
        await self.broadcast(message)

    async def send_worker_status(self, workers: list, queue_counts: dict, paused: dict):
        """
        Broadcast worker status update

        Args:
            workers: List of worker status dictionaries
            queue_counts: Dictionary of queue counts by job kind
            paused: Dictionary of pause states
        """
        message = {
            "type": "worker_status",
            "data": {
                "workers": workers,
                "queue_counts": queue_counts,
                "paused": paused
            }
        }
        await self.broadcast(message)


# Global connection manager instance
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint handler
    
    Maintains connection and handles incoming messages (keepalive, commands, etc.)
    """
    from fastapi import WebSocketDisconnect
    
    await manager.connect(websocket)
    
    try:
        while True:
            # Receive messages from client (e.g., ping/pong for keepalive)
            data = await websocket.receive_text()
            
            # Parse and handle client messages
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                if message_type == "ping":
                    # Respond to keepalive
                    await websocket.send_json({"type": "pong"})
                    logger.debug("Received ping, sent pong")
                elif message_type == "subscribe":
                    # Future: handle subscription to specific events
                    logger.debug(f"Client subscription request: {message}")
                else:
                    logger.warning(f"Unknown message type: {message_type}")
            
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from client: {data}")
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket client disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error: {type(e).__name__}: {e}")
    finally:
        manager.disconnect(websocket)
