"""
Scout UI — Event Emitter

Manages per-run WebSocket subscribers, broadcasting Agent events to all connected clients.
Thread-safe, supports multiple simultaneous runs.
"""

import asyncio
import json
import time
from typing import Any

from fastapi import WebSocket
from loguru import logger

from schemas import EventType


class EventEmitter:
    """Event bus for broadcasting agent events to WebSocket subscribers.

    Each run_id can have multiple WebSocket subscribers. Events are broadcast
    to all subscribers of a given run_id.
    """

    def __init__(self):
        self._subscribers: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, run_id: str, ws: WebSocket) -> None:
        """Add a WebSocket subscriber for a run.

        Args:
            run_id: The run identifier
            ws: WebSocket connection to add
        """
        async with self._lock:
            if run_id not in self._subscribers:
                self._subscribers[run_id] = []
            self._subscribers[run_id].append(ws)
            logger.info(
                f"WebSocket subscribed to run {run_id}, total: {len(self._subscribers[run_id])}"
            )

    async def unsubscribe(self, run_id: str, ws: WebSocket) -> None:
        """Remove a WebSocket subscriber for a run.

        Args:
            run_id: The run identifier
            ws: WebSocket connection to remove
        """
        async with self._lock:
            if run_id in self._subscribers:
                try:
                    self._subscribers[run_id].remove(ws)
                except ValueError:
                    pass
                if not self._subscribers[run_id]:
                    del self._subscribers[run_id]
                logger.info(f"WebSocket unsubscribed from run {run_id}")

    async def emit(
        self, run_id: str, event_type: EventType, data: dict[str, Any]
    ) -> None:
        """Emit a typed event to all subscribers of a run.

        Args:
            run_id: The run identifier
            event_type: Type of the event
            data: Event payload data
        """
        event = {
            "type": event_type.value,
            "timestamp": time.time(),
            "data": data,
        }
        await self._broadcast(run_id, event)

    async def _broadcast(self, run_id: str, event: dict) -> None:
        """Send event JSON to all subscribers. Remove dead connections.

        Args:
            run_id: The run identifier
            event: Event dict to serialize and send
        """
        async with self._lock:
            subscribers = self._subscribers.get(run_id, []).copy()

        if not subscribers:
            return

        message = json.dumps(event, ensure_ascii=False, default=str)
        dead = []

        for ws in subscribers:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        if dead:
            async with self._lock:
                for ws in dead:
                    if run_id in self._subscribers:
                        try:
                            self._subscribers[run_id].remove(ws)
                        except ValueError:
                            pass

    async def cleanup_run(self, run_id: str) -> None:
        """Remove all subscribers for a completed run.

        Args:
            run_id: The run identifier to clean up
        """
        async with self._lock:
            if run_id in self._subscribers:
                del self._subscribers[run_id]
                logger.info(f"Cleaned up subscribers for run {run_id}")

    def has_subscribers(self, run_id: str) -> bool:
        """Check if a run has any active subscribers.

        Args:
            run_id: The run identifier

        Returns:
            True if there are subscribers
        """
        return bool(self._subscribers.get(run_id))
