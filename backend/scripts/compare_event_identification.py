#!/usr/bin/env python3
"""Compare the previous and current event-identification inputs.

Read-only against the database: the connection refuses every statement that is
not a query. Nothing is written back to events, and reanalysis is not persisted.

--dry-run plans frames and prompts only. It does not call a vision provider.

Usage (fixtures only; do not point this at a live database or API key):

    cd backend
    python scripts/compare_event_identification.py \\
        --fixture path/to/events.json \\
        --dry-run \\
        --output-dir /tmp/identification-compare

The fixture is a JSON object with an ``events`` list. Each event may include
``id``, ``timestamp``, ``detection_start``, ``detection_end``, ``peak``,
``frame_count``, ``subject_crop_count``, ``offset_ms``, and ``box``
(``x``, ``y``, ``width``, ``height``). Timing is not stored on events, so a
database listing can only compare the fallback window plus a stored box.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
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

# Statements a comparison run is allowed to send. Everything else fails closed.
_READ_ONLY_HEADS = {"SELECT", "WITH", "PRAGMA", "EXPLAIN", "BEGIN", "COMMIT", "ROLLBACK"}
_EVENT_ID = re.compile(r"^[0-9a-fA-F-]{8,40}$")

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
    return SubjectBox(x, y, width, height, source="fixture", normalized=max(x, y, width, height) <= 1.0)


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
    """Smart-detect window when the fixture has timing, otherwise the old window."""
    timing = DetectionTiming(
        start=_parse_dt(event.get("detection_start")),
        end=_parse_dt(event.get("detection_end")),
        peak=_parse_dt(event.get("peak")),
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


def _ai_fields(described: Optional[dict]) -> Dict[str, Any]:
    described = described or {}
    return {
        "description": described.get("description"),
        "identification": described.get("identification"),
        "provider": described.get("provider"),
        "latency_ms": described.get("latency_ms"),
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
            "old": {**old, **old_ai},
            "new": {**new, **new_ai},
        })
    return {
        "dry_run": dry_run,
        "ai_calls": ai_calls,
        "note": (
            "Dry run: frames and prompts only. No vision request was sent."
            if dry_run
            else "Descriptions are filled only when a describer is provided. The database is not updated."
        ),
        "events": rows,
    }


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
            "tokens_estimate",
            "cost_estimate_usd",
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


def load_events_from_db(database_url: str, *, limit: int, event_ids: Optional[Sequence[str]]) -> List[dict]:
    """SELECT recent events. Timing columns are not stored, so windows fall back."""
    from sqlalchemy import bindparam, text

    if event_ids:
        for event_id in event_ids:
            if not _EVENT_ID.fullmatch(event_id):
                raise SystemExit("Refused an event id that is not a UUID")
    engine = open_read_only_engine(database_url)
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            info = conn.execute(text("PRAGMA table_info(events)")).fetchall()
            columns = {row[1] for row in info}
        else:
            info = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'events'"
                )
            ).fetchall()
            columns = {row[0] for row in info}
        wanted = ["id", "timestamp", "bounding_boxes", "smart_detection_type"]
        selected = [name for name in wanted if name in columns]
        if "id" not in selected:
            raise SystemExit("events.id is not readable")
        sql_cols = ", ".join(selected)
        if event_ids:
            stmt = text(
                f"SELECT {sql_cols} FROM events WHERE id IN :ids"
            ).bindparams(bindparam("ids", expanding=True))
            rows = conn.execute(stmt, {"ids": list(event_ids)}).mappings().all()
        else:
            stmt = text(
                f"SELECT {sql_cols} FROM events ORDER BY timestamp DESC LIMIT :limit"
            )
            rows = conn.execute(stmt, {"limit": int(limit)}).mappings().all()
    events = []
    for row in rows:
        box = None
        raw_boxes = row.get("bounding_boxes") if "bounding_boxes" in row else None
        if isinstance(raw_boxes, str):
            try:
                parsed = json.loads(raw_boxes)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                box = {
                    "x": parsed[0].get("x"),
                    "y": parsed[0].get("y"),
                    "width": parsed[0].get("width"),
                    "height": parsed[0].get("height"),
                }
        timestamp = row.get("timestamp") if "timestamp" in row else None
        events.append({
            "id": row["id"],
            "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp,
            "box": box,
            "smart_detection_type": row.get("smart_detection_type") if "smart_detection_type" in row else None,
        })
    return events


def write_report(report: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "comparison.json").write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    (output_dir / "comparison.md").write_text(render_markdown(report), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare old and new identification inputs")
    parser.add_argument("--fixture", type=Path, help="JSON fixture. Does not open the database.")
    parser.add_argument("--dry-run", action="store_true", help="Plan frames and prompts. Make no AI calls.")
    parser.add_argument("--event-ids", help="Comma-separated event ids (read-only SELECT)")
    parser.add_argument("--limit", type=int, default=10, help="Recent events when no ids are given")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--frame-count", type=int, default=10)
    parser.add_argument("--subject-crop-count", type=int, default=1)
    parser.add_argument("--offset-ms", type=int, default=2000)
    args = parser.parse_args(argv)

    if args.fixture:
        events = load_fixture(args.fixture)
    else:
        database_url = args.database_url
        if not database_url:
            raise SystemExit("Pass --fixture or --database-url. This script does not guess a database.")
        ids = [part.strip() for part in args.event_ids.split(",")] if args.event_ids else None
        events = load_events_from_db(database_url, limit=args.limit, event_ids=ids)

    # Dry-run never receives a describer, so no provider code runs.
    report = build_report(
        events,
        dry_run=args.dry_run,
        frame_count=args.frame_count,
        subject_crop_count=args.subject_crop_count,
        offset_ms=args.offset_ms,
        describe=None,
    )
    write_report(report, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
