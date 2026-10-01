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
    FrameSample,
    SubjectBox,
    _enforce_min_spacing,
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


def test_sampler_drops_frames_closer_than_half_a_second():
    kept = _enforce_min_spacing([
        FrameSample(20.490, "peak"),
        FrameSample(20.491, "dense"),
        FrameSample(0.0, "edge"),
        FrameSample(30.0, "edge"),
    ])
    offsets = [sample.offset_seconds for sample in kept]
    assert offsets == pytest.approx([0.0, 20.490, 30.0])
    assert [sample.kind for sample in kept][1] == "peak"

    samples = plan_frame_offsets(30.0, 10, 5.0, 25.0, 15.0, offset_ms=0)
    spaced = [sample.offset_seconds for sample in samples]
    assert len(samples) <= 10
    assert all(right - left >= 0.5 - 1e-6 for left, right in zip(spaced, spaced[1:]))
    assert any(sample.kind == "peak" and sample.offset_seconds == pytest.approx(15.0) for sample in samples)


def test_long_detection_is_not_cut_to_thirty_seconds():
    plan = plan_clip_window(DetectionTiming(
        start=ANCHOR,
        end=ANCHOR + timedelta(seconds=27),
        peak=ANCHOR + timedelta(seconds=10),
        anchor=ANCHOR,
    ))
    assert plan.source == "smart_detect"
    assert plan.duration_s == pytest.approx(33.0)
    assert plan.duration_s <= 45.0
    assert plan.detection_start_s == pytest.approx(3.0)
    assert plan.detection_end_s == pytest.approx(30.0)
    assert plan.peak_s == pytest.approx(13.0)


def test_over_cap_detection_keeps_the_peak_and_both_ends():
    plan = plan_clip_window(DetectionTiming(
        start=ANCHOR,
        end=ANCHOR + timedelta(seconds=64),
        peak=ANCHOR + timedelta(seconds=40),
        anchor=ANCHOR,
    ))
    assert plan.duration_s == pytest.approx(45.0)
    assert 0.0 < plan.peak_s < plan.duration_s
    samples = plan_frame_offsets(
        plan.duration_s,
        10,
        plan.detection_start_s,
        plan.detection_end_s,
        plan.peak_s,
        offset_ms=0,
    )
    assert len(samples) <= 10
    assert any(
        sample.kind == "peak" and sample.offset_seconds == pytest.approx(plan.peak_s)
        for sample in samples
    )
    assert samples[0].offset_seconds == pytest.approx(0.0, abs=0.05)
    assert samples[-1].offset_seconds == pytest.approx(plan.duration_s, abs=0.05)
    offsets = [sample.offset_seconds for sample in samples]
    assert all(right - left >= 0.5 - 1e-6 for left, right in zip(offsets, offsets[1:]))


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
    raw = _jpeg(800, 600)
    box = SubjectBox(0.2, 0.2, 0.4, 0.5, source="protect", normalized=True)
    cropped = crop_jpeg(raw, box)
    assert cropped
    image = Image.open(io.BytesIO(cropped))
    assert image.width < 800
    assert image.height < 600
    assert min(image.width, image.height) >= 160

    assert crop_jpeg(b"", box) is None
    assert crop_jpeg(raw, SubjectBox(0, 0, 0, 1, source="protect")) is None
    assert coerce_protect_coord([0, 0, 0, 10]) is None


def test_crop_jpeg_skips_a_tiny_box_without_upscaling():
    """A ~50x95 leaf in a 2688x1512 frame is not zoomed into an animal."""
    raw = _jpeg(2688, 1512)
    box = SubjectBox(0.42, 0.55, 50 / 2688, 95 / 1512, source="protect", normalized=True)
    assert crop_jpeg(raw, box) is None

    wide_but_short = SubjectBox(0.2, 0.4, 0.4, 90 / 1512, source="protect", normalized=True)
    assert wide_but_short.width * wide_but_short.height > 0.02
    assert crop_jpeg(raw, wide_but_short) is None


def test_coerce_protect_coord_thousandths_and_pixels():
    thousandths = coerce_protect_coord([100, 200, 300, 400], label="person")
    assert thousandths is not None
    assert thousandths.normalized is True
    assert thousandths.x == pytest.approx(0.1)
    assert thousandths.width == pytest.approx(0.3)

    pixels = coerce_protect_coord([40, 50, 1200, 400])
    assert pixels is not None
    assert pixels.normalized is False
    raw = _jpeg(1000, 800)
    cropped = crop_jpeg(raw, SubjectBox(100, 80, 400, 320, source="stored", normalized=False))
    assert cropped
    image = Image.open(io.BytesIO(cropped))
    assert image.width < 1000
    assert min(image.size) >= 160


def test_dumps_identification_skips_non_dicts():
    from app.services.identification import dumps_identification

    stored = dumps_identification({"object_type": "person", "identity": "unknown"})
    assert json.loads(stored)["object_type"] == "person"
    assert dumps_identification(None) is None
    assert dumps_identification("not-json-object") is None

    class AlwaysTrue:
        def __bool__(self):
            return True

    assert dumps_identification(AlwaysTrue()) is None


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


def test_parse_identification_none_is_a_false_alarm():
    from app.services.ai_types import AIResult
    from app.services.identification import apply_identification

    parsed = parse_identification(json.dumps({
        "description": "Nothing of interest is in the frame.",
        "object_type": "none",
        "count": 1,
        "identity": "a bird",
        "action": "a bird flies into view",
        "direction": "left",
        "package_or_carrier": "package",
    }))
    assert parsed["object_type"] == "none"
    assert parsed["count"] == 0
    assert parsed["identity"] == "unknown"
    assert parsed["action"] == "cannot_tell"
    assert parsed["direction"] == "cannot_tell"
    assert parsed["package_or_carrier"] == "none"

    alias = parse_identification('{"object_type": "false_alarm", "description": "Static leaf."}')
    assert alias["object_type"] == "none"

    result = AIResult(
        description="",
        confidence=0,
        objects_detected=["unknown"],
        provider="test",
        tokens_used=0,
        response_time_ms=0,
        cost_estimate=0.0,
        success=True,
    )
    apply_identification(result, json.dumps({
        "description": "Nothing is there.",
        "object_type": "none",
    }))
    assert result.identification["object_type"] == "none"
    assert "none" not in result.objects_detected
    assert "animal" not in result.objects_detected


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        (
            "A man walks to the house holding a white sheet of paper or a small book.",
            "none",
        ),
        (
            "A person at the door holds a phone, a cup, and an ordinary bag of mail.",
            "none",
        ),
        (
            "Someone stands by the mailbox with a sheet of paper.",
            "none",
        ),
        (
            "A person walks to the front door, sets a cardboard box on the step, and leaves.",
            "package",
        ),
        (
            "A padded mailer is lying at the door.",
            "package",
        ),
        (
            "Someone drops off a delivery bag and walks away.",
            "package",
        ),
        (
            "A parcel is picked up from the porch.",
            "package",
        ),
    ],
)
def test_package_label_follows_the_description(description, expected):
    """Paper is not a package. A box, mailer, delivery bag, or parcel is."""
    parsed = parse_identification(json.dumps({
        "description": description,
        "object_type": "person",
        "count": 1,
        "identity": "unknown",
        "action": "walking",
        "direction": "toward camera",
        "package_or_carrier": "package",
    }))
    assert parsed["package_or_carrier"] == expected
    assert parsed["object_type"] == "person"


def test_package_check_does_not_rewrite_carriers_or_stored_rows():
    from app.services.identification import loads_identification

    unsure = parse_identification(json.dumps({
        "description": "A man holds a white sheet of paper.",
        "object_type": "person",
        "package_or_carrier": "cannot_tell",
    }))
    assert unsure["package_or_carrier"] == "cannot_tell"

    carrier = parse_identification(json.dumps({
        "description": "A driver in a brown uniform sets a box on the step.",
        "object_type": "person",
        "package_or_carrier": "UPS",
    }))
    assert carrier["package_or_carrier"] == "ups"

    # A fresh reply that says package and never describes one is downgraded.
    bare = parse_identification('{"object_type": "person", "package_or_carrier": "package"}')
    assert bare["package_or_carrier"] == "none"

    # Reloading a stored row has no description, so an accepted package stays.
    loaded = loads_identification('{"object_type": "person", "package_or_carrier": "package"}')
    assert loaded["package_or_carrier"] == "package"


def test_identification_prompt_defines_a_package_and_a_carrier():
    from app.services.identification import DESCRIPTION_MAX_OUTPUT_TOKENS

    prompt = ensure_identification_prompt("Describe the scene.")
    assert "A package is a parcel, box, padded mailer, or delivery bag" in prompt
    assert "carried, dropped off or picked up, or lying at the door" in prompt
    assert "Ordinary handheld items are not packages" in prompt
    for item in ("paper", "mail", "a phone", "an ordinary bag", "a cup", "a small book"):
        assert item in prompt
    assert "uniform" in prompt
    assert "branded vehicle" in prompt
    assert "scanner" in prompt
    assert 'Do not say "package"' in prompt
    # The rest of the #632 contract stays put.
    assert "3 to 6 sentences" in prompt
    assert "licence plate" in prompt
    assert "license plate" in prompt
    assert "A camera label, a detector" in prompt
    assert 'set object_type to\n"none"' in prompt
    assert DESCRIPTION_MAX_OUTPUT_TOKENS == 1024


def test_identification_prompt_appends_once_and_multi_frame_still_formats():
    once = ensure_identification_prompt("Describe the scene.")
    twice = ensure_identification_prompt(once)
    assert once == twice
    assert IDENTIFICATION_MARKER in once
    assert "3 to 6 sentences" in once
    assert "licence plate" in once
    assert "no person, vehicle, animal, or package is visible" in once
    formatted = MULTI_FRAME_SYSTEM_PROMPT.format(num_frames=4)
    assert "4" in formatted
    assert IDENTIFICATION_MARKER in formatted
    assert "1-2 concise" not in formatted


def test_description_output_budget_covers_a_paragraph_on_every_provider():
    import inspect

    from app.services.identification import DESCRIPTION_MAX_OUTPUT_TOKENS
    from app.services.ai_providers.claude_provider import ClaudeProvider
    from app.services.ai_providers.gemini_provider import GeminiProvider
    from app.services.ai_providers.grok_provider import GrokProvider
    from app.services.ai_providers.openai_provider import OpenAIProvider
    from app.services.litellm_provider import LiteLLMProvider

    assert DESCRIPTION_MAX_OUTPUT_TOKENS >= 1024
    methods = [
        OpenAIProvider.generate_description,
        OpenAIProvider.generate_multi_image_description,
        ClaudeProvider.generate_description,
        ClaudeProvider.generate_multi_image_description,
        GrokProvider.generate_description,
        GrokProvider.generate_multi_image_description,
        GeminiProvider.generate_description,
        GeminiProvider.generate_multi_image_description,
        GeminiProvider.describe_video,
        LiteLLMProvider.describe_images,
    ]
    for method in methods:
        assert "DESCRIPTION_MAX_OUTPUT_TOKENS" in inspect.getsource(method)


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
    assert "3 to 6 sentences" in row["new"]["prompt"]
    assert IDENTIFICATION_MARKER not in row["old"]["prompt"]

    code = module.main(["--fixture", str(fixture), "--dry-run", "--output-dir", str(tmp_path / "cli")])
    assert code == 0
    cli_report = json.loads((tmp_path / "cli" / "comparison.json").read_text(encoding="utf-8"))
    assert cli_report["dry_run"] is True
    assert cli_report["ai_calls"] == 0

    default_code = module.main(["--fixture", str(fixture), "--output-dir", str(tmp_path / "default")])
    assert default_code == 0
    default_report = json.loads((tmp_path / "default" / "comparison.json").read_text(encoding="utf-8"))
    assert default_report["dry_run"] is True
    assert default_report["ai_calls"] == 0


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
    assert report["events"][0]["old"]["identification"] is None
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


def test_event_detection_columns_are_nullable():
    from app.models.event import Event

    for name in ("detection_start", "detection_end", "detection_peak", "subject_box"):
        assert Event.__table__.c[name].nullable is True


def test_detection_column_values_store_timing_and_box():
    from app.services.protect_detection_hints import DetectionHints, detection_column_values

    assert detection_column_values(DetectionHints()) == {}
    assert detection_column_values(None) == {}
    box = SubjectBox(0.1, 0.2, 0.3, 0.4, source="protect", label="person", normalized=True)
    hints = DetectionHints(
        start=ANCHOR,
        end=ANCHOR + timedelta(seconds=4),
        peak=ANCHOR + timedelta(seconds=2),
        boxes=[box],
    )
    values = detection_column_values(hints)
    assert values["detection_start"] == ANCHOR
    assert values["detection_end"] == ANCHOR + timedelta(seconds=4)
    assert values["detection_peak"] == ANCHOR + timedelta(seconds=2)
    parsed = json.loads(values["subject_box"])
    assert parsed["width"] == 0.3
    assert parsed["label"] == "person"
    assert parsed["normalized"] is True


def test_detection_fields_drop_a_malformed_box():
    from types import SimpleNamespace
    from app.api.v1.events import _event_detection_fields, _reanalyze_clip_window

    event = SimpleNamespace(
        timestamp=ANCHOR,
        detection_start=None,
        detection_end=None,
        detection_peak=None,
        subject_box="{not-json",
    )
    assert _event_detection_fields(event)["subject_box"] is None

    start, end, clip = _reanalyze_clip_window(event)
    assert clip is None
    assert start == ANCHOR - timedelta(seconds=5)
    assert end == ANCHOR + timedelta(seconds=5)

    timed = SimpleNamespace(
        timestamp=ANCHOR,
        detection_start=ANCHOR,
        detection_end=ANCHOR + timedelta(seconds=4),
        detection_peak=ANCHOR + timedelta(seconds=2),
        subject_box=json.dumps({"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}),
    )
    start, end, clip = _reanalyze_clip_window(timed)
    assert clip is not None
    assert clip.source == "smart_detect"
    assert start < ANCHOR
    assert end > ANCHOR + timedelta(seconds=4)
    assert _event_detection_fields(timed)["subject_box"]["width"] == 0.3


@pytest.mark.asyncio
async def test_persist_protect_event_stores_detection_columns():
    from types import SimpleNamespace
    from app.services.protect_event_storage_service import ProtectEventStorageService

    service = ProtectEventStorageService()
    db = MagicMock()
    camera = SimpleNamespace(id="cam-1", name="Gate")
    snap = SimpleNamespace(timestamp=ANCHOR, thumbnail_path=None)
    event = await service.persist_protect_event(
        db=db,
        camera=camera,
        snapshot_result=snap,
        ai_result=None,
        protect_event_id="protect-1",
        event_type="person",
        detection_start=ANCHOR,
        detection_end=ANCHOR + timedelta(seconds=4),
        detection_peak=ANCHOR + timedelta(seconds=2),
        subject_box='{"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4}',
    )
    assert event.detection_start == ANCHOR
    assert event.detection_peak == ANCHOR + timedelta(seconds=2)
    assert event.subject_box.startswith("{")
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_load_events_prefers_subject_box_and_omits_controller_secrets(tmp_path):
    module = _load_compare_script()
    from sqlalchemy import create_engine, text

    url = f"sqlite:///{tmp_path / 'events.db'}"
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE events (id TEXT PRIMARY KEY, timestamp TEXT, bounding_boxes TEXT, "
            "smart_detection_type TEXT, protect_event_id TEXT, camera_id TEXT, video_path TEXT, "
            "detection_start TEXT, detection_end TEXT, detection_peak TEXT, subject_box TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE cameras (id TEXT PRIMARY KEY, protect_controller_id TEXT, "
            "protect_camera_id TEXT, host TEXT, password TEXT)"
        ))
        conn.execute(
            text(
                "INSERT INTO cameras (id, protect_controller_id, protect_camera_id, host, password) "
                "VALUES (:id, :controller, :camera, :host, :password)"
            ),
            {
                "id": "cam-1",
                "controller": "abcdef12-3456-7890-abcd-ef1234567890",
                "camera": "pcam",
                "host": "controller.invalid",
                "password": "fixture-password",
            },
        )
        conn.execute(
            text(
                "INSERT INTO events (id, timestamp, bounding_boxes, smart_detection_type, "
                "protect_event_id, camera_id, video_path, detection_start, detection_end, "
                "detection_peak, subject_box) VALUES (:id, :timestamp, :boxes, :kind, "
                ":protect_id, :camera_id, NULL, :start, :end, :peak, :box)"
            ),
            {
                "id": "abcdef12-3456-7890-abcd-ef1234567890",
                "timestamp": "2026-01-01T12:00:00",
                "boxes": '[{"x": 9, "y": 9, "width": 9, "height": 9}]',
                "kind": "person",
                "protect_id": "protect-1",
                "camera_id": "cam-1",
                "start": "2026-01-01T12:00:00+00:00",
                "end": "2026-01-01T12:00:04+00:00",
                "peak": "2026-01-01T12:00:02+00:00",
                "box": '{"x": 0.2, "y": 0.2, "width": 0.3, "height": 0.4}',
            },
        )

    loaded = module.load_events_from_db(
        url,
        limit=5,
        event_ids=["abcdef12-3456-7890-abcd-ef1234567890"],
    )
    assert loaded[0]["box"]["x"] == 0.2
    assert loaded[0]["protect_event_id"] == "protect-1"
    assert loaded[0]["protect_controller_id"].startswith("abcdef12")
    assert "host" not in loaded[0]
    assert "password" not in loaded[0]
    blob = json.dumps(loaded)
    assert "controller.invalid" not in blob
    assert "fixture-password" not in blob
    report = module.build_report(loaded, dry_run=True)
    assert report["events"][0]["new"]["window_source"] == "smart_detect"


@pytest.mark.asyncio
async def test_fetch_protect_timing_maps_hints_without_connect(caplog):
    module = _load_compare_script()
    from app.services.protect_service import ProtectService

    start = ANCHOR
    end = ANCHOR + timedelta(seconds=4)
    peak = ANCHOR + timedelta(seconds=2)
    from types import SimpleNamespace

    fake_event = SimpleNamespace(
        start=start,
        end=end,
        metadata=SimpleNamespace(detected_thumbnails=[
            SimpleNamespace(
                confidence=90,
                clock_best_wall=peak,
                coord=[400, 300, 200, 400],
                type="person",
            )
        ]),
    )

    closed = {"n": 0}

    class FakeClient:
        async def get_event(self, event_id):
            assert event_id == "protect-evt-1"
            return fake_event

        async def close_session(self):
            closed["n"] += 1

    events = [{
        "id": "abcdef12-3456-7890-abcd-ef1234567890",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "protect_event_id": "protect-evt-1",
        "protect_controller_id": "abcdef12-3456-7890-abcd-ef1234567890",
    }]

    async def open_client(controller_id):
        assert controller_id.startswith("abcdef12")
        return FakeClient()

    with patch.object(ProtectService, "connect", side_effect=AssertionError("connect")):
        with caplog.at_level("WARNING"):
            await module.enrich_events_with_protect(events, open_client)

    assert closed["n"] == 1
    assert events[0]["timing_fetch"] == "ok"
    report = module.build_report(events, dry_run=True)
    assert report["events"][0]["new"]["window_source"] == "smart_detect"
    blob = json.dumps(report)
    assert "controller.invalid" not in blob
    assert "fixture-password" not in blob


@pytest.mark.asyncio
async def test_protect_lookup_failure_does_not_record_secrets(caplog, monkeypatch):
    module = _load_compare_script()
    import sys
    import types
    from app.services.protect_service import ProtectService

    created = {}

    class FakeApi:
        def __init__(self, **kwargs):
            created.update(kwargs)

        async def update(self):
            created["updated"] = True

        async def close_session(self):
            created["closed"] = True

    fake_mod = types.ModuleType("uiprotect")
    fake_mod.ProtectApiClient = FakeApi
    monkeypatch.setitem(sys.modules, "uiprotect", fake_mod)
    monkeypatch.setattr(ProtectService, "connect", AsyncMock(side_effect=AssertionError("connect")))

    with caplog.at_level("WARNING"):
        client = await module.open_readonly_protect_client({
            "host": "controller.invalid",
            "port": 443,
            "username": "fixture-user",
            "password": "fixture-password",
            "verify_ssl": False,
        })
    assert client is not None
    assert created["updated"] is True
    assert created["host"] == "controller.invalid"
    assert ProtectService.connect.await_count == 0

    class Boom(Exception):
        pass

    class BadClient:
        async def get_event(self, event_id):
            raise Boom("controller.invalid fixture-password")

        async def close_session(self):
            created["bad_closed"] = True

    events = [{
        "id": "abcdef12-3456-7890-abcd-ef1234567890",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "protect_event_id": "protect-evt-1",
        "protect_controller_id": "controller-1",
        "box": {"x": 0.2, "y": 0.2, "width": 0.2, "height": 0.2},
    }]

    async def open_client(controller_id):
        return BadClient()

    with caplog.at_level("WARNING"):
        await module.enrich_events_with_protect(events, open_client)

    assert events[0]["timing_fetch"] == "Boom"
    assert events[0]["box"]["x"] == 0.2
    report = module.build_report(events, dry_run=True)
    blob = json.dumps(report)
    assert "controller.invalid" not in blob
    assert "fixture-password" not in blob
    assert "controller.invalid" not in caplog.text
    assert "fixture-password" not in caplog.text
    assert created["bad_closed"] is True


def test_live_without_yes_prints_estimate_and_stops(tmp_path, capsys, monkeypatch):
    module = _load_compare_script()
    fixture = tmp_path / "events.json"
    fixture.write_text(json.dumps({"events": [{
        "id": "evt-timed",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "frame_count": 4,
    }]}), encoding="utf-8")

    async def chain(*args, **kwargs):
        raise AssertionError("provider chain must not run")

    monkeypatch.setattr(module, "run_provider_chain", chain)
    with pytest.raises(SystemExit):
        module.main([
            "--fixture", str(fixture),
            "--live",
            "--output-dir", str(tmp_path / "out"),
        ])
    out = capsys.readouterr().out
    assert "Estimated cost before any vision call" in out
    assert "--yes" in out
    report = json.loads((tmp_path / "out" / "comparison.json").read_text(encoding="utf-8"))
    assert report["dry_run"] is True
    assert report["live_started"] is False
    assert report["ai_calls"] == 0
    assert report["blocked"] == "confirmation_required"


def test_live_limit_and_dry_run_flags_fail_closed(tmp_path):
    module = _load_compare_script()
    with pytest.raises(SystemExit):
        module.main([
            "--fixture", str(tmp_path / "unused.json"),
            "--live",
            "--yes",
            "--limit", "26",
            "--output-dir", str(tmp_path / "out"),
        ])
    with pytest.raises(SystemExit, match="cannot be combined"):
        module.main([
            "--live",
            "--dry-run",
            "--output-dir", str(tmp_path / "out"),
        ])


@pytest.mark.asyncio
async def test_run_provider_chain_falls_through_without_a_database(monkeypatch):
    module = _load_compare_script()
    from types import SimpleNamespace

    def boom_db():
        raise AssertionError("database opened")

    monkeypatch.setattr("app.core.database.get_db_session", boom_db)

    class Fail:
        async def generate_multi_image_description(self, **kwargs):
            return SimpleNamespace(
                success=False,
                error="timed out waiting",
                description=None,
                provider="bad",
                tokens_used=1,
                response_time_ms=5,
                identification=None,
            )

    class Ok:
        async def generate_multi_image_description(self, **kwargs):
            return SimpleNamespace(
                success=True,
                error=None,
                description="A person walks past.",
                provider="fake",
                tokens_used=12,
                response_time_ms=40,
                identification={"object_type": "person", "identity": "unknown"},
            )

    result = await module.run_provider_chain(
        [Fail(), Ok()],
        ["aaaa"],
        "prompt",
        "Gate",
        "2026-01-01T00:00:00Z",
        ["person"],
    )
    assert result["provider"] == "fake"
    assert result["tokens_used"] == 12
    assert result["latency_ms"] == 40
    assert result["description"] == "A person walks past."
    assert result["identification"]["identity"] == "unknown"
    assert result["error"] is None


@pytest.mark.asyncio
async def test_live_temp_clips_are_deleted(tmp_path, monkeypatch):
    module = _load_compare_script()
    events = [{
        "id": "evt-1",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "protect_camera_id": "cam",
        "protect_controller_id": "ctl",
        "frame_count": 2,
        "subject_crop_count": 0,
        "smart_detection_type": "person",
    }]
    report = module.build_report(events, dry_run=True, frame_count=2, subject_crop_count=0)
    created = []

    async def download(controller_id, camera_id, start, end, output_file):
        path = Path(output_file)
        assert "data/clips" not in path.as_posix()
        path.write_bytes(b"fake-mp4")
        created.append(path)

    async def images(clip_path, plan, box):
        assert Path(clip_path).is_file()
        return ["aaaa"]

    async def chain(*args, **kwargs):
        return {
            "description": "A person walks past.",
            "identification": {"identity": "unknown"},
            "provider": "fake",
            "latency_ms": 3,
            "tokens_used": 9,
            "error": None,
        }

    monkeypatch.setattr(module, "images_from_plan", images)
    monkeypatch.setattr(module, "run_provider_chain", chain)
    await module.fill_live_descriptions(events, report, providers=[object()], download=download)
    assert len(created) == 2
    assert all(not path.exists() for path in created)
    assert report["dry_run"] is False
    assert report["ai_calls"] == 2
    assert report["events"][0]["old"]["tokens_used"] == 9
    assert report["events"][0]["old"]["identification"] is None
    assert report["events"][0]["new"]["provider"] == "fake"
    assert report["events"][0]["new"]["identification"]["identity"] == "unknown"
    assert not (tmp_path / "data" / "clips").exists()


@pytest.mark.asyncio
async def test_stored_clip_is_not_deleted(tmp_path, monkeypatch):
    module = _load_compare_script()
    clip = tmp_path / "kept.mp4"
    clip.write_bytes(b"stored")
    events = [{
        "id": "evt",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "video_path": str(clip),
        "frame_count": 2,
        "subject_crop_count": 0,
    }]
    report = module.build_report(events, dry_run=True, frame_count=2, subject_crop_count=0)

    async def download(*args, **kwargs):
        raise AssertionError("stored clip must not be downloaded again")

    async def images(clip_path, plan, box):
        assert Path(clip_path) == clip
        return ["aaaa"]

    async def chain(*args, **kwargs):
        return {
            "description": "A person walks past.",
            "identification": {"identity": "unknown"},
            "provider": "fake",
            "latency_ms": 1,
            "tokens_used": 2,
            "error": None,
        }

    monkeypatch.setattr(module, "images_from_plan", images)
    monkeypatch.setattr(module, "run_provider_chain", chain)
    await module.fill_live_descriptions(events, report, providers=[object()], download=download)
    assert clip.is_file() and clip.read_bytes() == b"stored"
    assert report["events"][0]["clip_note"] == "stored_clip_offsets_are_file_offsets"


def test_compare_cost_uses_measured_grok_image_tokens():
    module = _load_compare_script()
    estimate = module._estimate(10, "x" * 40, provider="grok")
    assert estimate["tokens_estimate"] >= 10000
    assert estimate["tokens_estimate"] < 10100
    assert estimate["estimate_provider"] == "grok"
    assert estimate["estimate_source"] == "provider_image_budget"
    # The old 85-token budget was about 8x low for this call.
    assert estimate["tokens_estimate"] > 10 * 85 * 8

    claude = module._estimate(1, "", provider="claude")
    assert claude["tokens_estimate"] == 1334


def test_tiny_box_skips_the_crop_in_the_comparison_plan():
    module = _load_compare_script()
    events = [{
        "id": "leaf",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "detection_start": "2026-01-01T12:00:00+00:00",
        "detection_end": "2026-01-01T12:00:04+00:00",
        "peak": "2026-01-01T12:00:02+00:00",
        "box": {"x": 0.42, "y": 0.55, "width": 50 / 2688, "height": 95 / 1512},
        "frame_count": 10,
        "subject_crop_count": 1,
        "smart_detection_type": "animal",
    }]
    report = module.build_report(events, dry_run=True)
    new = report["events"][0]["new"]
    assert new["subject_crop_used"] is False
    assert "closer crop does not mean" not in new["prompt"]
    assert "Detected objects" not in new["prompt"]


def test_production_old_prompt_is_the_protect_base_prompt(tmp_path):
    module = _load_compare_script()
    events = [{
        "id": "evt",
        "timestamp": "2026-01-01T12:00:00+00:00",
        "smart_detection_type": "animal",
    }]
    report = module.build_report(events, dry_run=True, production_old_prompt=True)
    old = report["events"][0]["old"]["prompt"]
    new = report["events"][0]["new"]["prompt"]
    assert "WHO (people" in old
    assert IDENTIFICATION_MARKER not in old
    assert "Detected objects" not in old
    assert IDENTIFICATION_MARKER in new
    assert report["events"][0]["old"]["identification"] is None

    code = module.main([
        "--fixture", str(_write_fixture(tmp_path, events)),
        "--production-old-prompt",
        "--output-dir", str(tmp_path / "out"),
    ])
    assert code == 0
    saved = json.loads((tmp_path / "out" / "comparison.json").read_text(encoding="utf-8"))
    assert "WHO (people" in saved["events"][0]["old"]["prompt"]
    assert IDENTIFICATION_MARKER not in saved["events"][0]["old"]["prompt"]


def _write_fixture(tmp_path, events):
    path = tmp_path / "events.json"
    path.write_text(json.dumps({"events": events}), encoding="utf-8")
    return path

