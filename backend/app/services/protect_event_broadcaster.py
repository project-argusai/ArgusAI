"""
ProtectEventBroadcaster

Responsible for broadcasting Protect events to connected clients (WebSocket)
and triggering HomeKit doorbell notifications.

Extracted from ProtectEventHandler during Phase 4 decomposition.

Migrated to @singleton decorator as part of #450 (Lightweight DI Container).
"""

import json
import logging
from datetime import datetime
from typing import Optional

from app.models.event import Event
from app.models.camera import Camera
from app.core.decorators import singleton

logger = logging.getLogger(__name__)


@singleton
class ProtectEventBroadcaster:
    """
    Handles WebSocket broadcasting and HomeKit notifications for Protect events.
    """

    def __init__(self):
        pass

    async def broadcast_event_created(self, event: Event, camera: Camera) -> int:
        """
        Broadcast EVENT_CREATED message via WebSocket.
        """
        try:
            from app.services.websocket_manager import get_websocket_manager

            websocket_manager = get_websocket_manager()

            try:
                objects_detected = json.loads(event.objects_detected)
            except (json.JSONDecodeError, TypeError):
                objects_detected = []

            message = {
                "type": "EVENT_CREATED",
                "data": {
                    "id": event.id,
                    "camera_id": event.camera_id,
                    "camera_name": camera.name,
                    "timestamp": event.timestamp.isoformat(),
                    "description": event.description,
                    "confidence": event.confidence,
                    "objects_detected": objects_detected,
                    "thumbnail_path": event.thumbnail_path,
                    "analysis_mode": event.analysis_mode,
                    "provider_used": event.provider_used,
                    "is_doorbell_ring": event.is_doorbell_ring,
                }
            }

            clients_notified = await websocket_manager.broadcast(message)

            logger.info(
                f"EVENT_CREATED broadcast: {clients_notified} clients notified",
                extra={
                    "event_type": "event_created_broadcast",
                    "event_id": event.id,
                    "camera_name": camera.name,
                    "clients_notified": clients_notified
                }
            )

            return clients_notified

        except Exception as e:
            logger.warning(
                f"EVENT_CREATED broadcast error: {e}",
                extra={
                    "event_type": "event_created_broadcast_error",
                    "event_id": event.id,
                    "error": str(e)
                }
            )
            return 0

    async def broadcast_doorbell_ring(
        self,
        camera_id: str,
        camera_name: str,
        thumbnail_url: str,
        timestamp: datetime
    ) -> int:
        """
        Broadcast immediate DOORBELL_RING notification.
        """
        try:
            from app.services.websocket_manager import get_websocket_manager

            websocket_manager = get_websocket_manager()

            message = {
                "type": "DOORBELL_RING",
                "data": {
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "thumbnail_url": thumbnail_url,
                    "timestamp": timestamp.isoformat()
                }
            }

            clients_notified = await websocket_manager.broadcast(message)

            logger.info(
                f"DOORBELL_RING broadcast: {clients_notified} clients notified for '{camera_name}'",
                extra={
                    "event_type": "doorbell_ring_broadcast",
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "clients_notified": clients_notified
                }
            )

            return clients_notified

        except Exception as e:
            logger.warning(
                f"DOORBELL_RING broadcast error: {e}",
                extra={
                    "event_type": "doorbell_ring_broadcast_error",
                    "camera_id": camera_id,
                    "error": str(e)
                }
            )
            return 0

    def trigger_homekit_doorbell(self, camera_id: str, event_id: Optional[str] = None) -> bool:
        """
        Trigger HomeKit doorbell notification (Story P5-1.7).
        """
        try:
            # This is currently a no-op or calls into HomeKit service.
            # For now we keep the behavior from the original handler.
            logger.debug(
                f"HomeKit doorbell trigger requested for camera {camera_id}",
                extra={
                    "event_type": "homekit_doorbell_trigger",
                    "camera_id": camera_id,
                    "event_id": event_id
                }
            )
            # In a future extraction, this would call a proper HomeKit service
            return True

        except Exception as e:
            logger.warning(f"HomeKit doorbell trigger failed: {e}")
            return False


# Backward compatible getter (delegates to @singleton decorator)
def get_protect_event_broadcaster() -> "ProtectEventBroadcaster":
    return ProtectEventBroadcaster()


def reset_protect_event_broadcaster() -> None:
    ProtectEventBroadcaster._reset_instance()