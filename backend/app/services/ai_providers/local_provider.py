"""Local vision model provider (OpenAI-compatible server on this host).

Talks to Ollama, mlx-vlm, LM Studio, or any server that implements
``/v1/chat/completions`` with image inputs. It is not part of the live cloud
fallback chain: ``LocalVLMFallbackService`` uses it to re-describe events
whose cloud analysis failed, with its own time budget.

Privacy: requests go only to the configured base URL. No API key is sent
(a fixed placeholder satisfies the SDK). Images are downscaled before
sending, and nothing from the response body is logged.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import time
from typing import List, Optional

from PIL import Image

from .base import AIProviderBase, resolve_request_timeout
from .quota_aware_client import LOCAL_PROVIDER_API_KEY, build_openai_client
from app.services.ai_types import AIResult
from app.services.identification import DESCRIPTION_MAX_OUTPUT_TOKENS
from app.services.ocr_service import OCRResult
from app.services.prompt_templates import MULTI_FRAME_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

LOCAL_PROVIDER_NAME = "local"
DEFAULT_LOCAL_TIMEOUT_S = 60.0
# Small local models drift with sampling; ArgusAI wants stable JSON.
LOCAL_TEMPERATURE = 0.2
EMPTY_SCENE_DESCRIPTION = "No person, vehicle, animal, or package is visible."


def downscale_image_base64(image_base64: str, max_side: int) -> str:
    """Return a JPEG no larger than ``max_side`` on its long edge.

    Vision-token count (and so local latency and memory) grows with
    resolution. An image already within the limit is returned unchanged.
    """
    raw = base64.b64decode(image_base64)
    with Image.open(io.BytesIO(raw)) as img:
        if max(img.size) <= max_side:
            return image_base64
        ratio = max_side / float(max(img.size))
        size = (max(1, int(img.size[0] * ratio)), max(1, int(img.size[1] * ratio)))
        resized = img.convert("RGB").resize(size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _reply_object(raw: str) -> Optional[dict]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def description_or_raise(raw: str, parsed_description: str) -> str:
    """The sentence to store, or ValueError when the reply has none.

    Small local models sometimes return the identification fields without a
    ``description`` (seen in ~half of empty-scene replies from a 4B model).
    The base parser would then store the raw JSON. An explicit empty frame
    gets the sentence the prompt asks for; any other reply without a
    description is a failure, so the placeholder stays.
    """
    data = _reply_object(raw)
    if data is None:
        return parsed_description  # plain-text reply
    text = data.get("description")
    if isinstance(text, str) and text.strip():
        return parsed_description
    if str(data.get("object_type") or "").strip().lower() == "none":
        return EMPTY_SCENE_DESCRIPTION
    raise ValueError("local model reply has no description")


class LocalVLMProvider(AIProviderBase):
    """Vision provider for a local OpenAI-compatible model server."""

    def __init__(
        self,
        base_url: str,
        model: str,
        max_image_side: int = 1024,
        default_timeout_s: float = DEFAULT_LOCAL_TIMEOUT_S,
    ):
        super().__init__(LOCAL_PROVIDER_API_KEY)
        self.base_url = base_url
        self.model = model
        self.max_image_side = max_image_side
        self.default_timeout_s = default_timeout_s
        # No SDK retries: a stopped local server should fail in milliseconds.
        self.client = build_openai_client(LOCAL_PROVIDER_API_KEY, base_url=base_url, max_retries=0)

    def _image_part(self, image_base64: str) -> dict:
        prepared = downscale_image_base64(image_base64, self.max_image_side)
        return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{prepared}"}}

    async def _complete(self, prompt: str, images_base64: List[str], request_timeout_s: Optional[float]) -> AIResult:
        start = time.time()
        try:
            content = [{"type": "text", "text": prompt}]
            content.extend(self._image_part(img) for img in images_base64)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": content},
                ],
                max_tokens=DESCRIPTION_MAX_OUTPUT_TOKENS,
                temperature=LOCAL_TEMPERATURE,
                response_format={"type": "json_object"},
                timeout=resolve_request_timeout(request_timeout_s, self.default_timeout_s),
            )
            elapsed_ms = int((time.time() - start) * 1000)
            raw = (response.choices[0].message.content or "").strip()
            if not raw:
                raise ValueError("empty response from local model")
            description, ai_confidence, bounding_boxes = self._parse_confidence_response(raw)
            description = description_or_raise(raw, description)
            usage = response.usage
            return self._with_identification(
                AIResult(
                    description=description,
                    confidence=ai_confidence if ai_confidence is not None else 0,
                    objects_detected=self._extract_objects(description),
                    provider=LOCAL_PROVIDER_NAME,
                    tokens_used=usage.total_tokens if usage else 0,
                    response_time_ms=elapsed_ms,
                    cost_estimate=0.0,
                    success=True,
                    ai_confidence=ai_confidence,
                    bounding_boxes=bounding_boxes,
                ),
                raw,
            )
        except Exception as exc:  # noqa: BLE001 - provider contract: never raise
            return AIResult(
                description="",
                confidence=0,
                objects_detected=[],
                provider=LOCAL_PROVIDER_NAME,
                tokens_used=0,
                response_time_ms=int((time.time() - start) * 1000),
                cost_estimate=0.0,
                success=False,
                # Class plus message; the SDK message carries the status, not the body.
                error=f"{type(exc).__name__}: {str(exc)[:200]}",
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
        prompt = custom_prompt or self.user_prompt_template
        return await self._complete(prompt, [image_base64], request_timeout_s)

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
        prompt = custom_prompt or MULTI_FRAME_SYSTEM_PROMPT.format(num_frames=len(images_base64))
        return await self._complete(prompt, list(images_base64), request_timeout_s)
