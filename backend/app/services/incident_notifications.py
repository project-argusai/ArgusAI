"""One notification per multi-camera incident.

Setting ``notify_per_incident`` (stored as ``settings_notify_per_incident``
through the system settings API) is off by default; missing, unreadable or
a failed read counts as off, which is exactly today's per-camera behavior.

When on:
- Notify first, no hold. Alert rules are still evaluated per event; only
  delivery is deduped, once per channel (generic push, or one alert rule)
  per incident, via an insert into ``incident_deliveries`` whose unique
  (group_key, channel) constraint is the atomic claim.
- An event that alerted before its group existed holds the claim
  retroactively (its row is keyed by its own event id).
- Doorbell rings bypass dedup. If the dedup check errors, the alert is sent.
- A blocked entity on any member suppresses the incident push.
- After the combined pass, one update push per incident, only when another
  camera joined after the first push. Claimed with
  ``UPDATE incidents SET update_pushed_at=now WHERE id=? AND update_pushed_at IS NULL``.

Logs carry ids and outcomes only, never descriptions or names.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.incident import Incident, IncidentDelivery
from app.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

SETTING_KEY = "settings_notify_per_incident"
PUSH_CHANNEL = "push"


def notify_per_incident_enabled(db) -> bool:
    try:
        row = db.get(SystemSetting, SETTING_KEY)
    except Exception:
        return False
    if row is None or row.value is None:
        return False
    return str(row.value).strip().strip('"').lower() in ("true", "1", "yes")


def _ids(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _members(db: Session, group_id: str) -> List[Event]:
    return (
        db.query(Event)
        .filter(Event.correlation_group_id == group_id)
        .order_by(Event.timestamp, Event.id)
        .all()
    )


def group_has_blocked_entity(db: Session, group_id: str) -> bool:
    from app.models.recognized_entity import RecognizedEntity

    ids = set()
    for member in _members(db, group_id):
        ids.update(_ids(member.matched_entity_ids))
    if not ids:
        return False
    return (
        db.query(RecognizedEntity.id)
        .filter(RecognizedEntity.id.in_(list(ids)), RecognizedEntity.is_blocked == True)  # noqa: E712
        .first()
        is not None
    )


def _first_delivery(db: Session, group_id: str, channel: str) -> Optional[IncidentDelivery]:
    keys = [group_id] + [m.id for m in _members(db, group_id)]
    return (
        db.query(IncidentDelivery)
        .filter(IncidentDelivery.group_key.in_(keys), IncidentDelivery.channel == channel)
        .order_by(IncidentDelivery.created_at, IncidentDelivery.id)
        .first()
    )


def _insert_claim(session: Session, group_key: str, channel: str, event_id: str) -> bool:
    """Insert-if-not-exists on (group_key, channel). True when this insert won."""
    session.add(IncidentDelivery(group_key=group_key, channel=channel, event_id=event_id))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return False
    return True


def _current_group(session: Session, event_id: str, fallback: Optional[str]) -> Optional[str]:
    """Group id as committed now (the caller's object may be stale)."""
    row = session.query(Event.correlation_group_id).filter(Event.id == event_id).first()
    if row is None:
        return fallback
    return row[0]


def _claim_group(session: Session, group_id: str, channel: str, event_id: str) -> bool:
    """Claim ``channel`` on the group id. An earlier member's own-id claim
    (made before the group existed) is copied to the group id first, with
    insert-if-not-exists, so it keeps the claim."""
    member_ids = [
        row[0] for row in session.query(Event.id).filter(Event.correlation_group_id == group_id)
    ]
    if member_ids:
        earlier = (
            session.query(IncidentDelivery)
            .filter(IncidentDelivery.group_key.in_(member_ids), IncidentDelivery.channel == channel)
            .order_by(IncidentDelivery.created_at, IncidentDelivery.id)
            .first()
        )
        if earlier is not None:
            _insert_claim(session, group_id, channel, earlier.event_id)
    if _insert_claim(session, group_id, channel, event_id):
        return True
    holder = (
        session.query(IncidentDelivery.event_id)
        .filter(IncidentDelivery.group_key == group_id, IncidentDelivery.channel == channel)
        .first()
    )
    return holder is not None and holder[0] == event_id


def _claim(db: Session, event: Event, channel: str) -> bool:
    """True when this event wins ``channel`` for its incident.

    Runs in its own short session so it never commits or rolls back the
    caller's shared session (AlertEngine keeps one ``self.db``). Never waits:
    correlation already ran inline before delivery.

    - Grouped (as committed now, not the caller's possibly stale object):
      claim on the group id only.
    - No group (alone, or correlation failed/timed out): claim on the event
      id, then re-read the committed group before returning, i.e. before any
      send. If a group formed meanwhile and this event does not hold the
      group's claim, it loses and does not send, so a grouped member and this
      event can never both send.
    """
    event_id = event.id
    session = Session(bind=db.get_bind())
    try:
        group_id = _current_group(session, event_id, event.correlation_group_id)
        if group_id:
            return _claim_group(session, group_id, channel, event_id)
        if not _insert_claim(session, event_id, channel, event_id):
            return False
        session.expire_all()
        group_id = _current_group(session, event_id, None)
        if group_id:
            return _claim_group(session, group_id, channel, event_id)
        return True
    finally:
        session.close()


def should_deliver(db: Session, event: Event, channel: str) -> bool:
    """Gate one delivery. Never raises; errors fail open (send)."""
    try:
        if not notify_per_incident_enabled(db):
            return True
        if bool(getattr(event, "is_doorbell_ring", False)):
            return True
        won = _claim(db, event, channel)
    except Exception as exc:
        logger.warning(
            "Incident dedup check failed; sending",
            extra={"event_type": "incident_dedup_error", "event_id": getattr(event, "id", None),
                   "channel": channel, "error_type": type(exc).__name__},
        )
        return True
    if not won:
        logger.info(
            "Incident delivery deduped",
            extra={"event_type": "incident_delivery_deduped", "event_id": event.id,
                   "incident_id": event.correlation_group_id, "channel": channel},
        )
    return won


def push_allowed(db: Session, event_id: str) -> bool:
    """Generic push gate for one stored event (blocked members, then dedup)."""
    try:
        if not notify_per_incident_enabled(db):
            return True
        event = db.get(Event, event_id)
        if event is None:
            return True
        if event.correlation_group_id and group_has_blocked_entity(db, event.correlation_group_id):
            logger.info(
                "Incident push suppressed: blocked entity",
                extra={"event_type": "incident_push_suppressed_blocked", "event_id": event_id,
                       "incident_id": event.correlation_group_id},
            )
            return False
    except Exception as exc:
        logger.warning("Incident push gate failed; sending",
                       extra={"event_id": event_id, "error_type": type(exc).__name__})
        return True
    return should_deliver(db, event, PUSH_CHANNEL)


def _claim_update_push(db: Session, incident_id: str) -> bool:
    result = db.execute(
        update(Incident)
        .where(Incident.id == incident_id, Incident.update_pushed_at.is_(None))
        .values(update_pushed_at=datetime.now(timezone.utc))
    )
    db.commit()
    return result.rowcount == 1


async def maybe_send_update_push(db: Session, incident: Optional[Incident]) -> bool:
    """Send the single post-combined-pass update push. True when sent."""
    if incident is None or incident.status not in ("done", "fallback", "failed"):
        return False
    try:
        if not notify_per_incident_enabled(db):
            return False
        first = _first_delivery(db, incident.id, PUSH_CHANNEL)
        if first is None:
            return False  # nothing was pushed for this incident
        members = _members(db, incident.id)
        pushed = next((m for m in members if m.id == first.event_id), None)
        if pushed is None:
            return False
        late = [m for m in members if m.camera_id != pushed.camera_id]
        if not late:
            return False
        if group_has_blocked_entity(db, incident.id):
            return False
        if not _claim_update_push(db, incident.id):
            return False
    except Exception as exc:
        db.rollback()
        logger.warning("Incident update push check failed",
                       extra={"incident_id": incident.id, "error_type": type(exc).__name__})
        return False

    text = incident.combined_description if incident.status == "done" and incident.combined_description else None
    if not text:
        text = late[-1].description or pushed.description or ""
    from app.services.push_notification_service import send_event_notification

    try:
        results = await send_event_notification(
            event_id=pushed.id,
            camera_name="Multiple cameras",
            description=text,
            camera_id=None,
            smart_detection_type=pushed.smart_detection_type,
            db=db,
        )
    except Exception as exc:
        # Send-once: keep the claim; never re-send.
        logger.warning("Incident update push failed",
                       extra={"incident_id": incident.id, "error_type": type(exc).__name__})
        return False
    if results and not any(getattr(r, "success", False) for r in results):
        # Send-once: update_pushed_at stays claimed; no retry.
        logger.warning("Incident update push not delivered",
                       extra={"incident_id": incident.id})
        return False
    logger.info("Incident update push sent",
                extra={"event_type": "incident_update_push", "incident_id": incident.id,
                       "late_members": len(late)})
    return True
