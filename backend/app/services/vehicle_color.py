"""
Coarse vehicle colour from a detected crop, and how it compares to a saved colour.

Used as an independent check next to the crop embedding: two red SUVs can
look alike to CLIP, but a red crop never matches a saved black car. The
check is deliberately coarse (about ten families) and says "unknown" rather
than guessing:

* Night IR frames carry no colour at all, so a frame whose channels are
  (nearly) equal everywhere returns ``None``.
* Neighbouring families (gray/silver/white, red/orange, blue/purple, a dark
  blue that reads as black) never count as a conflict.
"""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

COLOR_FAMILIES = (
    "red", "orange", "yellow", "green", "blue", "purple", "brown",
    "white", "black", "gray",
)

_ALIASES = {
    "grey": "gray", "silver": "gray", "charcoal": "gray", "gunmetal": "gray",
    "maroon": "red", "burgundy": "red", "crimson": "red",
    "gold": "yellow", "beige": "brown", "tan": "brown", "bronze": "brown",
    "navy": "blue", "teal": "blue", "violet": "purple",
    "pearl": "white", "cream": "white",
}

# Pairs that are too close to call a conflict under camera white balance.
_NEIGHBOURS = {
    frozenset({"gray", "white"}), frozenset({"gray", "black"}),
    frozenset({"red", "orange"}), frozenset({"orange", "yellow"}),
    frozenset({"orange", "brown"}), frozenset({"red", "brown"}),
    frozenset({"blue", "purple"}), frozenset({"blue", "black"}),
    frozenset({"green", "black"}), frozenset({"brown", "black"}),
    frozenset({"blue", "gray"}), frozenset({"green", "gray"}),
    frozenset({"brown", "gray"}),
}

# A frame whose mean |B-G|, |G-R| stays under this is treated as IR/greyscale.
_GRAYSCALE_CHANNEL_DELTA = 3.0
# Share of the region a family needs to be called the vehicle's colour.
_CHROMATIC_SHARE = 0.22
_MIN_WINNER_SHARE = 0.35


def normalize_color_name(name: Optional[str]) -> Optional[str]:
    """Map a free-text colour ("Grey", "silver", "Red") to a family, else None."""
    if not isinstance(name, str):
        return None
    for token in name.strip().lower().replace("-", " ").split():
        token = _ALIASES.get(token, token)
        if token in COLOR_FAMILIES:
            return token
    return None


def frame_is_grayscale(image_bgr: np.ndarray) -> bool:
    """True for IR night frames (and any frame without colour information)."""
    if image_bgr is None or image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        return True
    small = image_bgr
    if max(small.shape[:2]) > 320:
        scale = 320.0 / max(small.shape[:2])
        small = cv2.resize(small, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    f = small.astype(np.int16)
    delta = (np.abs(f[..., 0] - f[..., 1]).mean() + np.abs(f[..., 1] - f[..., 2]).mean()) / 2.0
    return float(delta) < _GRAYSCALE_CHANNEL_DELTA


def dominant_vehicle_color(crop_bgr: np.ndarray, *, frame_grayscale: Optional[bool] = None) -> Optional[str]:
    """Colour family of the vehicle in a tight crop, or None when it can't be told.

    Reads the centre of the crop (the body, mostly away from road and sky).
    Chromatic paint wins when it covers enough of the body, since windows,
    tyres and shadows are dark on every car.
    """
    if crop_bgr is None or crop_bgr.ndim != 3 or crop_bgr.size == 0:
        return None
    if frame_grayscale is None:
        frame_grayscale = frame_is_grayscale(crop_bgr)
    if frame_grayscale:
        return None
    h, w = crop_bgr.shape[:2]
    region = crop_bgr[int(h * 0.25): int(h * 0.85), int(w * 0.15): int(w * 0.85)]
    if region.size == 0:
        return None
    if max(region.shape[:2]) > 160:
        scale = 160.0 / max(region.shape[:2])
        region = cv2.resize(region, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV).reshape(-1, 3).astype(np.int16)
    hue, sat, val = hsv[:, 0], hsv[:, 1], hsv[:, 2]
    total = float(len(hue))

    dark = val < 50
    achromatic = (~dark) & (sat < 45)
    chromatic = (~dark) & (~achromatic)

    counts = {}
    hue_c, val_c = hue[chromatic], val[chromatic]
    bins = {
        "red": (hue_c < 8) | (hue_c >= 165),
        "orange": (hue_c >= 8) & (hue_c < 20),
        "yellow": (hue_c >= 20) & (hue_c < 34),
        "green": (hue_c >= 34) & (hue_c < 85),
        "blue": (hue_c >= 85) & (hue_c < 130),
        "purple": (hue_c >= 130) & (hue_c < 165),
    }
    for family, mask in bins.items():
        counts[family] = int(mask.sum())
    # Dim orange/red-orange paint reads as brown.
    brownish = bins["orange"] & (val_c < 130)
    counts["brown"] = int(brownish.sum())
    counts["orange"] -= counts["brown"]

    best_chroma = max(counts, key=counts.get)
    if counts[best_chroma] / total >= _CHROMATIC_SHARE:
        return best_chroma

    val_a = val[achromatic]
    achroma = {
        "black": int(dark.sum()),
        "white": int((val_a >= 185).sum()),
        "gray": int((val_a < 185).sum()),
    }
    best = max(achroma, key=achroma.get)
    if achroma[best] / total >= _MIN_WINNER_SHARE:
        return best
    return None


def color_agreement(observed: Optional[str], expected: Optional[str]) -> str:
    """'agree', 'conflict' or 'unknown' for an observed vs saved colour."""
    obs = normalize_color_name(observed)
    exp = normalize_color_name(expected)
    if not obs or not exp:
        return "unknown"
    if obs == exp:
        return "agree"
    if frozenset({obs, exp}) in _NEIGHBOURS:
        return "unknown"
    return "conflict"
