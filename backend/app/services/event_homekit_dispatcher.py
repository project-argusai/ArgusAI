"""
EventHomeKitDispatcher

Owns the HomeKit sensor-trigger routing for a processed event: always trigger the
motion sensor, plus the detection-type-specific sensor (occupancy for person,
vehicle / animal / package). Each trigger is a fire-and-forget async task whose
errors are logged but never propagated, so HomeKit problems can never block or
fail event processing.

Extracted from EventProcessor during the Phase B decomposition (#443) to shrink
the god-class and make the HomeKit routing independently testable.
"""

import asyncio
import logging
from typing import Any, Optional

from app.core.decorators import singleton

logger = logging.getLogger(__name__)


def _get_container():
    """Lazy getter for the service container (avoids circular imports)."""
    from app.services.service_container import container
    return container


@singleton
class EventHomeKitDispatcher:
    """Routes a processed event to the appropriate HomeKit sensor triggers."""

    async def dispatch(
        self, event: Any, event_id: str, smart_detection_type: Optional[str]
    ) -> None:
        """Trigger the appropriate HomeKit sensors based on detection type.

        Non-blocking: each sensor trigger is scheduled as a background task. Any
        failure (including HomeKit being unavailable) is contained here.
        """
        try:
            homekit_service = _get_container().homekit_service

            if not homekit_service.is_running:
                return

            # Always trigger motion
            asyncio.create_task(
                self._trigger_motion(homekit_service, event.camera_id, event_id)
            )
            logger.debug(
                f"HomeKit motion trigger task created for event {event_id}",
                extra={"event_id": event_id, "camera_id": event.camera_id}
            )

            # Person → occupancy
            if smart_detection_type == "person":
                asyncio.create_task(
                    self._trigger_occupancy(homekit_service, event.camera_id, event_id)
                )
                logger.debug(
                    f"HomeKit occupancy trigger task created for person event {event_id}",
                    extra={"event_id": event_id, "camera_id": event.camera_id, "smart_detection_type": smart_detection_type}
                )

            # Vehicle
            if smart_detection_type == "vehicle":
                asyncio.create_task(
                    self._trigger_vehicle(homekit_service, event.camera_id, event_id)
                )
                logger.debug(
                    f"HomeKit vehicle trigger task created for event {event_id}",
                    extra={"event_id": event_id, "camera_id": event.camera_id, "smart_detection_type": smart_detection_type}
                )

            # Animal
            if smart_detection_type == "animal":
                asyncio.create_task(
                    self._trigger_animal(homekit_service, event.camera_id, event_id)
                )
                logger.debug(
                    f"HomeKit animal trigger task created for event {event_id}",
                    extra={"event_id": event_id, "camera_id": event.camera_id, "smart_detection_type": smart_detection_type}
                )

            # Package (with carrier info)
            if smart_detection_type == "package":
                delivery_carrier = getattr(event, 'delivery_carrier', None)
                asyncio.create_task(
                    self._trigger_package(homekit_service, event.camera_id, event_id, delivery_carrier)
                )
                logger.debug(
                    f"HomeKit package trigger task created for event {event_id}",
                    extra={
                        "event_id": event_id,
                        "camera_id": event.camera_id,
                        "smart_detection_type": smart_detection_type,
                        "delivery_carrier": delivery_carrier
                    }
                )
        except Exception as homekit_error:
            logger.warning(
                f"Failed to trigger HomeKit sensors: {homekit_error}",
                extra={"error": str(homekit_error), "event_id": event_id}
            )

    async def _trigger_motion(self, homekit_service, camera_id: str, event_id: str) -> None:
        """Trigger HomeKit motion sensor (Story P4-6.2). Fire-and-forget; errors contained."""
        try:
            success = homekit_service.trigger_motion(camera_id, event_id=event_id)
            if success:
                logger.info(
                    "HomeKit motion triggered for event",
                    extra={"event_type": "homekit_motion_triggered", "event_id": event_id, "camera_id": camera_id}
                )
            else:
                logger.debug(
                    "HomeKit motion trigger returned False (no sensor for camera)",
                    extra={"event_type": "homekit_motion_no_sensor", "event_id": event_id, "camera_id": camera_id}
                )
        except Exception as e:
            logger.warning(
                f"HomeKit motion trigger failed for event {event_id}: {e}",
                extra={"event_type": "homekit_motion_error", "event_id": event_id, "camera_id": camera_id, "error": str(e)}
            )

    async def _trigger_occupancy(self, homekit_service, camera_id: str, event_id: str) -> None:
        """Trigger HomeKit occupancy sensor for person detection (Story P5-1.5)."""
        try:
            success = homekit_service.trigger_occupancy(camera_id, event_id=event_id)
            if success:
                logger.info(
                    "HomeKit occupancy triggered for person detection",
                    extra={"event_type": "homekit_occupancy_triggered", "event_id": event_id, "camera_id": camera_id}
                )
            else:
                logger.debug(
                    "HomeKit occupancy trigger returned False (no sensor for camera)",
                    extra={"event_type": "homekit_occupancy_no_sensor", "event_id": event_id, "camera_id": camera_id}
                )
        except Exception as e:
            logger.warning(
                f"HomeKit occupancy trigger failed for event {event_id}: {e}",
                extra={"event_type": "homekit_occupancy_error", "event_id": event_id, "camera_id": camera_id, "error": str(e)}
            )

    async def _trigger_vehicle(self, homekit_service, camera_id: str, event_id: str) -> None:
        """Trigger HomeKit vehicle sensor for vehicle detection (Story P5-1.6 AC1)."""
        try:
            success = homekit_service.trigger_vehicle(camera_id, event_id=event_id)
            if success:
                logger.info(
                    "HomeKit vehicle triggered for vehicle detection",
                    extra={"event_type": "homekit_vehicle_triggered", "event_id": event_id, "camera_id": camera_id}
                )
            else:
                logger.debug(
                    "HomeKit vehicle trigger returned False (no sensor for camera)",
                    extra={"event_type": "homekit_vehicle_no_sensor", "event_id": event_id, "camera_id": camera_id}
                )
        except Exception as e:
            logger.warning(
                f"HomeKit vehicle trigger failed for event {event_id}: {e}",
                extra={"event_type": "homekit_vehicle_error", "event_id": event_id, "camera_id": camera_id, "error": str(e)}
            )

    async def _trigger_animal(self, homekit_service, camera_id: str, event_id: str) -> None:
        """Trigger HomeKit animal sensor for animal detection (Story P5-1.6 AC2)."""
        try:
            success = homekit_service.trigger_animal(camera_id, event_id=event_id)
            if success:
                logger.info(
                    "HomeKit animal triggered for animal detection",
                    extra={"event_type": "homekit_animal_triggered", "event_id": event_id, "camera_id": camera_id}
                )
            else:
                logger.debug(
                    "HomeKit animal trigger returned False (no sensor for camera)",
                    extra={"event_type": "homekit_animal_no_sensor", "event_id": event_id, "camera_id": camera_id}
                )
        except Exception as e:
            logger.warning(
                f"HomeKit animal trigger failed for event {event_id}: {e}",
                extra={"event_type": "homekit_animal_error", "event_id": event_id, "camera_id": camera_id, "error": str(e)}
            )

    async def _trigger_package(
        self, homekit_service, camera_id: str, event_id: str, delivery_carrier: Optional[str] = None
    ) -> None:
        """Trigger HomeKit package sensor for package detection (Story P5-1.6 AC3, P7-2.3)."""
        try:
            success = homekit_service.trigger_package(
                camera_id, event_id=event_id, delivery_carrier=delivery_carrier
            )
            if success:
                logger.info(
                    "HomeKit package triggered for package detection"
                    + (f" (carrier: {delivery_carrier})" if delivery_carrier else ""),
                    extra={"event_type": "homekit_package_triggered", "event_id": event_id, "camera_id": camera_id, "delivery_carrier": delivery_carrier}
                )
            else:
                logger.debug(
                    "HomeKit package trigger returned False (no sensor for camera)",
                    extra={"event_type": "homekit_package_no_sensor", "event_id": event_id, "camera_id": camera_id, "delivery_carrier": delivery_carrier}
                )
        except Exception as e:
            logger.warning(
                f"HomeKit package trigger failed for event {event_id}: {e}",
                extra={"event_type": "homekit_package_error", "event_id": event_id, "camera_id": camera_id, "delivery_carrier": delivery_carrier, "error": str(e)}
            )


# Backward compatible getter (delegates to @singleton decorator)
def get_event_homekit_dispatcher() -> "EventHomeKitDispatcher":
    return EventHomeKitDispatcher()


def reset_event_homekit_dispatcher() -> None:
    EventHomeKitDispatcher._reset_instance()
