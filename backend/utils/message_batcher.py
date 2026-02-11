"""
Message batching utility for WebSocket messages.

Batches WebSocket messages to reduce network overhead and improve performance.
Messages are grouped by type and sent in configurable intervals.
"""
import asyncio
import json
from typing import Dict, List, Callable, Awaitable
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class MessageBatcher:
    """
    Batches WebSocket messages to reduce network overhead and improve performance.
    Messages are grouped by type and sent in configurable intervals.
    """

    def __init__(
        self,
        batch_interval: float = 0.5,
        max_batch_size: int = 50,
        send_callback: Callable[[dict], Awaitable[None]] = None
    ):
        """
        Initialize message batcher.

        Args:
            batch_interval: Seconds between batch flushes
            max_batch_size: Maximum messages per batch before auto-flush
            send_callback: Async callback to send batched messages
        """
        self.batch_interval = batch_interval
        self.max_batch_size = max_batch_size
        self.send_callback = send_callback
        self.pending_messages: Dict[str, List[dict]] = {}
        self.flush_task = None
        self.running = False

    async def start(self):
        """Start the background flushing task"""
        if self.running:
            return
        self.running = True
        self.flush_task = asyncio.create_task(self._flush_loop())
        logger.info(f"MessageBatcher started (interval={self.batch_interval}s, max_size={self.max_batch_size})")

    async def stop(self):
        """Stop the background flushing task and flush remaining messages"""
        self.running = False
        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_all()
        logger.info("MessageBatcher stopped")

    def add_message(self, message: dict) -> bool:
        """
        Add a message to the batch queue.

        Args:
            message: Message dictionary to batch

        Returns:
            True if message should be sent immediately (priority), False if batched
        """
        message_type = message.get('type', 'unknown')

        # Priority messages sent immediately (errors, connection events)
        priority_types = {'error', 'connection', 'connection_established', 'connection_lost'}
        if message_type in priority_types:
            return True

        # Add timestamp if not present
        if 'timestamp' not in message:
            message['timestamp'] = datetime.utcnow().isoformat()

        # Group by type
        if message_type not in self.pending_messages:
            self.pending_messages[message_type] = []

        self.pending_messages[message_type].append(message)

        # Flush if batch is full
        if len(self.pending_messages[message_type]) >= self.max_batch_size:
            asyncio.create_task(self._flush_type(message_type))

        return False

    async def _flush_loop(self):
        """Background task that flushes messages periodically"""
        while self.running:
            try:
                await asyncio.sleep(self.batch_interval)
                await self._flush_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in flush loop: {e}", exc_info=True)

    async def _flush_all(self):
        """Flush all pending message types"""
        for message_type in list(self.pending_messages.keys()):
            await self._flush_type(message_type)

    async def _flush_type(self, message_type: str):
        """Flush all messages of a specific type"""
        if message_type not in self.pending_messages:
            return

        messages = self.pending_messages.pop(message_type, [])
        if not messages:
            return

        # Create batch message
        batch_message = {
            'type': 'batch',
            'batch_type': message_type,
            'count': len(messages),
            'messages': messages,
            'timestamp': datetime.utcnow().isoformat()
        }

        # Send via callback if provided
        if self.send_callback:
            try:
                await self.send_callback(batch_message)
                logger.debug(f"Flushed batch of {len(messages)} {message_type} messages")
            except Exception as e:
                logger.error(f"Error sending batch: {e}", exc_info=True)

        return batch_message
