"""Read-only queries behind the MCP tools (issue #648).

Every function takes an open SQLAlchemy session, uses ORM queries only, never
writes, and returns ``(result_dict, result_count)``. Results are compact:
descriptions are truncated, lists are capped, and base64 thumbnails, frames,
clips, embeddings, and file paths are never included.
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from datetime import datetime
from typing import Any, Callable, Iterable, Optional

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session, load_only

from app.models.camera import Camera
from app.models.event import Event
from app.models.recognized_entity import EntityEvent, RecognizedEntity
from app.models.system_setting import SystemSetting
from app.services.identification import loads_identification
from app.services.mcp_connector.thumbnails import signed_thumbnail_url
from app.services.mcp_connector.time_window import (
    TimeWindow,
    as_utc,
    parse_window,
    resolve_timezone,
    to_local_iso,
)

MAX_LIMIT = 100
SUMMARY_EVENT_CAP = 2000
SUMMARY_INCIDENT_CAP = 25
DESCRIPTION_CHARS = 280
SHORT_DESCRIPTION_CHARS = 160
OBJECT_TYPES = ("person", "vehicle", "package", "animal")
_UNKNOWN_VALUES = {"", "unknown", "cannot_tell", "none", None}
_PICKUP_RE = re.compile(
    r"\b(?:pick(?:s|ed|ing)?\s+up|picked\s+it\s+up|retriev(?:e|es|ed|ing)|"
    r"collect(?:s|ed|ing)?|(?:takes|took|taking|grabs|grabbed)\s+(?:the|a)\s+(?:package|parcel|box))\b",
    re.IGNORECASE,
)

# Columns the tools read. Large columns (thumbnail_base64, key_frames_base64,
# bounding boxes, embeddings) are never loaded.
_EVENT_COLUMNS = (
    Event.id,
    Event.camera_id,
    Event.timestamp,
    Event.description,
    Event.enriched_description,
    Event.objects_detected,
    Event.smart_detection_type,
    Event.is_doorbell_ring,
    Event.alert_triggered,
    Event.correlation_group_id,
    Event.delivery_carrier,
    Event.identification,
    Event.matched_entity_ids,
    Event.final_entity_id,
    Event.confidence,
)
_HAS_THUMBNAIL = or_(Event.thumbnail_path.isnot(None), Event.thumbnail_base64.isnot(None)).label("has_thumbnail")


class ToolInputError(ValueError):
    """Bad tool input. The message is safe to return to the caller."""


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------

def household_timezone(db: Session):
    row = db.query(SystemSetting.value).filter(SystemSetting.key == "settings_timezone").first()
    return resolve_timezone(row[0] if row else None)


def _tz_name(tz) -> str:
    return getattr(tz, "key", None) or str(tz)


def clamp_limit(value: Any, default: int, maximum: int = MAX_LIMIT) -> int:
    if value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ToolInputError("limit must be an integer") from None
    return max(1, min(maximum, number))


def truncate(text: Optional[str], limit: int) -> Optional[str]:
    if not text:
        return None
    value = " ".join(str(text).split())
    if len(value) <= limit:
        return value
    cut = value[: limit - 1]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,.;:") + "…"


def _objects(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if isinstance(item, str) and item][:8]


def _window_dict(window: TimeWindow, tz) -> dict:
    return {
        "start": to_local_iso(window.start, tz),
        "end": to_local_iso(window.end, tz),
        "label": window.label,
        "timezone": _tz_name(tz),
    }


def _camera_names(db: Session) -> dict[str, str]:
    return {row.id: row.name for row in db.query(Camera.id, Camera.name).limit(500).all()}


def resolve_camera_ids(db: Session, camera: Optional[str]) -> Optional[list[str]]:
    """Camera ids for an id or (case-insensitive) name. None means all cameras."""
    if camera is None or not str(camera).strip():
        return None
    value = str(camera).strip()[:100]
    exact = db.query(Camera.id).filter(
        or_(Camera.id == value, func.lower(Camera.name) == value.lower())
    ).all()
    ids = [row.id for row in exact]
    if not ids:
        ids = [
            row.id
            for row in db.query(Camera.id).filter(Camera.name.icontains(value, autoescape=True)).limit(20).all()
        ]
    if not ids:
        known = sorted(_camera_names(db).values())[:30]
        raise ToolInputError(
            f"No camera matches '{value}'. Known cameras: {', '.join(known) if known else 'none'}"
        )
    return ids


def _object_filter(object_type: str):
    clauses = [
        Event.smart_detection_type == object_type,
        Event.objects_detected.contains(f'"{object_type}"', autoescape=True),
    ]
    if object_type == "package":
        clauses.append(Event.delivery_carrier.isnot(None))
    return or_(*clauses)


def _identification_brief(raw: Optional[str]) -> Optional[dict]:
    ident = loads_identification(raw)
    if not ident:
        return None
    brief = {}
    for key in ("object_type", "count", "action", "direction", "package_or_carrier"):
        value = ident.get(key)
        if value in _UNKNOWN_VALUES or (key == "count" and not value):
            continue
        brief[key] = value
    return brief or None


def _entity_brief(entries: Iterable[dict]) -> list[dict]:
    people = []
    for entry in list(entries)[:6]:
        label = entry.get("display_name") or entry.get("name")
        if not label:
            continue
        people.append({
            "label": label,
            "type": entry.get("entity_type") or "unknown",
            "named": bool(entry.get("name")),
        })
    return people


def _event_entities(db: Session, events: list) -> dict[str, list[dict]]:
    if not events:
        return {}
    from app.services.entity_service import build_event_entities

    return build_event_entities(db, events)


def _brief_event(
    event,
    *,
    has_thumbnail: bool,
    camera_names: dict,
    entities: dict,
    tz,
    description_chars: int = DESCRIPTION_CHARS,
) -> dict:
    item: dict[str, Any] = {
        "id": event.id,
        "time": to_local_iso(event.timestamp, tz),
        "camera": camera_names.get(event.camera_id, "Unknown camera"),
        "description": truncate(event.enriched_description or event.description, description_chars),
        "objects": _objects(event.objects_detected),
    }
    if event.smart_detection_type:
        item["detection"] = event.smart_detection_type
    if event.is_doorbell_ring:
        item["doorbell_ring"] = True
    people = _entity_brief(entities.get(event.id, []))
    if people:
        item["people_vehicles"] = people
    ident = _identification_brief(event.identification)
    if ident:
        item["identification"] = ident
    if event.delivery_carrier:
        item["carrier"] = event.delivery_carrier
    if event.correlation_group_id:
        item["incident_id"] = event.correlation_group_id
    if has_thumbnail:
        item["thumbnail_url"] = signed_thumbnail_url(event.id)
    return item


def _event_query(db: Session, window: TimeWindow):
    return (
        db.query(Event, _HAS_THUMBNAIL)
        .options(load_only(*_EVENT_COLUMNS))
        .filter(Event.timestamp >= window.start, Event.timestamp <= window.end)
    )


def _parse_object_type(object_type: Optional[str]) -> Optional[str]:
    if object_type is None or not str(object_type).strip():
        return None
    value = str(object_type).strip().lower()
    if value not in OBJECT_TYPES:
        raise ToolInputError(f"object_type must be one of: {', '.join(OBJECT_TYPES)}")
    return value


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

def recent_events(
    db: Session,
    *,
    since: Optional[str] = None,
    camera: Optional[str] = None,
    limit: Any = None,
    object_type: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[dict, int]:
    tz = household_timezone(db)
    window = parse_window(since, default="1h", tz=tz, now=now)
    limit_value = clamp_limit(limit, default=20)
    object_value = _parse_object_type(object_type)
    camera_ids = resolve_camera_ids(db, camera)

    query = _event_query(db, window)
    if camera_ids is not None:
        query = query.filter(Event.camera_id.in_(camera_ids))
    if object_value:
        query = query.filter(_object_filter(object_value))
    rows = query.order_by(desc(Event.timestamp)).limit(limit_value + 1).all()
    truncated = len(rows) > limit_value
    rows = rows[:limit_value]

    events = [row[0] for row in rows]
    entities = _event_entities(db, events)
    names = _camera_names(db)
    items = [
        _brief_event(event, has_thumbnail=bool(has_thumb), camera_names=names, entities=entities, tz=tz)
        for event, has_thumb in rows
    ]
    return {
        "window": _window_dict(window, tz),
        "count": len(items),
        "truncated": truncated,
        "events": items,
    }, len(items)


def event_summary(
    db: Session,
    *,
    window: Optional[str] = None,
    camera: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[dict, int]:
    tz = household_timezone(db)
    span = parse_window(window, default="today", tz=tz, now=now)
    camera_ids = resolve_camera_ids(db, camera)

    query = _event_query(db, span)
    if camera_ids is not None:
        query = query.filter(Event.camera_id.in_(camera_ids))
    rows = query.order_by(Event.timestamp).limit(SUMMARY_EVENT_CAP + 1).all()
    partial = len(rows) > SUMMARY_EVENT_CAP
    rows = rows[:SUMMARY_EVENT_CAP]
    events = [row[0] for row in rows]
    has_thumb = {row[0].id: bool(row[1]) for row in rows}
    names = _camera_names(db)
    entities = _event_entities(db, events)

    by_camera: Counter = Counter()
    by_object: Counter = Counter()
    doorbell_rings = 0
    package_events = 0
    alerts = 0
    visitors: dict[str, dict] = {}
    groups: dict[str, list] = {}
    for event in events:
        camera_name = names.get(event.camera_id, "Unknown camera")
        by_camera[camera_name] += 1
        objects = _objects(event.objects_detected)
        for obj in set(objects):
            by_object[obj] += 1
        if event.is_doorbell_ring:
            doorbell_rings += 1
        if "package" in objects or event.smart_detection_type == "package" or event.delivery_carrier:
            package_events += 1
        if event.alert_triggered:
            alerts += 1
        for entry in entities.get(event.id, []):
            if not entry.get("name"):
                continue
            key = entry.get("id") or entry["name"]
            seen = visitors.setdefault(key, {
                "name": entry["name"], "type": entry.get("entity_type") or "unknown", "sightings": 0, "last_seen": None,
            })
            seen["sightings"] += 1
            seen["last_seen"] = to_local_iso(event.timestamp, tz)
        group_key = event.correlation_group_id or f"event:{event.id}"
        groups.setdefault(group_key, []).append(event)

    incidents = []
    for key, members in groups.items():
        cameras = list(dict.fromkeys(names.get(m.camera_id, "Unknown camera") for m in members))
        objects = list(dict.fromkeys(obj for m in members for obj in _objects(m.objects_detected)))
        people = list(dict.fromkeys(
            p["label"] for m in members for p in _entity_brief(entities.get(m.id, []))
        ))
        lead = max(members, key=lambda m: (len(m.enriched_description or m.description or ""), m.confidence or 0))
        incident: dict[str, Any] = {
            "start": to_local_iso(members[0].timestamp, tz),
            "end": to_local_iso(members[-1].timestamp, tz),
            "cameras": cameras,
            "objects": objects,
            "event_count": len(members),
            "summary": truncate(lead.enriched_description or lead.description, 220),
            "event_id": lead.id,
        }
        if not key.startswith("event:"):
            incident["incident_id"] = key
        if people:
            incident["people_vehicles"] = people[:6]
        if any(m.is_doorbell_ring for m in members):
            incident["doorbell_ring"] = True
        if has_thumb.get(lead.id):
            incident["thumbnail_url"] = signed_thumbnail_url(lead.id)
        incidents.append(incident)
    incidents.sort(key=lambda item: item["start"] or "", reverse=True)

    total = len(events)
    headline_parts = [f"{total} event{'s' if total != 1 else ''}"]
    if by_camera:
        headline_parts.append(f"on {len(by_camera)} camera{'s' if len(by_camera) != 1 else ''}")
    if len(incidents) != total:
        headline_parts.append(f"({len(incidents)} incidents after grouping multi-camera events)")
    headline = " ".join(headline_parts)
    if by_object:
        headline += "; " + ", ".join(f"{count} {obj}" for obj, count in by_object.most_common(5))
    if doorbell_rings:
        headline += f"; {doorbell_rings} doorbell ring{'s' if doorbell_rings != 1 else ''}"

    result = {
        "window": _window_dict(span, tz),
        "headline": headline,
        "totals": {
            "events": total,
            "incidents": len(incidents),
            "doorbell_rings": doorbell_rings,
            "package_events": package_events,
            "alerts_triggered": alerts,
            "by_camera": dict(by_camera.most_common()),
            "by_object": dict(by_object.most_common()),
        },
        "named_visitors": sorted(visitors.values(), key=lambda v: v["sightings"], reverse=True)[:15],
        "incidents": incidents[:SUMMARY_INCIDENT_CAP],
        "incidents_truncated": len(incidents) > SUMMARY_INCIDENT_CAP,
        "partial": partial,
    }
    return result, total


def _default_status_provider(camera: Camera) -> tuple[str, Optional[str]]:
    """(status, reason) from in-memory service state. No network or DB writes."""
    if not camera.is_enabled:
        return "disabled", "disabled in settings"
    from app.services.service_container import container

    if camera.source_type == "protect":
        try:
            protect = container.protect_service
            controller = protect.get_connection_status(camera.protect_controller_id) if camera.protect_controller_id else None
            if controller is not None and not controller.get("connected"):
                return "unknown", "Protect controller not connected"
            online = protect.get_cached_camera_online(camera.protect_controller_id, camera.protect_camera_id)
        except Exception:
            return "unknown", "Protect status unavailable"
        if online is None:
            return "unknown", "no status reported yet"
        return ("online", None) if online else ("offline", "reported offline by Protect")

    try:
        status = container.camera_service.get_camera_status(camera.id) or {}
    except Exception:
        return "unknown", "capture status unavailable"
    if status.get("capture_disabled"):
        return "offline", "capture disabled after repeated failures"
    if status.get("worker_alive"):
        return "online", None
    return "offline", "capture worker not running"


def camera_status(
    db: Session,
    *,
    status_provider: Optional[Callable[[Camera], tuple[str, Optional[str]]]] = None,
) -> tuple[dict, int]:
    tz = household_timezone(db)
    provider = status_provider or _default_status_provider
    cameras = (
        db.query(Camera)
        .options(load_only(
            Camera.id, Camera.name, Camera.source_type, Camera.is_enabled, Camera.is_doorbell,
            Camera.protect_controller_id, Camera.protect_camera_id,
        ))
        .order_by(Camera.name)
        .limit(MAX_LIMIT)
        .all()
    )
    latest = (
        db.query(Event.camera_id, func.max(Event.timestamp).label("last_ts"))
        .group_by(Event.camera_id)
        .subquery()
    )
    last_rows = (
        db.query(Event.camera_id, Event.timestamp, Event.description, Event.enriched_description)
        .join(latest, (Event.camera_id == latest.c.camera_id) & (Event.timestamp == latest.c.last_ts))
        .all()
    )
    last_by_camera = {row.camera_id: row for row in last_rows}

    items = []
    counts: Counter = Counter()
    for camera in cameras:
        status, reason = provider(camera)
        counts[status] += 1
        item: dict[str, Any] = {
            "id": camera.id,
            "name": camera.name,
            "source": camera.source_type,
            "status": status,
        }
        if reason:
            item["status_reason"] = reason
        if camera.is_doorbell:
            item["doorbell"] = True
        last = last_by_camera.get(camera.id)
        if last is not None:
            item["last_event_at"] = to_local_iso(last.timestamp, tz)
            item["last_event"] = truncate(last.enriched_description or last.description, SHORT_DESCRIPTION_CHARS)
        else:
            item["last_event_at"] = None
        items.append(item)
    return {
        "timezone": _tz_name(tz),
        "counts": dict(counts),
        "cameras": items,
    }, len(items)


def package_status(
    db: Session,
    *,
    since: Optional[str] = None,
    camera: Optional[str] = None,
    now: Optional[datetime] = None,
) -> tuple[dict, int]:
    tz = household_timezone(db)
    window = parse_window(since, default="today", tz=tz, now=now)
    camera_ids = resolve_camera_ids(db, camera)

    query = _event_query(db, window).filter(_object_filter("package"))
    if camera_ids is not None:
        query = query.filter(Event.camera_id.in_(camera_ids))
    rows = query.order_by(desc(Event.timestamp)).limit(21).all()
    truncated = len(rows) > 20
    rows = rows[:20]
    names = _camera_names(db)

    later_by_camera: dict[str, list] = {}
    if rows:
        earliest = min(as_utc(row[0].timestamp) for row in rows)
        later_rows = (
            db.query(Event)
            .options(load_only(Event.id, Event.camera_id, Event.timestamp, Event.description, Event.objects_detected))
            .filter(
                Event.camera_id.in_({row[0].camera_id for row in rows}),
                Event.timestamp > earliest,
                Event.timestamp <= window.end,
            )
            .order_by(Event.timestamp)
            .limit(500)
            .all()
        )
        for later in later_rows:
            later_by_camera.setdefault(later.camera_id, []).append(later)

    packages = []
    for event, has_thumb in rows:
        delivered_at = as_utc(event.timestamp)
        after = [
            e for e in later_by_camera.get(event.camera_id, [])
            if e.id != event.id and as_utc(e.timestamp) > delivered_at
        ]
        evidence = next((e for e in after if _PICKUP_RE.search(e.description or "")), None)
        item: dict[str, Any] = {
            "event_id": event.id,
            "delivered_at": to_local_iso(event.timestamp, tz),
            "camera": names.get(event.camera_id, "Unknown camera"),
            "carrier": event.delivery_carrier or "unknown",
            "description": truncate(event.enriched_description or event.description, SHORT_DESCRIPTION_CHARS),
            "later_person_events_on_camera": sum(1 for e in after if "person" in _objects(e.objects_detected)),
            "pickup_status": "possibly_picked_up" if evidence else "no_pickup_seen",
        }
        if evidence is not None:
            item["pickup_evidence"] = {
                "time": to_local_iso(evidence.timestamp, tz),
                "description": truncate(evidence.description, SHORT_DESCRIPTION_CHARS),
            }
        if has_thumb:
            item["thumbnail_url"] = signed_thumbnail_url(event.id)
        packages.append(item)

    return {
        "window": _window_dict(window, tz),
        "package_events": len(packages),
        "truncated": truncated,
        "packages": packages,
        "pickup_tracking": "best_effort",
        "note": (
            "ArgusAI records package deliveries that cameras and AI detect. It does not confirm pickups. "
            "'possibly_picked_up' means a later event on the same camera described something being picked up; "
            "'no_pickup_seen' means no such event was found, not that the package is still there."
        ),
    }, len(packages)


def entity_sightings(
    db: Session,
    *,
    name: Optional[str],
    since: Optional[str] = None,
    limit: Any = None,
    now: Optional[datetime] = None,
) -> tuple[dict, int]:
    query_name = (name or "").strip()
    if not query_name:
        raise ToolInputError("name is required")
    if len(query_name) > 100:
        raise ToolInputError("name must be 100 characters or fewer")
    tz = household_timezone(db)
    window = parse_window(since, default="7d", tz=tz, now=now)
    limit_value = clamp_limit(limit, default=10, maximum=50)

    entity_columns = load_only(
        RecognizedEntity.id, RecognizedEntity.name, RecognizedEntity.entity_type,
        RecognizedEntity.first_seen_at, RecognizedEntity.last_seen_at, RecognizedEntity.occurrence_count,
        RecognizedEntity.is_vip,
    )
    matches = (
        db.query(RecognizedEntity).options(entity_columns)
        .filter(func.lower(RecognizedEntity.name) == query_name.lower())
        .limit(5).all()
    )
    if not matches:
        matches = (
            db.query(RecognizedEntity).options(entity_columns)
            .filter(RecognizedEntity.name.icontains(query_name, autoescape=True))
            .order_by(desc(RecognizedEntity.last_seen_at))
            .limit(5).all()
        )
    if not matches:
        known = [row[0] for row in db.query(RecognizedEntity.name).filter(RecognizedEntity.name.isnot(None)).limit(500)]
        suggestions = difflib.get_close_matches(query_name, [k for k in known if k], n=5, cutoff=0.6)
        return {
            "query": query_name,
            "found": False,
            "window": _window_dict(window, tz),
            "suggestions": suggestions,
            "note": "No named person or vehicle matches. Names come from entities labelled in ArgusAI.",
        }, 0

    names = _camera_names(db)
    results = []
    total = 0
    for entity in matches:
        linked = select(EntityEvent.event_id).where(EntityEvent.entity_id == entity.id)
        rows = (
            _event_query(db, window)
            .filter(or_(
                Event.id.in_(linked),
                Event.final_entity_id == entity.id,
                Event.matched_entity_ids.contains(f'"{entity.id}"', autoescape=True),
            ))
            .order_by(desc(Event.timestamp))
            .limit(limit_value + 1)
            .all()
        )
        truncated = len(rows) > limit_value
        rows = rows[:limit_value]
        sightings = []
        for event, has_thumb in rows:
            sighting: dict[str, Any] = {
                "event_id": event.id,
                "time": to_local_iso(event.timestamp, tz),
                "camera": names.get(event.camera_id, "Unknown camera"),
                "description": truncate(event.enriched_description or event.description, SHORT_DESCRIPTION_CHARS),
            }
            if has_thumb:
                sighting["thumbnail_url"] = signed_thumbnail_url(event.id)
            sightings.append(sighting)
        total += len(sightings)
        results.append({
            "name": entity.name,
            "type": entity.entity_type,
            "vip": bool(entity.is_vip),
            "first_seen": to_local_iso(entity.first_seen_at, tz),
            "last_seen": to_local_iso(entity.last_seen_at, tz),
            "total_sightings": entity.occurrence_count,
            "sightings_in_window": sightings,
            "sightings_truncated": truncated,
        })
    return {
        "query": query_name,
        "found": True,
        "window": _window_dict(window, tz),
        "matches": results,
    }, total
