"""
Gemini Provider (Google) Implementation

Extracted during Phase 3.3. Uses the supported ``google-genai`` SDK
(``from google import genai``).
"""

import base64
import logging
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple, Union

from google import genai
from google.genai import types

from .base import AIProviderBase
from app.services.ai_types import AIResult
from app.services.identification import (
    DESCRIPTION_MAX_OUTPUT_TOKENS,
    ensure_identification_prompt,
)
from app.services.ocr_service import OCRResult

logger = logging.getLogger(__name__)

# Gemini accepts inline video under 20 MB. Larger clips use the Files API.
GEMINI_INLINE_VIDEO_BYTES = 20 * 1024 * 1024
DEFAULT_GEMINI_VIDEO_FPS = 3

# Hung calls must return an error the fallback chain can classify.
# Single-image matches the 10s provider timeout (#625 / OpenAI). Multi-image
# matches OpenAI's 15s. Native video matches the 30s video SLA. Values are
# milliseconds because google.genai HttpOptions.timeout is in milliseconds.
_SINGLE_IMAGE_TIMEOUT_MS = 10_000
_MULTI_IMAGE_TIMEOUT_MS = 15_000
_VIDEO_TIMEOUT_MS = 30_000


def _redact_secret(text: str, secret: Optional[str]) -> str:
    """Remove an API key if a provider exception echoes it. Never log the key."""
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


def _error_for_fallback(exc: BaseException, api_key: Optional[str]) -> str:
    """Error text the fallback chain already understands (status codes, timeout)."""
    text = _redact_secret(str(exc) or type(exc).__name__, api_key)
    lowered = text.lower()
    if "timeout" in type(exc).__name__.lower() and "timeout" not in lowered and "timed out" not in lowered:
        text = f"timeout: {text}"
    return text


def _jpeg_bytes(image: Union[str, bytes, bytearray]) -> bytes:
    """Decode the base64 text callers pass. Raw bytes are sent unchanged."""
    if isinstance(image, (bytes, bytearray)):
        return bytes(image)
    return base64.b64decode(image)


def _image_part(image: Union[str, bytes, bytearray]) -> types.Part:
    return types.Part.from_bytes(data=_jpeg_bytes(image), mime_type="image/jpeg")


def _file_state_name(uploaded) -> str:
    """Files API state, for both the enum and a test double with ``.name``."""
    state = getattr(uploaded, "state", None)
    if state is None:
        return ""
    value = getattr(state, "value", None)
    if isinstance(value, str) and value:
        return value
    name = getattr(state, "name", None)
    if isinstance(name, str) and name:
        return name
    return str(state)


class GeminiProvider(AIProviderBase):
    """Google Gemini Flash vision provider"""

    def __init__(self, api_key: str, model: str = None):
        super().__init__(api_key)
        from app.services.ai_providers.model_resolver import resolve_model
        self.model_name = resolve_model("gemini", api_key, override=model)
        # Developer API key from settings. vertexai=False keeps a host-level
        # GOOGLE_GENAI_USE_VERTEXAI flag from sending that key to Vertex.
        # The key is not logged.
        self.client = genai.Client(api_key=api_key, vertexai=False)
        self.cost_per_1k_input_tokens = 0.000075
        self.cost_per_1k_output_tokens = 0.0003

    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None
    ) -> AIResult:
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Describe the security camera image in detail."

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=[user_prompt, _image_part(image_base64)],
                config=types.GenerateContentConfig(
                    max_output_tokens=DESCRIPTION_MAX_OUTPUT_TOKENS,
                    http_options=types.HttpOptions(timeout=_SINGLE_IMAGE_TIMEOUT_MS),
                ),
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.text.strip() if response.text else ""

            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw_response)

            # Gemini token estimation is rough
            tokens_used = len(raw_response.split()) * 1.3
            cost = tokens_used / 1000 * 0.0002

            confidence = ai_confidence or self._calculate_confidence(description, int(tokens_used))
            objects = self._extract_objects(description)

            return self._with_identification(AIResult(
                description=description,
                confidence=confidence,
                objects_detected=objects,
                provider="gemini",
                tokens_used=int(tokens_used),
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True,
                ai_confidence=ai_confidence,
                bounding_boxes=bounding_boxes,
            ), raw_response)

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider="gemini",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=_error_for_fallback(e, self.api_key)
            )

    async def generate_multi_image_description(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None
    ) -> AIResult:
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Analyze this sequence of images and describe the event."

            parts = [user_prompt]
            for img in images_base64:
                parts.append(_image_part(img))

            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=parts,
                config=types.GenerateContentConfig(
                    max_output_tokens=DESCRIPTION_MAX_OUTPUT_TOKENS,
                    http_options=types.HttpOptions(timeout=_MULTI_IMAGE_TIMEOUT_MS),
                ),
            )

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.text.strip() if response.text else ""

            description, ai_confidence, _ = self._parse_confidence_response(raw_response)

            tokens_used = len(raw_response.split()) * 1.5
            cost = tokens_used / 1000 * 0.00035

            return self._with_identification(AIResult(
                description=description,
                confidence=ai_confidence or 72,
                objects_detected=self._extract_objects(description),
                provider="gemini",
                tokens_used=int(tokens_used),
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=True,
                ai_confidence=ai_confidence,
            ), raw_response)

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider="gemini",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=_error_for_fallback(e, self.api_key)
            )

    def _calculate_confidence(self, description: str, tokens_used: int) -> int:
        confidence = 65
        if len(description) > 120:
            confidence += 12
        return min(confidence, 90)

    async def describe_video(
        self,
        video_path: "Path",
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
        fps: int = DEFAULT_GEMINI_VIDEO_FPS,
    ) -> AIResult:
        """Send the event clip to Gemini as video.

        Image-only providers never take this path. The caller downloads a clip
        already trimmed to the event window; this re-encodes it at ``fps`` when
        PyAV can. Inline video is used under 20 MB and the Files API above that.
        A failure is logged and returned so the caller can fall back. This does
        not call ``extract_frames``: that call used argument names the extractor
        does not accept, and the TypeError was swallowed.
        """
        start_time = time.time()
        path = Path(video_path)
        try:
            if not path.is_file():
                raise FileNotFoundError(path.name)

            fps = max(2, min(5, int(fps or DEFAULT_GEMINI_VIDEO_FPS)))
            payload, owns_payload = _prepare_gemini_clip(path, fps)
            try:
                video_bytes = payload.read_bytes()
                prompt = ensure_identification_prompt(
                    custom_prompt or "Describe this security camera clip."
                )
                video_config = types.GenerateContentConfig(
                    max_output_tokens=DESCRIPTION_MAX_OUTPUT_TOKENS,
                    http_options=types.HttpOptions(timeout=_VIDEO_TIMEOUT_MS),
                )
                if len(video_bytes) <= GEMINI_INLINE_VIDEO_BYTES:
                    parts = [
                        prompt,
                        types.Part(
                            inline_data=types.Blob(data=video_bytes, mime_type="video/mp4"),
                        ),
                    ]
                    response = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=parts,
                        config=video_config,
                    )
                else:
                    uploaded = _upload_gemini_file(self.client, payload)
                    response = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=[prompt, uploaded],
                        config=video_config,
                    )
            finally:
                if owns_payload:
                    payload.unlink(missing_ok=True)

            elapsed_ms = int((time.time() - start_time) * 1000)
            raw_response = response.text.strip() if getattr(response, "text", None) else ""
            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw_response)
            usage = getattr(response, "usage_metadata", None)
            tokens_used = int(getattr(usage, "total_token_count", 0) or 0)
            if tokens_used <= 0:
                tokens_used = int(len(raw_response.split()) * 1.5)
            cost = tokens_used / 1000 * 0.00035
            result = AIResult(
                description=description,
                confidence=ai_confidence or self._calculate_confidence(description, tokens_used),
                objects_detected=self._extract_objects(description),
                provider="gemini",
                tokens_used=tokens_used,
                response_time_ms=elapsed_ms,
                cost_estimate=cost,
                success=bool(description),
                ai_confidence=ai_confidence,
                bounding_boxes=bounding_boxes,
                error=None if description else "Gemini returned an empty video description",
            )
            return self._with_identification(result, raw_response)
        except Exception as exc:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Gemini native video failed; the caller may fall back to multi-frame images: %s",
                type(exc).__name__,
                extra={
                    "event_type": "gemini_native_video_failed",
                    "error_type": type(exc).__name__,
                },
            )
            return AIResult(
                description="",
                confidence=0,
                objects_detected=detected_objects or [],
                provider="gemini",
                tokens_used=0,
                response_time_ms=elapsed_ms,
                cost_estimate=0.0,
                success=False,
                error=f"Video analysis failed: {type(exc).__name__}",
            )


def _prepare_gemini_clip(src: Path, fps: int) -> Tuple[Path, bool]:
    """Re-encode at ``fps`` when possible. The original file is the fallback.

    The second value is True when the caller owns the returned path and should
    delete it. The source clip is never deleted here.
    """
    handle = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    handle.close()
    dest = Path(handle.name)
    try:
        import av

        with av.open(str(src)) as inp:
            if not inp.streams.video:
                dest.unlink(missing_ok=True)
                return src, False
            stream = inp.streams.video[0]
            width = int(stream.codec_context.width or 0)
            height = int(stream.codec_context.height or 0)
            if width < 2 or height < 2:
                dest.unlink(missing_ok=True)
                return src, False
            width -= width % 2
            height -= height % 2
            with av.open(str(dest), "w") as out:
                out_stream = out.add_stream("libx264", rate=fps)
                out_stream.width = width
                out_stream.height = height
                out_stream.pix_fmt = "yuv420p"
                next_t = 0.0
                step = 1.0 / float(fps)
                for frame in inp.decode(video=0):
                    moment = float(frame.time) if frame.time is not None else 0.0
                    if moment + 1e-3 < next_t:
                        continue
                    frame.pts = None
                    for packet in out_stream.encode(frame):
                        out.mux(packet)
                    next_t += step
                for packet in out_stream.encode(None):
                    out.mux(packet)
        if dest.is_file() and dest.stat().st_size > 0:
            return dest, True
    except Exception as exc:
        logger.warning(
            "Gemini clip re-encode failed; sending the original event clip: %s",
            type(exc).__name__,
            extra={"event_type": "gemini_clip_reencode_failed"},
        )
    dest.unlink(missing_ok=True)
    return src, False


def _upload_gemini_file(client, path: Path):
    """Files API path for clips at or above the inline limit."""
    uploaded = client.files.upload(file=str(path), config={"mime_type": "video/mp4"})
    deadline = time.time() + 30
    state_name = _file_state_name(uploaded)
    while state_name == "PROCESSING" and time.time() < deadline:
        time.sleep(1)
        uploaded = client.files.get(name=uploaded.name)
        state_name = _file_state_name(uploaded)
    if state_name == "FAILED":
        raise RuntimeError("Gemini file processing failed")
    return uploaded
