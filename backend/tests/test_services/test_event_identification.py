"""Event-aligned sampling, subject crops, Gemini native video, and identification parsing."""

import importlib.util
import inspect
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.services.event_sampling import (
    DetectionTiming,
    SubjectBox,
    allocate_subject_crops,
    coerce_protect_coord,
    crop_jpeg,
    legacy_uniform_offsets,
    plan_clip_window,
    plan_frame_offsets,
)
from app.services.identification import (
    IDENTIFICATION_MARKER,
    empty_identification,
    ensure_identification_prompt,
    parse_identification,
)
from app.services.prompt_templates import MULTI_FRAME_SYSTEM_PROMPT


ANCHOR = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _jpeg(width: int, height: int, color=(10, 20, 30)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_missing_timing_uses_fixed_window_and_uniform_offsets():
    plan = plan_clip_window(DetectionTiming(anchor=ANCHOR))
    assert plan.source == "fallback"
    assert plan.duration_s == pytest.approx(30.0)
    assert plan.start == ANCHOR - timedelta(seconds=15)
    assert plan.end == ANCHOR + timedelta(seconds=15)

    samples = plan_frame_offsets(30.0, 10, None, None, None, offset_ms=2000)
    legacy = legacy_uniform_offsets(30.0, 10, 2000)
    assert [s.offset_seconds for s in samples] == [s.offset_seconds for s in legacy]
    assert samples[0].offset_seconds == pytest.approx(2.0)
    assert samples[-1].offset_seconds == pytest.approx(30.0)


def test_smart_detect_window_is_dense_near_the_detection():
    start = ANCHOR
    end = ANCHOR + timedelta(seconds=4)
    peak = ANCHOR + timedelta(seconds=2)
    plan = plan_clip_window(DetectionTiming(start=start, end=end, peak=peak, anchor=ANCHOR))
    assert plan.source == "smart_detect"
    assert plan.duration_s <= 30.0
    assert plan.peak_s is not None

    samples = plan_frame_offsets(
        plan.duration_s,
        10,
        plan.detection_start_s,
        plan.detection_end_s,
        plan.peak_s,
        offset_ms=0,
    )
    inside = [
        sample for sample in samples
        if plan.detection_start_s - 0.05 <= sample.offset_seconds <= plan.detection_end_s + 0.05
    ]
    assert len(inside) >= 7
    assert any(sample.kind == "peak" and sample.offset_seconds == pytest.approx(plan.peak_s) for sample in samples)
    # The old even grid on a 30s clip is not this window.
    assert plan.duration_s < 30.0


def test_end_before_start_does_not_invert_the_window():
    plan = plan_clip_window(DetectionTiming(
        start=ANCHOR,
        end=ANCHOR - timedelta(seconds=5),
        anchor=ANCHOR,
    ))
    assert plan.end > plan.start
    assert plan.duration_s >= 6.0


def test_start_only_uses_a_minimum_window():
    plan = plan_clip_window(DetectionTiming(start=ANCHOR, anchor=ANCHOR))
    assert plan.source == "smart_detect"
    assert plan.duration_s >= 6.0
    assert plan.end > plan.start


def test_allocate_subject_crops_keeps_the_budget_and_the_peak_frame():
    samples = plan_frame_offsets(20.0, 10, 8.0, 12.0, 10.0, offset_ms=0)
    kept, crop_times = allocate_subject_crops(samples, 1, 10.0)
    assert len(kept) + len(crop_times) == len(samples)
    assert any(sample.kind == "peak" for sample in kept)
    assert crop_times

    untouched, no_crops = allocate_subject_crops(samples, 0, 10.0)
    assert len(untouched) == len(samples)
    assert no_crops == []


def test_crop_jpeg_uses_a_normalized_box_and_rejects_empty_boxes():
    raw = _jpeg(200, 160)
    box = SubjectBox(0.25, 0.25, 0.4, 0.4, source="protect", normalized=True)
    cropped = crop_jpeg(raw, box)
    assert cropped
    image = Image.open(io.BytesIO(cropped))
    assert image.width < 200
    assert image.height < 160
    assert image.width >= 32

    assert crop_jpeg(b"", box) is None
    assert crop_jpeg(raw, SubjectBox(0, 0, 0, 1, source="protect")) is None
    assert coerce_protect_coord([0, 0, 0, 10]) is None


def test_coerce_protect_coord_thousandths_and_pixels():
    thousandths = coerce_protect_coord([100, 200, 300, 400], label="person")
    assert thousandths is not None
    assert thousandths.normalized is True
    assert thousandths.x == pytest.approx(0.1)
    assert thousandths.width == pytest.approx(0.3)

    pixels = coerce_protect_coord([40, 50, 1200, 400])
    assert pixels is not None
    assert pixels.normalized is False
    raw = _jpeg(200, 200)
    cropped = crop_jpeg(raw, SubjectBox(20, 30, 80, 90, source="stored", normalized=False))
    assert cropped
    image = Image.open(io.BytesIO(cropped))
    assert image.width < 200


def test_parse_identification_unknown_and_cannot_tell():
    parsed = parse_identification(json.dumps({
        "description": "A shape is at the gate.",
        "object_type": "person",
        "count": 1,
        "identity": "unknown",
        "action": "standing",
        "direction": "cannot_tell",
        "package_or_carrier": "UPS truck",
    }))
    assert parsed["object_type"] == "person"
    assert parsed["count"] == 1
    assert parsed["identity"] == "unknown"
    assert parsed["direction"] == "cannot_tell"
    assert parsed["package_or_carrier"] == "ups"

    cannot = parse_identification(json.dumps({
        "description": "Too dark.",
        "object_type": "cannot_tell",
        "count": "cannot_tell",
        "identity": "cannot_tell",
        "action": "cannot_tell",
        "direction": "cannot_tell",
        "package_or_carrier": "cannot_tell",
    }))
    assert cannot["object_type"] == "unknown"
    assert cannot["count"] is None
    assert cannot["identity"] == "cannot_tell"
    assert cannot["package_or_carrier"] == "cannot_tell"

    prose = parse_identification("A person walked past, but this is not JSON.")
    assert prose == empty_identification()

    invalid_type = parse_identification('{"object_type": "bicycle", "count": 2}')
    assert invalid_type["object_type"] == "unknown"
    assert invalid_type["count"] == 2


def test_identification_prompt_appends_once_and_multi_frame_still_formats():
    once = ensure_identification_prompt("Describe the scene.")
    twice = ensure_identification_prompt(once)
    assert once == twice
    assert IDENTIFICATION_MARKER in once
    formatted = MULTI_FRAME_SYSTEM_PROMPT.format(num_frames=4)
    assert "4" in formatted
    assert IDENTIFICATION_MARKER in formatted


def test_extract_frames_rejects_the_old_gemini_arguments():
    """The native-video bug called extract_frames(video_path=, max_frames=)."""
    from app.services.frame_extractor import FrameExtractor

    signature = inspect.signature(FrameExtractor.extract_frames)
    with pytest.raises(TypeError):
        signature.bind(None, video_path="clip.mp4", max_frames=5)


def _gemini_provider():
    with patch("google.generativeai.configure"), patch("google.generativeai.GenerativeModel") as model_cls:
        model = MagicMock()
        model_cls.return_value = model
        with patch("app.services.ai_providers.model_resolver.resolve_model", return_value="gemini-test"):
            from app.services.ai_providers.gemini_provider import GeminiProvider
            provider = GeminiProvider("test-key")
        return provider, model


@pytest.mark.asyncio
async def test_describe_video_sends_mp4_bytes_and_does_not_extract_frames(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.frame_extractor.get_frame_extractor", lambda: (_ for _ in ()).throw(AssertionError("extractor")))
    provider, model = _gemini_provider()
    response = MagicMock()
    response.text = json.dumps({
        "description": "A person walks toward the camera.",
        "object_type": "person",
        "count": 1,
        "identity": "unknown",
        "action": "walking",
        "direction": "toward camera",
        "package_or_carrier": "none",
    })
    response.usage_metadata = None
    model.generate_content_async = AsyncMock(return_value=response)

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")
    result = await provider.describe_video(clip, "Gate", "2026-01-01T00:00:00Z", ["motion"])

    parts = model.generate_content_async.await_args.args[0]
    assert parts[1]["mime_type"] == "video/mp4"
    assert parts[1]["data"] == clip.read_bytes()
    assert result.success is True
    assert result.description == "A person walks toward the camera."
    assert result.identification["identity"] == "unknown"
    assert result.identification["object_type"] == "person"


@pytest.mark.asyncio
async def test_describe_video_logs_a_warning_instead_of_hiding_the_failure(tmp_path, caplog):
    provider, model = _gemini_provider()
    model.generate_content_async = AsyncMock(side_effect=RuntimeError("provider down"))
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"not-a-real-mp4")

    with caplog.at_level("WARNING"):
        result = await provider.describe_video(clip, "Gate", "2026-01-01T00:00:00Z", [])

    assert result.success is False
    assert "RuntimeError" in (result.error or "")
    assert "gemini_native_video_failed" in caplog.text or any(
        getattr(record, "event_type", None) == "gemini_native_video_failed" or "gemini_native_video_failed" in str(getattr(record, "extra", {}))
        or record.getMessage()
        for record in caplog.records
    )
    assert any("Gemini native video failed" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_describe_video_uses_files_api_above_the_inline_limit(tmp_path, monkeypatch):
    import app.services.ai_providers.gemini_provider as gemini_mod

    monkeypatch.setattr(gemini_mod, "GEMINI_INLINE_VIDEO_BYTES", 1)
    provider, model = _gemini_provider()
    response = MagicMock()
    response.text = '{"description": "A vehicle passes.", "object_type": "vehicle", "count": 1, "identity": "unknown", "action": "passing", "direction": "left", "package_or_carrier": "none"}'
    response.usage_metadata = None
    model.generate_content_async = AsyncMock(return_value=response)
    uploaded = MagicMock()
    uploaded.name = "files/abc"
    uploaded.state.name = "ACTIVE"

    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"0123456789")
    with patch("google.generativeai.upload_file", return_value=uploaded) as upload:
        result = await provider.describe_video(clip, "Drive", "2026-01-01T00:00:00Z", [])

    upload.assert_called_once()
    assert result.success is True
    sent = model.generate_content_async.await_args.args[0]
    assert sent[1] is uploaded


def _load_compare_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "compare_event_identification.py"
    spec = importlib.util.spec_from_file_location("compare_event_identification", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compare_script_dry_run_writes_json_and_markdown(tmp_path):
    module = _load_compare_script()
    fixture = tmp_path / "events.json"
    fixture.write_text(json.dumps({
        "events": [{
            "id": "evt-timed",
            "timestamp": "2026-01-01T12:00:00+00:00",
            "detection_start": "2026-01-01T12:00:00+00:00",
            "detection_end": "2026-01-01T12:00:04+00:00",
            "peak": "2026-01-01T12:00:02+00:00",
            "box": {"x": 0.4, "y": 0.3, "width": 0.2, "height": 0.4},
            "frame_count": 10,
            "subject_crop_count": 1,
        }]
    }), encoding="utf-8")
    output = tmp_path / "out"
    called = {"n": 0}

    def describer(event, plan, label):
        called["n"] += 1
        raise AssertionError("dry-run must not describe")

    events = module.load_fixture(fixture)
    report = module.build_report(events, dry_run=True, describe=describer)
    module.write_report(report, output)

    assert called["n"] == 0
    assert report["ai_calls"] == 0
    payload = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
    markdown = (output / "comparison.md").read_text(encoding="utf-8")
    row = payload["events"][0]
    assert row["new"]["subject_crop_used"] is True
    assert row["old"]["subject_crop_used"] is False
    assert row["new"]["offsets_s"] != row["old"]["offsets_s"]
    assert row["new"]["image_count"] == row["old"]["image_count"]
    assert row["new"]["description"] is None
    assert "subject_crop_used" in markdown
    assert IDENTIFICATION_MARKER in row["new"]["prompt"]
    assert IDENTIFICATION_MARKER not in row["old"]["prompt"]

    code = module.main(["--fixture", str(fixture), "--dry-run", "--output-dir", str(tmp_path / "cli")])
    assert code == 0
    cli_report = json.loads((tmp_path / "cli" / "comparison.json").read_text(encoding="utf-8"))
    assert cli_report["dry_run"] is True
    assert cli_report["ai_calls"] == 0


def test_compare_describer_fills_fields_without_a_database(tmp_path):
    module = _load_compare_script()
    events = [{
        "id": "evt-1",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "box": {"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.3},
    }]

    def describer(event, plan, label):
        return {
            "description": f"{label} saw a person",
            "identification": {"object_type": "person", "identity": "unknown"},
            "provider": "fake",
            "latency_ms": 12,
        }

    report = module.build_report(events, dry_run=False, describe=describer)
    assert report["ai_calls"] == 2
    assert report["events"][0]["new"]["provider"] == "fake"
    assert report["events"][0]["new"]["identification"]["identity"] == "unknown"
    assert report["events"][0]["old"]["latency_ms"] == 12


def test_compare_database_access_is_read_only(tmp_path):
    module = _load_compare_script()
    from sqlalchemy import create_engine, text

    db_path = tmp_path / "events.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE events (id TEXT PRIMARY KEY, timestamp TEXT, "
            "bounding_boxes TEXT, smart_detection_type TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO events (id, timestamp, bounding_boxes, smart_detection_type) "
            "VALUES ('abcdef12-3456-7890-abcd-ef1234567890', '2026-01-01T00:00:00', NULL, 'person')"
        ))

    guarded = module.open_read_only_engine(url)
    with pytest.raises(RuntimeError):
        with guarded.connect() as conn:
            conn.execute(text("DELETE FROM events"))

    loaded = module.load_events_from_db(
        url,
        limit=5,
        event_ids=["abcdef12-3456-7890-abcd-ef1234567890"],
    )
    assert len(loaded) == 1
    assert loaded[0]["id"].startswith("abcdef12")

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM events")).scalar()
    assert count == 1

    with pytest.raises(RuntimeError):
        module.assert_read_only("INSERT INTO events (id) VALUES ('x')")
    module.assert_read_only("SELECT id FROM events")
    with pytest.raises(SystemExit):
        module.load_events_from_db(url, limit=1, event_ids=["not an id"])
