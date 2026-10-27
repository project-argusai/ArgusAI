"""Combined AI description per multi-camera incident.

Notify-first: nothing here delays any alert. After a group settles, one
multi-image call runs over at most one frame per camera (max 4) inside the
multi-image SLA. Timeout or failure marks the incident ``fallback`` and the
UI keeps showing per-camera descriptions.

The entity chip (``matched_entity_ids``) is the ordered union of member
events' ``matched_entity_ids``, set by identity verification. It is never
parsed from combined or per-camera description text.

Gated by the ``incident_combined_description_enabled`` system setting, on
by default; an explicit false value turns it off. Logs carry ids, status and timings only.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.incident import Incident
from app.models.system_setting import SystemSetting

logger = logging.getLogger(__name__)

COMBINED_SETTING_KEY = "incident_combined_description_enabled"
DEFAULT_SETTLE_MS = 3000
MIN_SETTLE_MS = 1000
MAX_SETTLE_MS = 10000
MAX_CAMERAS = 4
MAX_ATTEMPTS = 2
# Outer guard on top of the orchestrator's own SLA handling.
SLA_GRACE_MS = 1000

COMBINED_PROMPT = (
    "These images are from different cameras at the same moment and show one "
    "incident. Write one short description of what happened across all of "
    "them. Do not name or identify any person or vehicle."
)

_OFF_VALUES = {"false", "0", "off", "no"}


def combined_description_enabled(db: Session) -> bool:
    """On by default. Only an explicit false/0/off/no value turns it off.

    Missing or unparseable values use the default (on). It only adds data;
    alerts never wait on it. A failed settings read is treated as off so a
    broken DB never triggers extra AI calls.
    """
    try:
        row = db.get(SystemSetting, COMBINED_SETTING_KEY)
    except Exception:
        return False
    if row is None or row.value is None:
        return True
    return str(row.value).strip().strip('"').lower() not in _OFF_VALUES


def resolve_settle_ms(value: Optional[Any] = None) -> int:
    if value is None:
        value = os.environ.get("INCIDENT_SETTLE_MS")
    try:
        ms = int(value) if value is not None else DEFAULT_SETTLE_MS
    except (TypeError, ValueError):
        ms = DEFAULT_SETTLE_MS
    return max(MIN_SETTLE_MS, min(MAX_SETTLE_MS, ms))


def json_safe(obj: Any) -> Any:
    """Cast numpy scalars/arrays to plain Python so json.dumps works."""
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return json_safe(obj.tolist())
    return obj


def _loads_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def _members(db: Session, group_id: str) -> List[Event]:
    return (
        db.query(Event)
        .filter(Event.correlation_group_id == group_id)
        .order_by(Event.timestamp, Event.id)
        .all()
    )


def union_entity_ids(members: Iterable[Event]) -> List[str]:
    seen: Dict[str, None] = {}
    for member in members:
        for entity_id in _loads_list(member.matched_entity_ids):
            seen.setdefault(entity_id, None)
    return list(seen)


def _frame_bytes(event: Event) -> Optional[bytes]:
    candidates: List[str] = []
    if event.thumbnail_base64:
        candidates.append(event.thumbnail_base64)
    candidates.extend(_loads_list(getattr(event, "key_frames_base64", None)))
    for raw in candidates:
        try:
            data = raw.split(",", 1)[1] if raw.startswith("data:") else raw
            return base64.b64decode(data, validate=True)
        except Exception:
            continue
    return None


def _pick_frames(members: List[Event]) -> List[bytes]:
    frames: List[bytes] = []
    used_cameras = set()
    for member in members:
        if member.camera_id in used_cameras:
            continue
        frame = _frame_bytes(member)
        if frame is None:
            continue
        used_cameras.add(member.camera_id)
        frames.append(frame)
        if len(frames) >= MAX_CAMERAS:
            break
    return frames


def _get_orchestrator():
    from app.services.vision_analysis_orchestrator import get_vision_analysis_orchestrator

    return get_vision_analysis_orchestrator()


async def run_combined_pass(
    db: Session,
    group_id: str,
    orchestrator=None,
) -> Optional[Incident]:
    """Compute (or refresh) the combined result for one correlation group.

    Returns None when the flag is off or the group spans fewer than two
    cameras (no row, no AI call). Idempotent: a finished incident whose
    membership has not changed is returned as is.
    """
    if not group_id or not combined_description_enabled(db):
        return None

    members = _members(db, group_id)
    if len({m.camera_id for m in members}) < 2:
        stub = db.get(Incident, group_id)
        if stub is not None and stub.status == "pending" and not stub.combined_description:
            db.delete(stub)  # placeholder from scheduling; nothing to combine
            db.commit()
        return None

    incident = db.get(Incident, group_id)
    if incident is None:
        incident = Incident(id=group_id, status="pending", attempts=0)
        db.add(incident)
    elif incident.status != "pending" and incident.member_count == len(members):
        return incident
    else:
        # Recompute: drop the stale combined result so a reader never sees
        # an old description next to status=pending.
        incident.status = "pending"
        incident.attempts = 0
        incident.combined_description = None
        incident.combined_identification = None
        incident.provider_used = None

    incident.member_count = len(members)
    incident.primary_event_id = members[0].id
    entity_ids = union_entity_ids(members)
    incident.matched_entity_ids = json.dumps(entity_ids) if entity_ids else None
    db.commit()

    frames = _pick_frames(members)
    if len(frames) < 2:
        return _finish(db, incident, "fallback", reason="frames_unavailable")

    if orchestrator is None:
        orchestrator = _get_orchestrator()
    sla_ms = int(getattr(orchestrator, "default_multi_image_sla_ms", 25_000))

    result = None
    reason = None
    # One overall budget for the whole pass: a retry only gets what is left.
    loop = asyncio.get_running_loop()
    deadline = loop.time() + (sla_ms + SLA_GRACE_MS) / 1000.0
    while incident.attempts < MAX_ATTEMPTS:
        remaining_s = deadline - loop.time()
        if remaining_s <= 0:
            reason = reason or "timeout"
            break
        incident.attempts += 1
        attempt_sla_ms = max(1, min(sla_ms, int(remaining_s * 1000)))
        try:
            result = await asyncio.wait_for(
                orchestrator.analyze_images(
                    images=frames,
                    camera_name="Multiple cameras",
                    timestamp=members[0].timestamp.isoformat() if members[0].timestamp else None,
                    sla_timeout_ms=attempt_sla_ms,
                    custom_prompt=COMBINED_PROMPT,
                ),
                timeout=remaining_s,
            )
        except asyncio.TimeoutError:
            reason = "timeout"
            break  # SLA spent: no retry
        except Exception as exc:  # provider error, breaker open, bad JSON
            reason = type(exc).__name__
            result = None
            continue
        if result is not None and getattr(result, "success", False) and result.description:
            break
        reason = "provider_failed"
        result = None

    if result is None:
        return _finish(db, incident, "fallback", reason=reason)

    incident.combined_description = result.description
    identification = getattr(result, "identification", None)
    incident.combined_identification = (
        json.dumps(json_safe(identification)) if identification else None
    )
    incident.provider_used = getattr(result, "provider", None)
    return _finish(db, incident, "done")


def _finish(db: Session, incident: Incident, status: str, reason: Optional[str] = None) -> Incident:
    incident.status = status
    if status != "done":
        incident.combined_description = None
        incident.combined_identification = None
    db.commit()
    logger.info(
        "Incident combined pass finished",
        extra={
            "event_type": "incident_combined_pass",
            "incident_id": incident.id,
            "status": status,
            "reason": reason,
            "member_count": incident.member_count,
            "attempts": incident.attempts,
        },
    )
    return incident


def serialize_incident(db: Session, incident: Incident, members: Optional[List[Event]] = None) -> Dict[str, Any]:
    if members is None:
        member_ids = [
            row_id
            for (row_id,) in db.query(Event.id)
            .filter(Event.correlation_group_id == incident.id)
            .order_by(Event.timestamp, Event.id)
            .all()
        ]
    else:
        member_ids = [m.id for m in members]
    identification = None
    if incident.combined_identification:
        try:
            identification = json.loads(incident.combined_identification)
        except ValueError:
            identification = None
    return {
        "id": incident.id,
        "correlation_group_id": incident.id,
        "status": incident.status,
        "combined_description": incident.combined_description,
        "combined_identification": identification,
        "matched_entity_ids": _loads_list(incident.matched_entity_ids),
        "member_event_ids": member_ids,
        "member_count": incident.member_count,
        "primary_event_id": incident.primary_event_id,
        "provider_used": incident.provider_used,
        "created_at": incident.created_at,
        "updated_at": incident.updated_at,
    }


def incidents_for_events(db: Session, events: Iterable[Event]) -> Dict[str, Dict[str, Any]]:
    """Map correlation_group_id -> serialized incident for a page of events."""
    group_ids = {e.correlation_group_id for e in events if e.correlation_group_id}
    if not group_ids:
        return {}
    try:
        incidents = db.query(Incident).filter(Incident.id.in_(group_ids)).all()
        if not incidents:
            return {}
        rows = (
            db.query(Event.id, Event.correlation_group_id)
            .filter(Event.correlation_group_id.in_([i.id for i in incidents]))
            .order_by(Event.timestamp, Event.id)
            .all()
        )
    except Exception:
        return {}
    by_group: Dict[str, List[str]] = {}
    for event_id, gid in rows:
        by_group.setdefault(gid, []).append(event_id)
    out = {}
    for incident in incidents:
        payload = serialize_incident(db, incident, members=[])
        payload["member_event_ids"] = by_group.get(incident.id, [])
        out[incident.id] = payload
    return out


# --- scheduling ------------------------------------------------------------

_pending_tasks: Dict[str, asyncio.Task] = {}


def schedule_combined_pass(db: Session, group_id: Optional[str]) -> None:
    """Debounce a combined pass for ``group_id`` until the group settles.

    Re-arming on each new member means the pass runs once, settle_ms after
    the last camera joined. Never raises; never blocks the caller.
    """
    if not group_id:
        return
    try:
        if not combined_description_enabled(db):
            return
        loop = asyncio.get_running_loop()
    except Exception:
        return
    _insert_pending_row(db, group_id)
    # Single worker process assumed: this map is in-memory. Cancelling a
    # superseded task during its settle sleep is free, but cancelling one
    # whose AI call is already in flight wastes that call (the re-armed
    # task makes a fresh one).
    existing = _pending_tasks.get(group_id)
    if existing is not None and not existing.done():
        existing.cancel()
    _pending_tasks[group_id] = loop.create_task(_settle_then_run(group_id, resolve_settle_ms()))


def _insert_pending_row(db: Session, group_id: str) -> None:
    """Insert a pending row if none exists, so a restart mid-settle is swept.

    Uses INSERT .. ON CONFLICT DO NOTHING; an existing row (any status) is
    left untouched. Never raises.
    """
    # Own short session: never commit or roll back the caller's session
    # (correlation_service passes its shared one).
    session = Session(bind=db.get_bind())
    try:
        now = datetime.now(timezone.utc)
        values = dict(id=group_id, status="pending", member_count=0, attempts=0,
                      created_at=now, updated_at=now)
        dialect = session.get_bind().dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert as dialect_insert
        else:
            from sqlalchemy.dialects.sqlite import insert as dialect_insert
        stmt = dialect_insert(Incident).values(**values).on_conflict_do_nothing(index_elements=["id"])
        session.execute(stmt)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("Incident pending insert failed",
                       extra={"incident_id": group_id, "error_type": type(exc).__name__})
    finally:
        session.close()


async def _settle_then_run(group_id: str, settle_ms: int) -> None:
    try:
        await asyncio.sleep(settle_ms / 1000.0)
    except asyncio.CancelledError:
        return
    from app.core.database import SessionLocal

    db = SessionLocal()
    update_attempted = False
    try:
        incident = await run_combined_pass(db, group_id)
        if incident is not None:
            from app.services import incident_notifications

            update_attempted = True
            await incident_notifications.maybe_send_update_push(db, incident)
    except Exception as exc:
        db.rollback()
        try:
            incident = db.get(Incident, group_id)
            if incident is not None and incident.status == "pending":
                incident.status = "failed"
                db.commit()
            if incident is not None and incident.status == "failed" and not update_attempted:
                # "failed" behaves like "fallback": update push with per-camera text.
                from app.services import incident_notifications

                await incident_notifications.maybe_send_update_push(db, incident)
        except Exception:
            db.rollback()
        logger.warning(
            "Incident combined pass failed",
            extra={"event_type": "incident_combined_pass_error", "incident_id": group_id,
                   "error_type": type(exc).__name__},
        )
    finally:
        db.close()
        if _pending_tasks.get(group_id) is asyncio.current_task():
            _pending_tasks.pop(group_id, None)


async def sweep_pending_incidents(older_than_ms: Optional[int] = None) -> int:
    """Startup sweeper: recompute incidents left ``pending`` by a restart."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    count = 0
    try:
        if not combined_description_enabled(db):
            return 0
        cutoff_ms = older_than_ms if older_than_ms is not None else resolve_settle_ms() + 30_000
        now = datetime.now(timezone.utc)
        for incident in db.query(Incident).filter(Incident.status == "pending").all():
            created = incident.updated_at or incident.created_at
            if created is not None and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created is not None and (now - created).total_seconds() * 1000 < cutoff_ms:
                continue
            done = await run_combined_pass(db, incident.id)
            if done is not None:
                from app.services import incident_notifications

                await incident_notifications.maybe_send_update_push(db, done)
            count += 1
    except Exception as exc:
        db.rollback()
        logger.warning("Incident sweep failed", extra={"error_type": type(exc).__name__})
    finally:
        db.close()
    return count
