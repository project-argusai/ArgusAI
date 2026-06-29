"""
Dynamic vision-model resolution for AI providers.

Provider model IDs get deprecated over time (e.g. Gemini's `gemini-1.5-flash`
returned 404, Claude's `claude-3-haiku-20240307` was retired). Hardcoding a
single model means AI silently breaks the day a model is sunset. This resolver
picks a currently-available vision-capable model for each provider, so the
system self-heals as model line-ups change.

Resolution order (per provider):
  1. explicit `override` (admin pin, e.g. a SystemSetting) — always wins
  2. dynamic query of the provider's "list models" API, filtered to a
     preference list of cheap vision-capable models (result cached per process)
  3. a current, known-good fallback constant (so AI still works if the network
     query fails)

The dynamic query uses a short timeout and is cached, so the cost is at most one
brief lookup per provider per process. Fallbacks are kept current so behavior is
correct even when the query is skipped or fails.
"""
import logging
import threading
import time
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# Preference order (substring match, best/cheapest-first) of vision-capable models.
_PREFERENCES = {
    "openai": ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o", "gpt-4.1"],
    "grok": ["grok-4.3", "grok-4", "grok-3", "grok-2-vision", "grok-vision"],
    "claude": ["claude-haiku-4-5", "claude-3-5-haiku", "claude-haiku", "claude-3-haiku"],
    "gemini": ["gemini-flash-latest", "gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash"],
}

# Exclude non-text-vision models (image generation, tts, embeddings, etc.).
_EXCLUDE_SUBSTRINGS = ("imagine", "image", "video", "tts", "embed", "embedding",
                       "transcribe", "search", "build", "audio", "realtime")

# Current, known-good defaults (verified available 2026-06). Used if the dynamic
# query fails. Gemini's `-latest` alias auto-updates and is the safest default.
_FALLBACKS = {
    "openai": "gpt-4o-mini",
    "grok": "grok-4.3",
    "claude": "claude-haiku-4-5-20251001",
    "gemini": "gemini-flash-latest",
}

_LIST_TIMEOUT_S = 5.0
_CACHE_TTL_S = 6 * 3600
_cache: dict = {}          # provider -> (model, resolved_at)
_lock = threading.Lock()


def _list_models(provider: str, api_key: str) -> List[str]:
    """Return the provider's available model IDs (raises on network/auth error)."""
    with httpx.Client(timeout=_LIST_TIMEOUT_S) as c:
        if provider == "openai":
            r = c.get("https://api.openai.com/v1/models",
                      headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]
        if provider == "grok":
            r = c.get("https://api.x.ai/v1/models",
                      headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]
        if provider == "claude":
            r = c.get("https://api.anthropic.com/v1/models",
                      headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})
            r.raise_for_status()
            return [m["id"] for m in r.json().get("data", [])]
        if provider == "gemini":
            r = c.get(f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}")
            r.raise_for_status()
            return [m["name"].replace("models/", "") for m in r.json().get("models", [])]
    return []


def _pick(provider: str, available: List[str]) -> Optional[str]:
    """Pick the best available model for a provider by preference order."""
    candidates = [m for m in available
                  if not any(x in m.lower() for x in _EXCLUDE_SUBSTRINGS)]
    for pref in _PREFERENCES.get(provider, []):
        for m in candidates:
            if pref in m:
                return m
    return None


def list_available_models(provider: str, api_key: str) -> List[str]:
    """Public helper for an admin "what models are available" view.

    Returns the vision-capable candidates (preferred ones first), or [] on error.
    """
    try:
        available = _list_models(provider, api_key)
    except Exception as e:  # noqa: BLE001 - best-effort listing
        logger.warning("model_resolver: list_available_models(%s) failed: %s", provider, e)
        return []
    candidates = [m for m in available
                  if not any(x in m.lower() for x in _EXCLUDE_SUBSTRINGS)]
    preferred = [m for pref in _PREFERENCES.get(provider, []) for m in candidates if pref in m]
    seen = set()
    ordered = [m for m in preferred + candidates if not (m in seen or seen.add(m))]
    return ordered


def resolve_model(provider: str, api_key: str, override: Optional[str] = None) -> str:
    """Resolve the model ID to use for a provider (see module docstring)."""
    if override and override.strip():
        return override.strip()

    now = time.time()
    with _lock:
        cached = _cache.get(provider)
        if cached and (now - cached[1]) < _CACHE_TTL_S:
            return cached[0]

    model = _FALLBACKS.get(provider, "")
    try:
        picked = _pick(provider, _list_models(provider, api_key))
        if picked:
            model = picked
    except Exception as e:  # noqa: BLE001 - fall back to known-good default
        logger.warning("model_resolver: dynamic resolve(%s) failed (%s); using fallback %s",
                       provider, e, model)

    with _lock:
        _cache[provider] = (model, now)
    logger.info("model_resolver: %s -> %s", provider, model)
    return model


def clear_cache() -> None:
    """Drop cached resolutions (e.g. after an admin changes the model override)."""
    with _lock:
        _cache.clear()
