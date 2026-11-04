"""Low-light frame handling for night vehicle identification.

Pure helpers: classify a frame as normal / low light / IR (grayscale), apply
a light enhancement (CLAHE or gamma) before local analysis, and build the
prompt note that tells the model not to guess colour on IR or grayscale
frames. Nothing here logs image data or description text.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# frame_condition values stored on identification.
FRAME_NORMAL = "normal"
FRAME_LOW_LIGHT = "low_light"
FRAME_IR = "ir"  # grayscale / infrared night vision
FRAME_CONDITIONS = (FRAME_NORMAL, FRAME_LOW_LIGHT, FRAME_IR)
COLORLESS_CONDITIONS = frozenset({FRAME_IR})

# Mean absolute RGB channel spread (0-255) below which a frame is grayscale.
GRAYSCALE_MAX_SPREAD = 6.0

NIGHT_PROMPT_MARKER = "NIGHT FRAME NOTE"


@dataclass(frozen=True)
class LowLightConfig:
    enabled: bool = True
    method: str = "clahe"
    dark_luma: int = 70

    @classmethod
    def from_settings(cls) -> "LowLightConfig":
        from app.core.config import settings

        return cls(
            enabled=bool(getattr(settings, "NIGHT_VEHICLE_LOW_LIGHT_ENABLED", True)),
            method=str(getattr(settings, "NIGHT_VEHICLE_ENHANCE_METHOD", "clahe")).lower(),
            dark_luma=int(getattr(settings, "NIGHT_VEHICLE_DARK_LUMA", 70)),
        )


@dataclass(frozen=True)
class FrameLight:
    condition: str
    mean_luma: float
    channel_spread: float

    @property
    def is_low_light(self) -> bool:
        return self.condition != FRAME_NORMAL

    @property
    def colorless(self) -> bool:
        return self.condition in COLORLESS_CONDITIONS


def _decode(image_base64: str):
    from PIL import Image

    raw = image_base64.split(",", 1)[1] if image_base64.startswith("data:") else image_base64
    return Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")


def classify_frame(image_base64: str, dark_luma: int = 70) -> Optional[FrameLight]:
    """Classify a base64 JPEG/PNG frame. None when it cannot be decoded."""
    import numpy as np

    try:
        img = _decode(image_base64)
    except Exception as exc:  # noqa: BLE001 - bad image means "unknown"
        logger.debug("Frame light check skipped (%s)", type(exc).__name__)
        return None
    img.thumbnail((256, 256))
    arr = np.asarray(img, dtype=np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    luma = float((0.299 * r + 0.587 * g + 0.114 * b).mean())
    spread = float((np.abs(r - g) + np.abs(g - b) + np.abs(r - b)).mean() / 3.0)
    if spread <= GRAYSCALE_MAX_SPREAD:
        condition = FRAME_IR
    elif luma < dark_luma:
        condition = FRAME_LOW_LIGHT
    else:
        condition = FRAME_NORMAL
    return FrameLight(condition=condition, mean_luma=round(luma, 1), channel_spread=round(spread, 1))


def enhance_low_light(image_base64: str, method: str = "clahe") -> str:
    """Return a brightened copy (base64 JPEG). The input on any failure."""
    if method not in ("clahe", "gamma"):
        return image_base64
    try:
        import numpy as np
        from PIL import Image

        img = _decode(image_base64)
        arr = np.asarray(img)
        if method == "clahe":
            import cv2

            lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
            l_chan, a_chan, b_chan = cv2.split(lab)
            l_chan = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l_chan)
            out = cv2.cvtColor(cv2.merge((l_chan, a_chan, b_chan)), cv2.COLOR_LAB2RGB)
        else:
            gamma = 0.6
            table = (np.linspace(0, 1, 256) ** gamma * 255).astype("uint8")
            out = table[arr]
        buf = io.BytesIO()
        Image.fromarray(out).save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:  # noqa: BLE001 - enhancement is best effort
        logger.debug("Low-light enhancement skipped (%s)", type(exc).__name__)
        return image_base64


def low_light_prompt_note(light: Optional[FrameLight], enhanced: bool = False) -> str:
    """Prompt text for a low-light or IR frame; '' for a normal frame."""
    if light is None or not light.is_low_light:
        return ""
    lines = [f"{NIGHT_PROMPT_MARKER}:"]
    if light.colorless:
        lines.append(
            "This frame is infrared / grayscale night vision. Colours are not visible: "
            "do not name a vehicle colour (write 'cannot_tell' for colour) and do not "
            "infer colour from brightness."
        )
    else:
        lines.append("This frame was taken in low light. Only name a colour you can clearly see.")
    if enhanced:
        lines.append("The image was brightened for readability; noise and glare are artefacts.")
    lines.append(
        "For a vehicle, describe its headlight / lighting pattern in headlight_pattern "
        "(for example one continuous full-width light bar versus two separate headlights) "
        "even when the make is not visible."
    )
    return "\n".join(lines)


def apply_low_light_note(prompt: str, note: str) -> str:
    if not note or NIGHT_PROMPT_MARKER in (prompt or ""):
        return prompt
    return (prompt or "").rstrip() + "\n\n" + note


def is_night_hour(when: Optional[datetime], start_hour: int = 18, end_hour: int = 7) -> bool:
    """Whether ``when`` (box-local after conversion) falls in the night window."""
    if when is None:
        return False
    if when.tzinfo is not None:
        when = when.astimezone()
    hour = when.hour
    if start_hour == end_hour:
        return False
    if start_hour > end_hour:
        return hour >= start_hour or hour < end_hour
    return start_hour <= hour < end_hour


def identification_is_colorless(identification) -> bool:
    return isinstance(identification, dict) and identification.get("frame_condition") in COLORLESS_CONDITIONS


def identification_is_night(identification) -> bool:
    return isinstance(identification, dict) and identification.get("frame_condition") in (FRAME_LOW_LIGHT, FRAME_IR)
