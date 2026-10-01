#!/usr/bin/env python3
"""Compare the previous and current event-identification inputs.

Read-only against the database: the connection refuses every statement that is
not a query. Nothing is written back to events, and reanalysis is not persisted.
Live mode does not write event media. Temporary clips are deleted after use.

--dry-run is the default. It plans frames and prompts only and does not call a
vision provider.

--fetch-protect-timing looks up Protect start/end/detected thumbnails for events
that store a Protect event id. It uses the stored controller credentials and
does not call ProtectService.connect (that path writes connection state).

--live runs both plans through the configured provider chain. It prints an
estimated cost first and refuses to start without --yes. The default cap is
10 events and the hard maximum is 25.

Usage (fixtures only; do not point this at a live database or API key):

    cd backend
    python scripts/compare_event_identification.py \\
        --fixture path/to/events.json \\
        --dry-run \\
        --output-dir /tmp/identification-compare
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import inspect
import json
import logging
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.event_sampling import (  # noqa: E402
    DetectionTiming,
    SubjectBox,
    allocate_subject_crops,
    legacy_uniform_offsets,
    plan_clip_window,
    plan_frame_offsets,
)
from app.services.identification import (  # noqa: E402
    append_subject_crop_note,
    ensure_identification_prompt,
)

logger = logging.getLogger(__name__)

# Statements a comparison run is allowed to send. Everything else fails closed.
_READ_ONLY_HEADS = {"SELECT", "WITH", "PRAGMA", "EXPLAIN", "BEGIN", "COMMIT", "ROLLBACK"}
_EVENT_ID = re.compile(r"^[0-9a-fA-F-]{8,40}$")
_EVENT_COLUMNS = (
    "id",
    "timestamp",
    "bounding_boxes",
    "smart_detection_type",
    "protect_event_id",
    "camera_id",
    "video_path",
    "detection_start",
    "detection_end",
    "detection_peak",
    "subject_box",
)
_CAMERA_COLUMNS = ("protect_controller_id", "protect_camera_id")
_ALLOWED_TABLES = {"events", "cameras", "protect_controllers", "system_settings"}
_PROVIDER_KEY_NAMES = {
    "ai_api_key_openai": "openai",
    "ai_api_key_grok": "grok",
    "ai_api_key_claude": "claude",
    "ai_api_key_gemini": "gemini",
}

LIVE_DEFAULT_CAP = 10
LIVE_HARD_MAX = 25
SLA_MS = 10000

# The previous multi-frame prompt did not ask for identification JSON.
OLD_PROMPT = (
    "These are frames from one security camera, in time order. "
    "Describe what the subject does in one or two factual sentences."
)

# Local estimate only. Not a billed amount and not a provider response.
_TOKENS_PER_IMAGE = 85
_USD_PER_1K_TOKENS = 0.00015


def assert_read_only(statement: Optional[str]) -> None:
    """Raise when ``statement`` is not a read."""
    text = (statement or "").lstrip()
    while text.startswith("--"):
        newline = text.find("\n")
        text = "" if newline < 0 else text[newline + 1:].lstrip()
    if text.startswith("/*"):
        end = text.find("*/")
        text = "" if end < 0 else text[end + 2:].lstrip()
    if not text:
        return
    head = text.split(None, 1)[0].upper().rstrip(";")
    if head not in _READ_ONLY_HEADS:
        raise RuntimeError(f"read-only comparison refused {head}")


def open_read_only_engine(database_url: str):
    """Engine that rejects writes before they reach the database."""
    from sqlalchemy import create_engine, event

    engine = create_engine(database_url)

    @event.listens_for(engine, "before_cursor_execute")
    def _guard(conn, cursor, statement, parameters, context, executemany):
        assert_read_only(statement)

    return engine


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    text = str(value).strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _box_from_event(event: dict) -> Optional[SubjectBox]:
    raw = event.get("box")
    if not isinstance(raw, dict):
        return None
    try:
        x = float(raw["x"])
        y = float(raw["y"])
        width = float(raw["width"])
        height = float(raw["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if width <= 0 or height <= 0:
        return None
    normalized = raw.get("normalized")
    if normalized is None:
        normalized = max(x, y, width, height) <= 1.0
    return SubjectBox(x, y, width, height, source="fixture", normalized=bool(normalized))


def _sample_payload(samples) -> Dict[str, Any]:
    return {
        "offsets_s": [round(sample.offset_seconds, 3) for sample in samples],
        "kinds": [sample.kind for sample in samples],
    }


def _estimate(image_count: int, prompt: str) -> Dict[str, Any]:
    tokens = int(len(prompt) / 4) + int(image_count) * _TOKENS_PER_IMAGE
    return {
        "tokens_estimate": tokens,
        "cost_estimate_usd": round(tokens / 1000.0 * _USD_PER_1K_TOKENS, 6),
        "estimate_source": "local_image_budget",
    }


def plan_old(event: dict, frame_count: int, offset_ms: int) -> Dict[str, Any]:
    """Fixed 15s/15s window, even spacing, no subject crop."""
    duration = 30.0
    samples = legacy_uniform_offsets(duration, frame_count, offset_ms)
    prompt = OLD_PROMPT
    return {
        "window_source": "fixed_30s",
        "duration_s": duration,
        "subject_crop_used": False,
        "crop_count": 0,
        "full_count": len(samples),
        "image_count": len(samples),
        "prompt": prompt,
        **_sample_payload(samples),
        **_estimate(len(samples), prompt),
    }


def plan_new(event: dict, frame_count: int, offset_ms: int, crop_count: int) -> Dict[str, Any]:
    """Smart-detect window when the event has timing, otherwise the old window."""
    peak_raw = event.get("peak")
    if peak_raw in (None, ""):
        peak_raw = event.get("detection_peak")
    timing = DetectionTiming(
        start=_parse_dt(event.get("detection_start")),
        end=_parse_dt(event.get("detection_end")),
        peak=_parse_dt(peak_raw),
        anchor=_parse_dt(event.get("timestamp")),
    )
    clip = plan_clip_window(timing)
    if clip.source == "smart_detect":
        samples = plan_frame_offsets(
            clip.duration_s,
            frame_count,
            clip.detection_start_s,
            clip.detection_end_s,
            clip.peak_s,
            offset_ms=0,
        )
    else:
        samples = plan_frame_offsets(
            clip.duration_s,
            frame_count,
            None,
            None,
            None,
            offset_ms=offset_ms,
        )

    box = _box_from_event(event)
    used_crop = False
    crop_n = 0
    crop_offsets: List[float] = []
    kept = samples
    if box is not None and crop_count > 0 and len(samples) >= 2:
        kept, crop_times = allocate_subject_crops(samples, crop_count, clip.peak_s)
        # A crop replaces a full frame. If nothing could be dropped, skip the crop
        # so the image budget does not grow.
        if len(kept) + len(crop_times) > len(samples):
            kept = samples
            crop_times = []
        used_crop = bool(crop_times)
        crop_n = len(crop_times)
        crop_offsets = [round(moment, 3) for moment in crop_times]

    prompt = ensure_identification_prompt(OLD_PROMPT)
    if used_crop:
        prompt = append_subject_crop_note(prompt, len(kept), crop_n)
    image_count = len(kept) + crop_n
    return {
        "window_source": clip.source,
        "duration_s": round(clip.duration_s, 3),
        "detection_start_s": clip.detection_start_s,
        "detection_end_s": clip.detection_end_s,
        "peak_s": clip.peak_s,
        "subject_crop_used": used_crop,
        "crop_count": crop_n,
        "crop_offsets_s": crop_offsets,
        "full_count": len(kept),
        "image_count": image_count,
        "prompt": prompt,
        **_sample_payload(kept),
        **_estimate(image_count, prompt),
    }


def _safe_error_label(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if not text or len(text) > 80 or " " in text:
        return "unavailable"
    return text


def _ai_fields(described: Optional[dict]) -> Dict[str, Any]:
    described = described or {}
    identification = described.get("identification")
    if not isinstance(identification, dict):
        identification = None
    return {
        "description": described.get("description"),
        "identification": identification,
        "provider": described.get("provider"),
        "latency_ms": described.get("latency_ms"),
        "tokens_used": described.get("tokens_used"),
        "error": _safe_error_label(described.get("error")),
    }


def build_report(
    events: Sequence[dict],
    *,
    dry_run: bool,
    frame_count: int = 10,
    subject_crop_count: int = 1,
    offset_ms: int = 2000,
    describe=None,
) -> Dict[str, Any]:
    """Side-by-side plans. ``describe`` is invoked only when ``dry_run`` is false."""
    rows = []
    ai_calls = 0
    for event in events:
        count = int(event.get("frame_count") or frame_count)
        crops = int(event.get("subject_crop_count") if event.get("subject_crop_count") is not None else subject_crop_count)
        offset = int(event.get("offset_ms") if event.get("offset_ms") is not None else offset_ms)
        old = plan_old(event, count, offset)
        new = plan_new(event, count, offset, crops)
        if dry_run or describe is None:
            old_ai = _ai_fields(None)
            new_ai = _ai_fields(None)
        else:
            old_ai = _ai_fields(describe(event, old, "old"))
            new_ai = _ai_fields(describe(event, new, "new"))
            ai_calls += 2
        rows.append({
            "id": event.get("id"),
            "timing_fetch": event.get("timing_fetch"),
            "old": {**old, **old_ai},
            "new": {**new, **new_ai},
        })
    return {
        "dry_run": dry_run,
        "ai_calls": ai_calls,
        "live_started": False,
        "note": (
            "Dry run: frames and prompts only. No vision request was sent."
            if dry_run
            else "Descriptions are filled only when a describer is provided. The database is not updated."
        ),
        "events": rows,
    }


def estimate_report_cost(report: Dict[str, Any]) -> Dict[str, Any]:
    """Sum the local image-budget estimate for both sides. No provider is called."""
    tokens = 0
    cost = 0.0
    for row in report.get("events") or []:
        for side in ("old", "new"):
            plan = row.get(side) or {}
            tokens += int(plan.get("tokens_estimate") or 0)
            cost += float(plan.get("cost_estimate_usd") or 0.0)
    event_count = len(report.get("events") or [])
    return {
        "tokens_estimate": tokens,
        "cost_estimate_usd": round(cost, 6),
        "events": event_count,
        "calls": event_count * 2,
    }


def format_cost_estimate(report: Dict[str, Any]) -> str:
    summary = estimate_report_cost(report)
    return (
        "Estimated cost before any vision call: "
        f"${summary['cost_estimate_usd']:.6f} USD "
        f"({summary['tokens_estimate']} tokens, {summary['events']} events, "
        f"{summary['calls']} calls). Pass --yes to proceed."
    )


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Event identification comparison",
        "",
        f"Dry run: {report['dry_run']}",
        f"AI calls: {report['ai_calls']}",
        "",
        report.get("note") or "",
        "",
    ]
    for row in report["events"]:
        lines.append(f"## {row.get('id')}")
        lines.append("")
        lines.append("| | Old | New |")
        lines.append("| --- | --- | --- |")
        for key in (
            "window_source",
            "duration_s",
            "image_count",
            "subject_crop_used",
            "crop_count",
            "offsets_s",
            "description",
            "identification",
            "provider",
            "latency_ms",
            "tokens_used",
            "tokens_estimate",
            "cost_estimate_usd",
            "error",
        ):
            lines.append(f"| {key} | {row['old'].get(key)} | {row['new'].get(key)} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def load_fixture(path: Path) -> List[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data.get("events") if isinstance(data, dict) else data
    if not isinstance(events, list):
        raise SystemExit("Fixture must be a JSON object with an events list")
    return events


def _table_names(conn, dialect: str) -> set:
    from sqlalchemy import text

    if dialect == "sqlite":
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        return {row[0] for row in rows}
    rows = conn.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    ).fetchall()
    return {row[0] for row in rows}


def _column_names(conn, dialect: str, table: str) -> set:
    from sqlalchemy import text

    if table not in _ALLOWED_TABLES:
        raise RuntimeError("read-only comparison refused a table name")
    if dialect == "sqlite":
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return {row[1] for row in rows}
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :table"),
        {"table": table},
    ).fetchall()
    return {row[0] for row in rows}


def _box_dict(raw: Any) -> Optional[dict]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        return None
    try:
        return {
            "x": float(raw["x"]),
            "y": float(raw["y"]),
            "width": float(raw["width"]),
            "height": float(raw["height"]),
            "normalized": raw.get("normalized"),
        }
    except (KeyError, TypeError, ValueError):
        return None


def load_events_from_db(database_url: str, *, limit: int, event_ids: Optional[Sequence[str]]) -> List[dict]:
    """SELECT recent events. Optional Protect ids and stored timing are included when present."""
    from sqlalchemy import bindparam, text

    if event_ids:
        for event_id in event_ids:
            if not _EVENT_ID.fullmatch(event_id):
                raise SystemExit("Refused an event id that is not a UUID")
    engine = open_read_only_engine(database_url)
    with engine.connect() as conn:
        dialect = engine.dialect.name
        columns = _column_names(conn, dialect, "events")
        selected = [name for name in _EVENT_COLUMNS if name in columns]
        if "id" not in selected:
            raise SystemExit("events.id is not readable")
        camera_selected: List[str] = []
        tables = _table_names(conn, dialect)
        if "cameras" in tables and "camera_id" in columns:
            camera_columns = _column_names(conn, dialect, "cameras")
            camera_selected = [name for name in _CAMERA_COLUMNS if name in camera_columns]
        select_parts = [f"events.{name}" for name in selected]
        select_parts.extend(f"cameras.{name}" for name in camera_selected)
        join = ""
        if camera_selected:
            join = " LEFT JOIN cameras ON cameras.id = events.camera_id"
        sql_cols = ", ".join(select_parts)
        if event_ids:
            stmt = text(
                f"SELECT {sql_cols} FROM events{join} WHERE events.id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            rows = conn.execute(stmt, {"ids": list(event_ids)}).mappings().all()
        else:
            stmt = text(
                f"SELECT {sql_cols} FROM events{join} ORDER BY events.timestamp DESC LIMIT :limit"
            )
            rows = conn.execute(stmt, {"limit": int(limit)}).mappings().all()
    events = []
    for row in rows:
        subject = _box_dict(row.get("subject_box")) if "subject_box" in row.keys() else None
        box = subject or (_box_dict(row.get("bounding_boxes")) if "bounding_boxes" in row.keys() else None)
        timestamp = row.get("timestamp") if "timestamp" in row.keys() else None
        event = {
            "id": row["id"],
            "timestamp": _iso(timestamp),
            "box": box,
            "smart_detection_type": row.get("smart_detection_type") if "smart_detection_type" in row.keys() else None,
        }
        for name in ("protect_event_id", "protect_controller_id", "protect_camera_id", "video_path", "camera_id"):
            if name in row.keys() and row.get(name) is not None:
                event[name] = row.get(name)
        for name in ("detection_start", "detection_end", "detection_peak"):
            if name in row.keys() and row.get(name) is not None:
                event[name] = _iso(row.get(name))
        if event.get("detection_peak") and not event.get("peak"):
            event["peak"] = event["detection_peak"]
        events.append(event)
    return events


def load_controller_row(engine, controller_id: str) -> Optional[dict]:
    """Read one controller row. The password stays in this dict and never enters the report."""
    from sqlalchemy import text

    if not controller_id or not _EVENT_ID.fullmatch(str(controller_id)):
        return None
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if "protect_controllers" not in _table_names(conn, dialect):
            return None
        row = conn.execute(
            text(
                "SELECT id, host, port, username, password, verify_ssl "
                "FROM protect_controllers WHERE id = :id"
            ),
            {"id": controller_id},
        ).mappings().first()
    if row is None:
        return None
    return {
        "id": row["id"],
        "host": row["host"],
        "port": row["port"],
        "username": row["username"],
        "password": row["password"],
        "verify_ssl": bool(row["verify_ssl"]) if row["verify_ssl"] is not None else False,
    }


def apply_hints_to_event(event: dict, hints) -> None:
    """Copy Protect timing onto an in-memory event. An existing box is kept when Protect has none."""
    if getattr(hints, "start", None) is not None:
        event["detection_start"] = _iso(hints.start)
    if getattr(hints, "end", None) is not None:
        event["detection_end"] = _iso(hints.end)
    if getattr(hints, "peak", None) is not None:
        event["peak"] = _iso(hints.peak)
        event["detection_peak"] = _iso(hints.peak)
    boxes = getattr(hints, "boxes", None) or []
    if boxes:
        box = boxes[0]
        event["box"] = {
            "x": box.x,
            "y": box.y,
            "width": box.width,
            "height": box.height,
            "normalized": box.normalized,
        }
    event["timing_fetch"] = "ok" if hints.has_timing() else "no_timing"


async def _close_client(client) -> None:
    closer = getattr(client, "close_session", None)
    if not callable(closer):
        return
    try:
        result = closer()
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        logger.warning(
            "Protect client close failed: %s",
            type(exc).__name__,
            extra={"event_type": "compare_protect_close_failed"},
        )


async def enrich_events_with_protect(events: Sequence[dict], open_client) -> None:
    """Fill timing from Protect. ``open_client`` returns an object with get_event and close_session."""
    from app.services.protect_detection_hints import extract_detection_hints

    groups: Dict[str, List[dict]] = {}
    for event in events:
        protect_event_id = event.get("protect_event_id")
        controller_id = event.get("protect_controller_id")
        if not protect_event_id:
            event["timing_fetch"] = "no_protect_event_id"
            continue
        if not controller_id:
            event["timing_fetch"] = "no_controller"
            continue
        groups.setdefault(str(controller_id), []).append(event)

    for controller_id, group in groups.items():
        client = None
        try:
            client = await open_client(controller_id)
            for event in group:
                try:
                    protect_event = await client.get_event(event["protect_event_id"])
                    hints = extract_detection_hints(protect_event)
                    apply_hints_to_event(event, hints)
                except Exception as exc:
                    event["timing_fetch"] = type(exc).__name__
                    logger.warning(
                        "Protect timing lookup failed: %s",
                        type(exc).__name__,
                        extra={"event_type": "compare_protect_timing_failed"},
                    )
        except Exception as exc:
            label = type(exc).__name__
            logger.warning(
                "Protect timing client failed: %s",
                label,
                extra={"event_type": "compare_protect_timing_failed"},
            )
            for event in group:
                if not event.get("timing_fetch"):
                    event["timing_fetch"] = label
        finally:
            if client is not None:
                await _close_client(client)


async def open_readonly_protect_client(controller_row: dict):
    """Log in with ProtectApiClient.update. Does not call ProtectService.connect."""
    from uiprotect import ProtectApiClient

    password = controller_row.get("password") or ""
    if isinstance(password, str) and password.startswith("encrypted:"):
        from app.utils.encryption import decrypt_password
        password = decrypt_password(password)
    client = ProtectApiClient(
        host=controller_row["host"],
        port=int(controller_row.get("port") or 443),
        username=controller_row.get("username") or "",
        password=password,
        verify_ssl=bool(controller_row.get("verify_ssl")),
    )
    try:
        await client.update()
    except Exception:
        await _close_client(client)
        raise
    return client


async def fetch_protect_timing(events: Sequence[dict], database_url: str) -> None:
    engine = open_read_only_engine(database_url)

    async def open_client(controller_id: str):
        row = load_controller_row(engine, controller_id)
        if row is None:
            raise LookupError("missing_controller")
        return await open_readonly_protect_client(row)

    await enrich_events_with_protect(events, open_client)


def clip_bounds_for_side(event: dict, plan: dict, side: str):
    anchor = _parse_dt(event.get("timestamp"))
    if side == "old" or plan.get("window_source") != "smart_detect":
        if anchor is None:
            return None
        return anchor - timedelta(seconds=15), anchor + timedelta(seconds=15)
    peak_raw = event.get("peak")
    if peak_raw in (None, ""):
        peak_raw = event.get("detection_peak")
    clip = plan_clip_window(DetectionTiming(
        start=_parse_dt(event.get("detection_start")),
        end=_parse_dt(event.get("detection_end")),
        peak=_parse_dt(peak_raw),
        anchor=anchor,
    ))
    return clip.start, clip.end


async def images_from_plan(clip_path, plan: dict, box: Optional[SubjectBox]) -> List[str]:
    """JPEG frames for one side, as raw base64. Crops replace frames inside the plan."""
    from app.services.event_sampling import crop_jpeg
    from app.services.frame_extractor import get_frame_extractor

    offsets = list(plan.get("offsets_s") or [])
    if not offsets:
        return []
    extractor = get_frame_extractor()
    frames, _times = await extractor.extract_frames_with_timestamps(
        clip_path=clip_path,
        frame_count=max(1, len(offsets)),
        sampling_strategy="uniform",
        offset_ms=0,
        filter_blur=False,
        target_offsets_s=offsets,
    )
    images: List[bytes] = []
    for frame in frames or []:
        if isinstance(frame, (bytes, bytearray)):
            images.append(bytes(frame))
    crop_offsets = list(plan.get("crop_offsets_s") or [])
    if plan.get("subject_crop_used") and box is not None and crop_offsets:
        for offset in crop_offsets:
            native = await extractor.extract_native_jpeg_at(clip_path, float(offset))
            if not native:
                continue
            cropped = crop_jpeg(native, box)
            if cropped:
                images.append(cropped)
    return [base64.b64encode(img).decode("ascii") for img in images]


async def _materialize_clip(event: dict, plan: dict, side: str, download):
    """Return (path, delete_after, error_label). A stored file is not deleted."""
    local = event.get("video_path") or event.get("clip_path")
    if local:
        path = Path(str(local))
        if path.is_file():
            return path, False, None
    if download is None:
        return None, False, "no_media"
    bounds = clip_bounds_for_side(event, plan, side)
    camera_id = event.get("protect_camera_id")
    controller_id = event.get("protect_controller_id")
    if bounds is None or not camera_id or not controller_id:
        return None, False, "no_media"
    fd, name = tempfile.mkstemp(prefix="argus-compare-", suffix=".mp4")
    os.close(fd)
    path = Path(name)
    try:
        await download(controller_id, camera_id, bounds[0], bounds[1], path)
    except Exception as exc:
        path.unlink(missing_ok=True)
        logger.warning(
            "Protect clip download failed: %s",
            type(exc).__name__,
            extra={"event_type": "compare_clip_download_failed"},
        )
        return None, False, type(exc).__name__
    if not path.is_file() or path.stat().st_size == 0:
        path.unlink(missing_ok=True)
        return None, False, "no_media"
    return path, True, None


async def run_provider_chain(
    providers: Sequence[Any],
    images_base64: Sequence[str],
    prompt: str,
    camera_name: str,
    timestamp: str,
    detected_objects: Optional[Sequence[str]],
    sla_ms: int = SLA_MS,
) -> Dict[str, Any]:
    """Call providers in order. Does not record usage and does not open the database."""
    from app.services.ai_provider_order import classify_provider_error
    from app.services.identification import parse_identification

    empty = {
        "description": None,
        "identification": None,
        "provider": None,
        "latency_ms": None,
        "tokens_used": None,
        "error": "no_media",
    }
    if not images_base64:
        return empty

    started = time.monotonic()
    last_error = "unavailable"
    for provider in providers:
        remaining_ms = sla_ms - (time.monotonic() - started) * 1000.0
        if remaining_ms <= 0:
            last_error = "timeout"
            break
        call_started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                provider.generate_multi_image_description(
                    images_base64=list(images_base64),
                    camera_name=camera_name or "camera",
                    timestamp=timestamp or "",
                    detected_objects=list(detected_objects or []),
                    custom_prompt=prompt,
                ),
                timeout=remaining_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            last_error = "timeout"
            break
        except Exception as exc:
            last_error = type(exc).__name__
            continue
        latency = getattr(result, "response_time_ms", None)
        if not isinstance(latency, (int, float)):
            latency = int((time.monotonic() - call_started) * 1000)
        else:
            latency = int(latency)
        if getattr(result, "success", False):
            identification = getattr(result, "identification", None)
            if not isinstance(identification, dict):
                identification = parse_identification(getattr(result, "description", None))
            provider_name = getattr(result, "provider", None)
            if not isinstance(provider_name, str):
                provider_name = None
            tokens = getattr(result, "tokens_used", None)
            if not isinstance(tokens, int):
                tokens = None
            return {
                "description": getattr(result, "description", None),
                "identification": identification if isinstance(identification, dict) else None,
                "provider": provider_name,
                "latency_ms": latency,
                "tokens_used": tokens,
                "error": None,
            }
        raw_error = getattr(result, "error", None)
        last_error = classify_provider_error(str(raw_error)) if raw_error else "unsuccessful"
    empty["error"] = last_error
    return empty


async def fill_live_descriptions(
    events: Sequence[dict],
    report: Dict[str, Any],
    *,
    providers: Sequence[Any],
    download=None,
    image_loader=None,
) -> Dict[str, Any]:
    """Fill both sides from ``providers``. Temporary clips are removed before return."""
    ai_calls = 0
    for event, row in zip(events, report["events"]):
        for side in ("old", "new"):
            plan = row[side]
            path = None
            delete_after = False
            try:
                if image_loader is not None:
                    images = await image_loader(event, plan, side)
                else:
                    path, delete_after, media_error = await _materialize_clip(event, plan, side, download)
                    if path is None:
                        described = _ai_fields(None)
                        described["error"] = _safe_error_label(media_error or "no_media")
                        row[side].update(described)
                        continue
                    local = event.get("video_path") or event.get("clip_path")
                    if local and Path(str(local)) == path:
                        row["clip_note"] = "stored_clip_offsets_are_file_offsets"
                    images = await images_from_plan(path, plan, _box_from_event(event))
                if not images:
                    described = _ai_fields(None)
                    described["error"] = "no_media"
                    row[side].update(described)
                    continue
                described = await run_provider_chain(
                    providers,
                    images,
                    plan.get("prompt") or "",
                    str(event.get("camera_name") or "camera"),
                    str(event.get("timestamp") or ""),
                    [event["smart_detection_type"]] if event.get("smart_detection_type") else [],
                )
                row[side].update(_ai_fields(described))
                ai_calls += 1
            except Exception as exc:
                described = _ai_fields(None)
                described["error"] = type(exc).__name__
                row[side].update(described)
                logger.warning(
                    "Live comparison side failed: %s",
                    type(exc).__name__,
                    extra={"event_type": "compare_live_side_failed"},
                )
            finally:
                if delete_after and path is not None:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError as exc:
                        logger.warning(
                            "Temporary clip delete failed: %s",
                            type(exc).__name__,
                            extra={"event_type": "compare_temp_clip_delete_failed"},
                        )
    report["dry_run"] = False
    report["live_started"] = True
    report["ai_calls"] = ai_calls
    report["note"] = "Live comparison. The database and event media were not updated."
    return report


def load_provider_order(engine) -> list:
    from sqlalchemy import text

    from app.services.ai_provider_order import DEFAULT_PROVIDER_ORDER, _PROVIDER_NAME_MAP

    try:
        with engine.connect() as conn:
            if "system_settings" not in _table_names(conn, engine.dialect.name):
                return list(DEFAULT_PROVIDER_ORDER)
            row = conn.execute(
                text("SELECT value FROM system_settings WHERE key = :key"),
                {"key": "ai_provider_order"},
            ).first()
    except Exception as exc:
        logger.warning(
            "Provider order unreadable: %s",
            type(exc).__name__,
            extra={"event_type": "compare_provider_order_unreadable"},
        )
        return list(DEFAULT_PROVIDER_ORDER)
    if not row or not row[0]:
        return list(DEFAULT_PROVIDER_ORDER)
    try:
        names = json.loads(row[0])
    except (ValueError, TypeError):
        return list(DEFAULT_PROVIDER_ORDER)
    order = []
    for name in names:
        mapped = _PROVIDER_NAME_MAP.get(name)
        if mapped is not None:
            order.append(mapped)
    return order or list(DEFAULT_PROVIDER_ORDER)


def load_decrypted_provider_keys(engine) -> Dict[str, str]:
    from sqlalchemy import text

    found: Dict[str, str] = {}
    try:
        with engine.connect() as conn:
            if "system_settings" not in _table_names(conn, engine.dialect.name):
                return {}
            rows = conn.execute(
                text(
                    "SELECT key, value FROM system_settings WHERE key IN "
                    "('ai_api_key_openai', 'ai_api_key_grok', 'ai_api_key_claude', 'ai_api_key_gemini')"
                )
            ).mappings().all()
    except Exception as exc:
        logger.warning(
            "Provider keys unreadable: %s",
            type(exc).__name__,
            extra={"event_type": "compare_provider_keys_unreadable"},
        )
        return {}
    for row in rows:
        name = _PROVIDER_KEY_NAMES.get(row["key"])
        raw = row["value"]
        if not name or not isinstance(raw, str) or not raw:
            continue
        try:
            secret = raw
            if raw.startswith("encrypted:"):
                from app.utils.encryption import decrypt_password
                secret = decrypt_password(raw)
        except Exception as exc:
            logger.warning(
                "Provider key decrypt failed: %s",
                type(exc).__name__,
                extra={"event_type": "compare_provider_key_decrypt_failed"},
            )
            continue
        if isinstance(secret, str) and secret:
            found[name] = secret
    return found


def build_live_providers(keys: Dict[str, str], order: Sequence[Any]) -> list:
    from app.services.ai_providers.claude_provider import ClaudeProvider
    from app.services.ai_providers.gemini_provider import GeminiProvider
    from app.services.ai_providers.grok_provider import GrokProvider
    from app.services.ai_providers.openai_provider import OpenAIProvider
    from app.services.ai_types import AIProvider

    classes = {
        AIProvider.OPENAI: OpenAIProvider,
        AIProvider.GROK: GrokProvider,
        AIProvider.CLAUDE: ClaudeProvider,
        AIProvider.GEMINI: GeminiProvider,
    }
    clients = []
    for provider in order:
        secret = keys.get(getattr(provider, "value", ""))
        cls = classes.get(provider)
        if not secret or cls is None:
            continue
        try:
            clients.append(cls(secret))
        except Exception as exc:
            logger.warning(
                "Vision provider skipped: %s",
                type(exc).__name__,
                extra={"event_type": "compare_provider_unavailable"},
            )
    return clients


def write_report(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    (output_dir / "comparison.md").write_text(render_markdown(report), encoding="utf-8")


def _guard_live_flags(args) -> None:
    if args.live and args.dry_run:
        raise SystemExit("--live and --dry-run cannot be combined")
    if args.live and not (1 <= int(args.limit) <= LIVE_HARD_MAX):
        raise SystemExit(f"--live --limit must be between 1 and {LIVE_HARD_MAX}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare old and new identification inputs")
    parser.add_argument("--fixture", type=Path, help="JSON fixture. Does not open the database.")
    parser.add_argument("--dry-run", action="store_true", help="Plan frames and prompts. Make no AI calls. This is the default.")
    parser.add_argument("--live", action="store_true", help="Call the configured vision providers. Requires --yes.")
    parser.add_argument("--yes", action="store_true", help="Confirm the printed cost estimate and start --live.")
    parser.add_argument(
        "--fetch-protect-timing",
        action="store_true",
        help="Read Protect start/end/peak for events that store a Protect event id. Does not write.",
    )
    parser.add_argument("--event-ids", help="Comma-separated event ids (read-only SELECT)")
    parser.add_argument("--limit", type=int, default=LIVE_DEFAULT_CAP, help="Recent events when no ids are given")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--frame-count", type=int, default=10)
    parser.add_argument("--subject-crop-count", type=int, default=1)
    parser.add_argument("--offset-ms", type=int, default=2000)
    args = parser.parse_args(argv)
    _guard_live_flags(args)

    database_url = args.database_url
    if args.fixture:
        if args.fetch_protect_timing:
            raise SystemExit("--fetch-protect-timing requires --database-url and does not apply to a fixture")
        events = load_fixture(args.fixture)
    else:
        if not database_url:
            raise SystemExit("Pass --fixture or --database-url. This script does not guess a database.")
        ids = [part.strip() for part in args.event_ids.split(",")] if args.event_ids else None
        events = load_events_from_db(database_url, limit=args.limit, event_ids=ids)

    if args.live:
        events = list(events)[: int(args.limit)]

    if args.fetch_protect_timing:
        asyncio.run(fetch_protect_timing(events, database_url))

    # Plans are built before any provider call so the cost line is real.
    # dry_run stays true until fill_live_descriptions actually calls a provider.
    report = build_report(
        events,
        dry_run=True,
        frame_count=args.frame_count,
        subject_crop_count=args.subject_crop_count,
        offset_ms=args.offset_ms,
        describe=None,
    )
    if not args.live:
        write_report(report, args.output_dir)
        return 0

    print(format_cost_estimate(report))
    if not args.yes:
        report["blocked"] = "confirmation_required"
        report["live_started"] = False
        write_report(report, args.output_dir)
        raise SystemExit("Refused to call a vision provider without --yes")
    if not database_url:
        raise SystemExit("No vision provider key is configured.")

    engine = open_read_only_engine(database_url)
    keys = load_decrypted_provider_keys(engine)
    if not keys:
        raise SystemExit("No vision provider key is configured.")
    providers = build_live_providers(keys, load_provider_order(engine))
    keys.clear()
    if not providers:
        raise SystemExit("No vision provider key is configured.")

    _download_clients: Dict[str, Any] = {}

    async def _download(controller_id, camera_id, start, end, output_file):
        if controller_id not in _download_clients:
            row = load_controller_row(engine, controller_id)
            if row is None:
                raise LookupError("missing_controller")
            _download_clients[controller_id] = await open_readonly_protect_client(row)
        client = _download_clients[controller_id]
        video = client.get_camera_video(camera_id, start, end, output_file=Path(output_file))
        if inspect.isawaitable(video):
            await video

    try:
        asyncio.run(fill_live_descriptions(events, report, providers=providers, download=_download))
    finally:
        async def _close_all():
            for client in _download_clients.values():
                await _close_client(client)

        if _download_clients:
            asyncio.run(_close_all())
        keys.clear()
    write_report(report, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
