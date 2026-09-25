"""Shared AI provider fallback order.

AIService and VisionAnalysisOrchestrator both read ``ai_provider_order`` from
``system_settings`` through this helper so they cannot drift. The setting is a
JSON list of provider names. ``anthropic`` maps to Claude and ``google`` maps
to Gemini, matching the names stored by the settings API.

Providers without a configured API key are not removed here. Callers skip
those the same way the analysis loop always has: a missing provider client
means "not configured".
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional, Sequence

from app.services.ai_types import AIProvider

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_ORDER: List[AIProvider] = [
    AIProvider.OPENAI,
    AIProvider.GROK,
    AIProvider.CLAUDE,
    AIProvider.GEMINI,
]

# Stored setting names -> enum. Keep in sync with the settings API.
_PROVIDER_NAME_MAP = {
    "openai": AIProvider.OPENAI,
    "grok": AIProvider.GROK,
    "anthropic": AIProvider.CLAUDE,
    "google": AIProvider.GEMINI,
}

# Prefer an explicit status over a bare 3-digit run that might appear in an id.
_EXPLICIT_STATUS_RE = re.compile(
    r"(?:error\s*code|status(?:_code)?|http)\s*[:=]?\s*([1-5]\d{2})\b",
    re.IGNORECASE,
)
_BARE_STATUS_RE = re.compile(r"\b([45]\d{2})\b")


def load_ai_provider_order() -> List[AIProvider]:
    """Return the effective provider order, read fresh from the database.

    Falls back to ``DEFAULT_PROVIDER_ORDER`` when the setting is missing,
    empty, or not valid JSON. Logs the effective order once (provider names
    only — never keys or request payloads).
    """
    effective = list(DEFAULT_PROVIDER_ORDER)

    try:
        from app.core.database import get_db_session
        from app.models.system_setting import SystemSetting

        with get_db_session() as db:
            order_setting = db.query(SystemSetting).filter(
                SystemSetting.key == "ai_provider_order"
            ).first()

            logger.info(
                "Provider order query result: setting exists=%s, value=%s",
                order_setting is not None,
                order_setting.value if order_setting else None,
            )
            if order_setting and order_setting.value:
                try:
                    order_list = json.loads(order_setting.value)
                    provider_order = []
                    for name in order_list:
                        mapped = _PROVIDER_NAME_MAP.get(name)
                        if mapped is not None:
                            provider_order.append(mapped)
                    if provider_order:
                        effective = provider_order
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning(
                        "Invalid provider order in settings: %s, using default",
                        exc,
                    )
    except Exception as exc:
        logger.warning(
            "Failed to load provider order from database: %s, using default",
            exc,
        )

    logger.info(
        "Using configured provider order: %s",
        [provider.value for provider in effective],
    )
    return effective


def classify_provider_error(error: Optional[str]) -> str:
    """Map a provider error to a status or error class safe to log.

    Returns a short label such as ``quota_exhausted`` or ``http_429``.
    The raw error text (which may contain response bodies) is not returned.
    """
    if not error:
        return "unknown"

    text = error.lower()
    if any(
        token in text
        for token in (
            "insufficient_quota",
            "exceeded your current quota",
            "billing",
        )
    ):
        return "quota_exhausted"
    if "timed out" in text or "timeout" in text:
        return "timeout"

    explicit = _EXPLICIT_STATUS_RE.search(error)
    if explicit:
        return f"http_{explicit.group(1)}"

    bare = _BARE_STATUS_RE.search(error)
    if bare:
        return f"http_{bare.group(1)}"

    if any(
        token in text
        for token in ("unauthorized", "authentication", "invalid api key", "permission")
    ):
        return "auth_error"

    head = error.split(":", 1)[0].strip()
    if (
        head
        and " " not in head
        and len(head) <= 80
        and (head.endswith("Error") or head.endswith("Exception"))
    ):
        return head
    return "provider_error"


def format_chain_failure(reason: str, attempts: Sequence[str]) -> str:
    """One-line failure summary: reason plus provider:class attempts."""
    attempted = ", ".join(attempts) if attempts else "none"
    return f"{reason}. attempted=[{attempted}]"
