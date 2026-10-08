"""Push and MQTT fan-out for stored UniFi Protect events.

The Phase B decomposition (May 2026) moved Protect storage into
``ProtectEventStorageService`` and dropped two steps the old handler ran after
every stored event: the Web Push notification and the MQTT publish for Home
Assistant. This module restores both through the existing services:

- Push goes through ``send_event_notification``, which applies each
  subscription's notification preferences (cameras, object types, quiet hours,
  sound). On top of that, a per-camera cooldown keeps a burst of detections on
  one camera to a single push; doorbell rings always notify. Events whose
  verified entities include a blocked entity are not pushed, matching the
  entity alert rules.
- MQTT publishes the event, last-event timestamp, activity state and counts,
  only while the broker connection is up (it is only up when MQTT is enabled).

Both run in background tasks after the event is stored and broadcast, each
under its own timeout, and nothing here raises: a failed or slow push or
publish never affects the stored event or the handler's result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, ContextManager, Dict, List, Optional, Set

from app.core.decorators import singleton

logger = logging.getLogger(__name__)

# One push per camera per window. Prod Protect history (6 days, 5 cameras)
# gives about 33 pushes/day with no window and about 25/day at 120 s.
PUSH_CAMERA_COOLDOWN_S = 120.0
# send_event_notification retries each subscription 3x (2 s, 4 s, 8 s).
PUSH_TIMEOUT_S = 60.0
MQTT_TIMEOUT_S = 15.0


@dataclass
class EventSnapshot:
    """Plain copy of what push/MQTT need, read once in a short session."""

    event_id: str
    camera_id: str
    camera_name: str
    description: str
    timestamp: datetime
    thumbnail_url: Optional[str] = None
    smart_detection_type: Optional[str] = None
    anomaly_score: Optional[float] = None
    is_doorbell_ring: bool = False
    recognition_status: Optional[str] = None
    delivery_carrier: Optional[str] = None
    entity_names: List[str] = field(default_factory=list)
    is_vip: bool = False
    has_blocked_entity: bool = False


def _thumbnail_url(path: Optional[str]) -> Optional[str]:
    """Protect rows already store the API path; older rows store a relative one."""
    if not path:
        return None
    if path.startswith("/") or path.startswith("http"):
        return path
    return f"/api/v1/thumbnails/{path}"


def _entity_ids(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        ids = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [i for i in ids if isinstance(i, str)] if isinstance(ids, list) else []


def load_event_snapshot(db, event_id: str) -> Optional[EventSnapshot]:
    from app.models.camera import Camera
    from app.models.event import Event
    from app.models.recognized_entity import RecognizedEntity

    event = db.query(Event).filter(Event.id == event_id).first()
    if event is None:
        return None
    camera = db.query(Camera).filter(Camera.id == event.camera_id).first()
    snap = EventSnapshot(
        event_id=event.id,
        camera_id=event.camera_id,
        camera_name=camera.name if camera else "Camera",
        description=event.description or "",
        timestamp=event.timestamp,
        thumbnail_url=_thumbnail_url(event.thumbnail_path),
        smart_detection_type=event.smart_detection_type,
        anomaly_score=event.anomaly_score,
        is_doorbell_ring=bool(event.is_doorbell_ring),
        recognition_status=event.recognition_status,
        delivery_carrier=event.delivery_carrier,
    )
    ids = _entity_ids(event.matched_entity_ids)
    if ids:
        entities = db.query(RecognizedEntity).filter(RecognizedEntity.id.in_(ids)).all()
        by_id = {e.id: e for e in entities}
        ordered = [by_id[i] for i in ids if i in by_id]
        snap.entity_names = [e.name for e in ordered if e.name]
        snap.is_vip = any(bool(e.is_vip) for e in ordered)
        snap.has_blocked_entity = any(bool(e.is_blocked) for e in ordered)
    return snap


class ProtectEventNotifier:
    """Schedules push + MQTT for stored Protect events. Never raises."""

    def __init__(
        self,
        push_cooldown_s: float = PUSH_CAMERA_COOLDOWN_S,
        push_timeout_s: float = PUSH_TIMEOUT_S,
        mqtt_timeout_s: float = MQTT_TIMEOUT_S,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.push_cooldown_s = push_cooldown_s
        self.push_timeout_s = push_timeout_s
        self.mqtt_timeout_s = mqtt_timeout_s
        self._clock = clock
        self._last_push_at: Dict[str, float] = {}
        self._tasks: Set[asyncio.Task] = set()

    # -- scheduling -------------------------------------------------------

    def schedule(
        self, event_id: Any, session_factory: Callable[[], ContextManager]
    ) -> Optional[asyncio.Task]:
        """Start push + MQTT for ``event_id`` in the background."""
        if not isinstance(event_id, str) or not event_id:
            return None
        try:
            task = asyncio.get_running_loop().create_task(
                self.notify(event_id, session_factory)
            )
        except Exception as exc:  # no running loop, or loop closing
            logger.warning(
                "Protect notification scheduling failed",
                extra={
                    "event_type": "protect_notify_schedule_failed",
                    "event_id": event_id,
                    "error_type": type(exc).__name__,
                },
            )
            return None
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def drain(self) -> None:
        """Wait for scheduled work (tests and shutdown)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # -- work -------------------------------------------------------------

    async def notify(
        self, event_id: str, session_factory: Callable[[], ContextManager]
    ) -> None:
        try:
            with session_factory() as db:
                snap = load_event_snapshot(db, event_id)
        except Exception as exc:
            logger.warning(
                "Protect notification skipped: event load failed",
                extra={
                    "event_type": "protect_notify_load_failed",
                    "event_id": event_id,
                    "error_type": type(exc).__name__,
                },
            )
            return
        if snap is None:
            return
        await asyncio.gather(
            self._bounded(self.publish_mqtt(snap, session_factory), self.mqtt_timeout_s, "mqtt", event_id),
            self._bounded(self.send_push(snap, session_factory), self.push_timeout_s, "push", event_id),
        )

    async def _bounded(self, coro, timeout_s: float, step: str, event_id: str) -> None:
        try:
            await asyncio.wait_for(coro, timeout=timeout_s)
        except asyncio.TimeoutError:
            logger.warning(
                f"Protect {step} timed out",
                extra={"event_type": f"protect_{step}_timeout", "event_id": event_id, "timeout_s": timeout_s},
            )
        except Exception as exc:
            logger.warning(
                f"Protect {step} failed",
                extra={"event_type": f"protect_{step}_failed", "event_id": event_id, "error_type": type(exc).__name__},
            )

    def _claim_push_slot(self, snap: EventSnapshot) -> Optional[tuple]:
        """Claim the camera's push window: ``(claimed_at, previous)`` or None while cooling down."""
        now = self._clock()
        previous = self._last_push_at.get(snap.camera_id)
        if (
            not snap.is_doorbell_ring
            and previous is not None
            and now - previous < self.push_cooldown_s
        ):
            return None
        self._last_push_at[snap.camera_id] = now
        return (now, previous)

    def _release_push_slot(self, camera_id: str, claim: tuple) -> None:
        """Undo a claim nothing was sent for, unless a later event re-claimed the camera."""
        claimed_at, previous = claim
        if self._last_push_at.get(camera_id) != claimed_at:
            return
        if previous is None:
            self._last_push_at.pop(camera_id, None)
        else:
            self._last_push_at[camera_id] = previous

    async def send_push(
        self, snap: EventSnapshot, session_factory: Callable[[], ContextManager]
    ) -> int:
        """Send the event push; returns subscriptions attempted (0 when skipped)."""
        if snap.has_blocked_entity:
            logger.info(
                "Protect push suppressed: blocked entity",
                extra={"event_type": "protect_push_suppressed_blocked", "event_id": snap.event_id},
            )
            return 0
        claim = self._claim_push_slot(snap)
        if claim is None:
            logger.info(
                "Protect push skipped: camera cooldown",
                extra={
                    "event_type": "protect_push_cooldown",
                    "event_id": snap.event_id,
                    "camera_id": snap.camera_id,
                    "cooldown_s": self.push_cooldown_s,
                },
            )
            return 0

        from app.services.carrier_extractor import CARRIER_DISPLAY_NAMES
        from app.services.push_notification_service import send_event_notification

        detection = "ring" if snap.is_doorbell_ring else snap.smart_detection_type
        results: List[Any] = []
        try:
            with session_factory() as db:
                results = await send_event_notification(
                    event_id=snap.event_id,
                    camera_name=snap.camera_name,
                    description=snap.description,
                    thumbnail_url=snap.thumbnail_url,
                    camera_id=snap.camera_id,
                    smart_detection_type=detection,
                    anomaly_score=snap.anomaly_score,
                    entity_names=snap.entity_names or None,
                    is_vip=snap.is_vip,
                    recognition_status=snap.recognition_status,
                    delivery_carrier=snap.delivery_carrier,
                    delivery_carrier_display=CARRIER_DISPLAY_NAMES.get(snap.delivery_carrier or ""),
                    db=db,
                ) or []
        finally:
            # Nothing was attempted (no subscriptions, all filtered by
            # preferences, or the send raised): don't hold the camera window.
            if not results:
                self._release_push_slot(snap.camera_id, claim)
        logger.info(
            "Protect push dispatched",
            extra={
                "event_type": "protect_push_sent",
                "event_id": snap.event_id,
                "attempted": len(results),
                "successful": sum(1 for r in results if getattr(r, "success", False)),
            },
        )
        return len(results)

    async def publish_mqtt(
        self, snap: EventSnapshot, session_factory: Callable[[], ContextManager]
    ) -> bool:
        """Publish event + status sensors. Returns False when MQTT is not connected."""
        from app.models.event import Event
        from app.services.mqtt_service import get_mqtt_service, serialize_event_for_mqtt
        from app.services.mqtt_status_service import get_camera_event_counts, set_activity_on

        mqtt = get_mqtt_service()
        if not mqtt.is_connected:
            return False

        with session_factory() as db:
            event = db.query(Event).filter(Event.id == snap.event_id).first()
            if event is None:
                return False
            payload = serialize_event_for_mqtt(
                event, snap.camera_name, api_base_url=mqtt.get_api_base_url()
            )
        topic = mqtt.get_event_topic(str(snap.camera_id))
        published = await mqtt.publish(topic, payload)
        logger.info(
            "Protect event published to MQTT" if published else "MQTT publish returned False",
            extra={
                "event_type": "mqtt_protect_event_published" if published else "mqtt_protect_event_publish_failed",
                "event_id": snap.event_id,
            },
        )

        # Status sensors: each independent, as before the refactor.
        steps = (
            ("last_event", lambda: mqtt.publish_last_event_timestamp(
                camera_id=str(snap.camera_id), camera_name=snap.camera_name,
                event_id=snap.event_id, timestamp=snap.timestamp,
                description=snap.description, smart_detection_type=snap.smart_detection_type,
            )),
            ("activity", lambda: mqtt.publish_activity_state(
                camera_id=str(snap.camera_id), state="ON", last_event_at=snap.timestamp,
            )),
            ("activity_timer", lambda: set_activity_on(str(snap.camera_id), snap.timestamp)),
        )
        for name, step in steps:
            try:
                await step()
            except Exception as exc:
                logger.warning(
                    f"MQTT {name} publish failed",
                    extra={"event_type": "mqtt_protect_status_failed", "step": name,
                           "event_id": snap.event_id, "error_type": type(exc).__name__},
                )
        try:
            counts = await get_camera_event_counts(str(snap.camera_id))
            await mqtt.publish_event_counts(
                camera_id=str(snap.camera_id), camera_name=snap.camera_name,
                events_today=counts["events_today"], events_this_week=counts["events_this_week"],
            )
        except Exception as exc:
            logger.warning(
                "MQTT counts publish failed",
                extra={"event_type": "mqtt_protect_status_failed", "step": "counts",
                       "event_id": snap.event_id, "error_type": type(exc).__name__},
            )
        return bool(published)


@singleton
class _NotifierHolder:
    """Process-wide notifier (cooldown state); reset with the other singletons."""

    def __init__(self):
        self.notifier = ProtectEventNotifier()


def get_protect_event_notifier() -> ProtectEventNotifier:
    return _NotifierHolder().notifier


def reset_protect_event_notifier() -> None:
    _NotifierHolder._reset_instance()
