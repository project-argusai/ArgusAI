"""google-genai SDK migration for the Gemini provider.

The deprecated ``google.generativeai`` package must not be imported. These
tests mock ``google.genai`` and lock the behavior the fallback chain depends
on: image parts, the 1024-token budget, timeouts, status-code errors, token
and cost estimates, and the native-video fps clamp.
"""
import asyncio
import base64
import io
import os
import subprocess
import sys
import tempfile
import warnings
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from PIL import Image

from app.services.ai_provider_order import classify_provider_error
from app.services.identification import DESCRIPTION_MAX_OUTPUT_TOKENS, IDENTIFICATION_MARKER


def _jpeg_b64() -> str:
    image = Image.new("RGB", (2, 2), color="red")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def _provider(api_key="test-key"):
    with patch("app.services.ai_providers.gemini_provider.genai.Client") as client_cls:
        client = MagicMock()
        client_cls.return_value = client
        with patch(
            "app.services.ai_providers.model_resolver.resolve_model",
            return_value="gemini-test",
        ):
            from app.services.ai_providers.gemini_provider import GeminiProvider

            provider = GeminiProvider(api_key)
    return provider, client


def test_backend_does_not_import_the_deprecated_sdk():
    backend = Path(__file__).resolve().parents[2]
    requirements = (backend / "requirements.txt").read_text(encoding="utf-8")
    assert "google-generativeai" not in requirements
    assert "google-genai>=" in requirements
    offenders = []
    candidates = [backend / "main.py"]
    candidates.extend((backend / "app").rglob("*.py"))
    candidates.extend((backend / "scripts").rglob("*.py"))
    for path in candidates:
        if "opencv_face" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "google.generativeai" in text:
            offenders.append(str(path.relative_to(backend)))
    assert offenders == []


def test_importing_the_provider_emits_no_generativeai_future_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        import importlib
        import app.services.ai_providers.gemini_provider as module

        importlib.reload(module)
    bad = [
        str(item.message)
        for item in caught
        if "google.generativeai" in str(item.message).lower()
        or (
            issubclass(item.category, FutureWarning)
            and "generativeai" in str(item.message).lower()
        )
    ]
    assert bad == []
    assert "google.generativeai" not in sys.modules


def test_app_entrypoint_emits_no_generativeai_future_warning():
    """Startup smoke: importing main must not log the deprecated-SDK warning."""
    backend = Path(__file__).resolve().parents[2]
    code = """
import warnings
warnings.simplefilter("always")
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    import main
bad = []
for item in caught:
    message = str(item.message)
    if "google.generativeai" in message.lower() or (
        issubclass(item.category, FutureWarning) and "generativeai" in message.lower()
    ):
        bad.append(message)
if bad:
    raise SystemExit(" | ".join(bad))
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend)
    # Same disposable values the CI startup-smoke job uses. Do not print them.
    env.setdefault("ENCRYPTION_KEY", "YhLHon9m3QOhb394b-Qa761Vgj9ij3oLlT-moS2oRcg=")
    env.setdefault("JWT_SECRET_KEY", "ci-smoke-test-secret-not-for-production")
    with tempfile.TemporaryDirectory() as tmp:
        env["DATABASE_URL"] = "sqlite:///" + str(Path(tmp) / "smoke.db")
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=backend,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
    assert completed.returncode == 0, completed.stderr[-2000:] + completed.stdout[-500:]


@pytest.mark.asyncio
async def test_single_image_sends_jpeg_bytes_budget_timeout_and_cost():
    provider, client = _provider()
    response = MagicMock()
    response.text = "one two three four"
    client.aio.models.generate_content = AsyncMock(return_value=response)
    image = _jpeg_b64()

    result = await provider.generate_description(image, "Yard", "2026-01-01T00:00:00Z", [])

    call = client.aio.models.generate_content.await_args.kwargs
    part = call["contents"][1]
    assert call["model"] == "gemini-test"
    assert part.inline_data.mime_type == "image/jpeg"
    assert part.inline_data.data == base64.b64decode(image)
    assert call["config"].max_output_tokens == DESCRIPTION_MAX_OUTPUT_TOKENS == 1024
    assert call["config"].http_options.timeout == 10_000
    assert result.success is True
    assert result.tokens_used == int(4 * 1.3)
    assert result.cost_estimate == pytest.approx((4 * 1.3) / 1000 * 0.0002)


@pytest.mark.asyncio
async def test_multi_image_timeout_and_cost():
    provider, client = _provider()
    response = MagicMock()
    response.text = "one two three four"
    client.aio.models.generate_content = AsyncMock(return_value=response)
    images = [_jpeg_b64(), _jpeg_b64()]

    result = await provider.generate_multi_image_description(
        images, "Yard", "2026-01-01T00:00:00Z", []
    )

    call = client.aio.models.generate_content.await_args.kwargs
    assert len(call["contents"]) == 3
    assert call["config"].max_output_tokens == 1024
    assert call["config"].http_options.timeout == 15_000
    assert result.tokens_used == int(4 * 1.5)
    assert result.cost_estimate == pytest.approx((4 * 1.5) / 1000 * 0.00035)
    # No structured identification / ai_confidence → scored from empty fields
    from app.services.identification import confidence_from_identification
    assert result.confidence == confidence_from_identification()


@pytest.mark.asyncio
async def test_provider_error_keeps_status_and_redacts_the_key():
    secret = "test-key"
    provider, client = _provider(secret)
    client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError(f"429 rate limit for {secret}")
    )

    result = await provider.generate_description(_jpeg_b64(), "Yard", "t", [])

    assert result.success is False
    assert secret not in (result.error or "")
    assert "[redacted]" in (result.error or "")
    assert classify_provider_error(result.error) == "http_429"

    client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError(f"429 RESOURCE_EXHAUSTED for {secret}")
    )
    quota = await provider.generate_description(_jpeg_b64(), "Yard", "t", [])
    assert secret not in (quota.error or "")
    assert classify_provider_error(quota.error) == "quota_exhausted"


@pytest.mark.asyncio
async def test_timeout_is_classified_for_the_fallback_chain():
    provider, client = _provider()
    client.aio.models.generate_content = AsyncMock(
        side_effect=httpx.ReadTimeout("The read operation timed out")
    )

    result = await provider.generate_description(_jpeg_b64(), "Yard", "t", [])

    assert result.success is False
    assert classify_provider_error(result.error) == "timeout"
    assert "test-key" not in (result.error or "")


@pytest.mark.asyncio
async def test_orchestrator_deadline_cancels_the_call_and_replaces_the_fixed_timeout():
    """A shorter orchestrator budget cancels Gemini and is the HTTP timeout."""
    provider, client = _provider()
    seen = {}

    async def hang(**kwargs):
        seen["timeout_ms"] = kwargs["config"].http_options.timeout
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            seen["cancelled"] = True
            raise

    client.aio.models.generate_content = hang
    result = await provider.generate_description(
        _jpeg_b64(), "Yard", "t", [], request_timeout_s=0.05
    )

    assert seen["timeout_ms"] == 50
    assert seen.get("cancelled") is True
    assert result.success is False
    assert classify_provider_error(result.error) == "timeout"
    assert "test-key" not in (result.error or "")


@pytest.mark.asyncio
async def test_longer_orchestrator_deadline_is_not_cut_to_the_fixed_timeout():
    """A budget above 10s/15s is sent as-is. The fixed default does not win."""
    provider, client = _provider()
    response = MagicMock()
    response.text = "one two"
    client.aio.models.generate_content = AsyncMock(return_value=response)

    await provider.generate_description(
        _jpeg_b64(), "Yard", "t", [], request_timeout_s=25
    )
    single = client.aio.models.generate_content.await_args.kwargs
    assert single["config"].http_options.timeout == 25_000
    assert single["config"].max_output_tokens == 1024

    await provider.generate_multi_image_description(
        [_jpeg_b64(), _jpeg_b64()], "Yard", "t", [], request_timeout_s=20
    )
    multi = client.aio.models.generate_content.await_args.kwargs
    assert multi["config"].http_options.timeout == 20_000

    await provider.generate_description(
        _jpeg_b64(), "Yard", "t", [], request_timeout_s=0
    )
    # A non-positive budget uses the shared 30s fallback, not the 10s default.
    fallback = client.aio.models.generate_content.await_args.kwargs
    assert fallback["config"].http_options.timeout == 30_000


@pytest.mark.asyncio
async def test_describe_video_uses_usage_metadata_and_clamps_fps(tmp_path, monkeypatch):
    provider, client = _provider()
    seen = {}

    def prepare(src, fps):
        seen["fps"] = fps
        return src, False

    monkeypatch.setattr(
        "app.services.ai_providers.gemini_provider._prepare_gemini_clip",
        prepare,
    )
    response = MagicMock()
    response.text = '{"description": "A person walks.", "object_type": "person", "count": 1, "identity": "unknown", "action": "walking", "direction": "left", "package_or_carrier": "none"}'
    response.usage_metadata = SimpleNamespace(total_token_count=120)
    client.aio.models.generate_content = AsyncMock(return_value=response)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")

    result = await provider.describe_video(clip, "Gate", "t", ["motion"], fps=9)

    assert seen["fps"] == 5
    assert result.success is True
    assert result.tokens_used == 120
    assert result.cost_estimate == pytest.approx(120 / 1000 * 0.00035)
    prompt = client.aio.models.generate_content.await_args.kwargs["contents"][0]
    assert IDENTIFICATION_MARKER in prompt

    await provider.describe_video(clip, "Gate", "t", [], fps=1)
    assert seen["fps"] == 2


@pytest.mark.asyncio
async def test_files_api_waits_until_active(tmp_path, monkeypatch):
    provider, client = _provider()
    monkeypatch.setattr(
        "app.services.ai_providers.gemini_provider.GEMINI_INLINE_VIDEO_BYTES",
        1,
    )
    sleeps = []
    monkeypatch.setattr(
        "app.services.ai_providers.gemini_provider.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )
    uploaded = SimpleNamespace(name="files/abc", state=SimpleNamespace(name="PROCESSING"))

    def upload(**kwargs):
        assert kwargs["config"]["mime_type"] == "video/mp4"
        return uploaded

    def get(name):
        assert name == "files/abc"
        uploaded.state = SimpleNamespace(name="ACTIVE")
        return uploaded

    client.files.upload.side_effect = upload
    client.files.get.side_effect = get
    response = MagicMock()
    response.text = "A vehicle passes the drive."
    response.usage_metadata = None
    client.aio.models.generate_content = AsyncMock(return_value=response)
    clip = tmp_path / "big.mp4"
    clip.write_bytes(b"0123456789")

    result = await provider.describe_video(clip, "Drive", "t", [])

    assert sleeps == [1]
    assert result.success is True
    sent = client.aio.models.generate_content.await_args.kwargs["contents"]
    assert sent[1] is uploaded


@pytest.mark.asyncio
async def test_summary_gemini_uses_genai_timeout_and_hides_the_key():
    from app.services.summary_service import SummaryService

    service = SummaryService.__new__(SummaryService)
    service._cost_tracker = MagicMock()
    service._cost_tracker.calculate_cost.return_value = Decimal("0.010000")
    response = MagicMock()
    response.text = "Someone walked past the gate."
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=response)
    secret = "summary-gemini-key"

    with patch("google.genai.Client", return_value=client) as client_cls:
        text, provider, input_tokens, output_tokens, cost = await service._call_gemini(
            secret, "Be brief.", "Events: 1", 60
        )

    assert client_cls.call_args.kwargs == {"api_key": secret, "vertexai": False}
    call = client.aio.models.generate_content.await_args.kwargs
    assert call["model"] == "gemini-2.5-flash"
    assert call["contents"] == "Be brief.\n\nEvents: 1"
    assert call["config"].http_options.timeout == 60_000
    assert text == "Someone walked past the gate."
    assert provider == "gemini"
    assert secret not in text
    assert input_tokens == len("Be brief.\n\nEvents: 1") // 4
    assert output_tokens == len(text) // 4
    assert cost == Decimal("0.010000")


@pytest.mark.asyncio
async def test_google_key_check_redacts_the_key():
    from app.api.v1.system import _test_google_key

    secret = "gemini-key-should-not-leak"
    client = MagicMock()
    pager = MagicMock()
    pager.page = []
    client.models.list.return_value = pager

    with patch("google.genai.Client", return_value=client) as client_cls:
        ok, message = await _test_google_key(secret)

    assert ok is True
    assert message == "Google AI API key validated successfully"
    assert client_cls.call_args.kwargs["vertexai"] is False
    assert secret not in message

    client.models.list.side_effect = RuntimeError(f"network down {secret}")
    with patch("google.genai.Client", return_value=client):
        ok, message = await _test_google_key(secret)

    assert ok is False
    assert secret not in message
    assert "[redacted]" in message
