"""
Gemini Provider (Google) Implementation

Extracted during Phase 3.3.
"""

import logging
import tempfile
import asyncio
import time
from pathlib import Path
from typing import List, Optional, Tuple

import google.generativeai as genai

from .base import AIProviderBase, resolve_request_timeout
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


class GeminiProvider(AIProviderBase):
    """Google Gemini Flash vision provider"""

    def __init__(self, api_key: str, model: str = None):
        super().__init__(api_key)
        genai.configure(api_key=api_key)
        from app.services.ai_providers.model_resolver import resolve_model
        self.model_name = resolve_model("gemini", api_key, override=model)
        self.model = genai.GenerativeModel(self.model_name)
        self.cost_per_1k_input_tokens = 0.000075
        self.cost_per_1k_output_tokens = 0.0003

    async def _generate_content(self, contents, max_output_tokens: int, request_timeout_s: Optional[float]):
        """Call Gemini and cancel the request when the orchestrator budget expires.

        ``request_timeout_s`` is None for direct callers; the library default
        then applies. A positive value is the remaining per-provider budget.
        """
        coro = self.model.generate_content_async(
            contents,
            generation_config={"max_output_tokens": max_output_tokens},
        )
        if request_timeout_s is None:
            return await coro
        return await asyncio.wait_for(
            coro,
            timeout=resolve_request_timeout(request_timeout_s, 30.0),
        )

    async def generate_description(
        self,
        image_base64: str,
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
        request_timeout_s: Optional[float] = None,
    ) -> AIResult:
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Describe the security camera image in detail."

            response = await self._generate_content(
                [
                    user_prompt,
                    {"mime_type": "image/jpeg", "data": image_base64}
                ],
                DESCRIPTION_MAX_OUTPUT_TOKENS,
                request_timeout_s,
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
                error=str(e)
            )

    async def generate_multi_image_description(
        self,
        images_base64: List[str],
        camera_name: str,
        timestamp: str,
        detected_objects: List[str],
        custom_prompt: Optional[str] = None,
        audio_transcription: Optional[str] = None,
        ocr_result: Optional[OCRResult] = None,
        request_timeout_s: Optional[float] = None,
    ) -> AIResult:
        start_time = time.time()

        try:
            user_prompt = custom_prompt or "Analyze this sequence of images and describe the event."

            parts = [user_prompt]
            for img in images_base64:
                parts.append({"mime_type": "image/jpeg", "data": img})

            response = await self._generate_content(
                parts,
                DESCRIPTION_MAX_OUTPUT_TOKENS,
                request_timeout_s,
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
                error=str(e)
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
                if len(video_bytes) <= GEMINI_INLINE_VIDEO_BYTES:
                    parts = [prompt, {"mime_type": "video/mp4", "data": video_bytes}]
                    response = await self.model.generate_content_async(
                        parts,
                        generation_config={"max_output_tokens": DESCRIPTION_MAX_OUTPUT_TOKENS},
                    )
                else:
                    uploaded = _upload_gemini_file(payload)
                    response = await self.model.generate_content_async(
                        [prompt, uploaded],
                        generation_config={"max_output_tokens": DESCRIPTION_MAX_OUTPUT_TOKENS},
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


def _upload_gemini_file(path: Path):
    """Files API path for clips at or above the inline limit."""
    uploaded = genai.upload_file(path=str(path), mime_type="video/mp4")
    deadline = time.time() + 30
    state_name = getattr(getattr(uploaded, "state", None), "name", "")
    while state_name == "PROCESSING" and time.time() < deadline:
        time.sleep(1)
        uploaded = genai.get_file(uploaded.name)
        state_name = getattr(getattr(uploaded, "state", None), "name", "")
    if state_name == "FAILED":
        raise RuntimeError("Gemini file processing failed")
    return uploaded
