"""
WebSocket Connection Manager (Epic 5)

Simple WebSocket manager for broadcasting real-time events to connected clients.
Supports dashboard notifications and alert broadcasts.

Usage:
    # In FastAPI app
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            websocket_manager.disconnect(websocket)

    # Broadcasting
    await websocket_manager.broadcast({
        "type": "ALERT_TRIGGERED",
        "data": {"event": event_dict, "rule": rule_dict}
    })
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections and message broadcasting.

    Thread-safe connection management with async broadcast support.
    Handles connection errors gracefully without crashing.

    Attributes:
        active_connections: Set of connected WebSocket instances
    """

    def __init__(self):
        """Initialize WebSocket manager with empty connection set."""
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept and register a new WebSocket connection.

        Args:
            websocket: FastAPI WebSocket instance
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

        logger.info(
            f"WebSocket connected. Active connections: {len(self.active_connections)}",
            extra={"connection_count": len(self.active_connections)}
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection.

        Args:
            websocket: WebSocket to disconnect
        """
        async with self._lock:
            self.active_connections.discard(websocket)

        logger.info(
            f"WebSocket disconnected. Active connections: {len(self.active_connections)}",
            extra={"connection_count": len(self.active_connections)}
        )

    async def broadcast(self, message: Dict[str, Any]) -> int:
        """
        Broadcast a message to all connected WebSocket clients.

        Adds timestamp to message and handles individual connection errors
        without affecting other connections.

        Args:
            message: Dictionary to serialize and send as JSON

        Returns:
            Number of clients that successfully received the message
        """
        if not self.active_connections:
            logger.debug("No WebSocket connections to broadcast to")
            return 0

        # Add timestamp to message
        message_with_timestamp = {
            **message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        json_message = json.dumps(message_with_timestamp)
        success_count = 0
        failed_connections = []

        async with self._lock:
            connections = list(self.active_connections)

        for websocket in connections:
            try:
                await websocket.send_text(json_message)
                success_count += 1
            except Exception as e:
                logger.warning(
                    f"Failed to send WebSocket message: {e}",
                    extra={"error": str(e)}
                )
                failed_connections.append(websocket)

        # Clean up failed connections
        if failed_connections:
            async with self._lock:
                for ws in failed_connections:
                    self.active_connections.discard(ws)

            logger.info(
                f"Cleaned up {len(failed_connections)} failed WebSocket connections",
                extra={"cleaned_count": len(failed_connections)}
            )

        logger.debug(
            f"Broadcast complete: {success_count}/{len(connections)} clients",
            extra={
                "success_count": success_count,
                "total_connections": len(connections),
                "message_type": message.get("type")
            }
        )

        return success_count

    async def broadcast_alert(
        self,
        event_data: Dict[str, Any],
        rule_data: Dict[str, Any]
    ) -> int:
        """
        Broadcast an alert triggered message.

        Convenience method for alert notifications.

        Args:
            event_data: Event dictionary
            rule_data: Alert rule dictionary

        Returns:
            Number of clients notified
        """
        return await self.broadcast({
            "type": "ALERT_TRIGGERED",
            "data": {
                "event": event_data,
                "rule": rule_data
            }
        })

    def get_connection_count(self) -> int:
        """Get current number of active connections."""
        return len(self.active_connections)


# Global singleton instance
websocket_manager = WebSocketManager()


def get_websocket_manager() -> WebSocketManager:
    """Get the global WebSocket manager instance."""
    return websocket_manager
