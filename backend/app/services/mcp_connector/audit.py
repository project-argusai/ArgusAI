"""Audit logging for MCP tool calls (issue #648).

Every tool call writes one append-only ``user_audit_logs`` row with action
``mcp_tool_call`` and emits a structured log line. Rows carry the key id and
prefix, the tool name, a bounded argument summary, the result count, and the
outcome. The API key itself, headers, and result bodies are never recorded.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

from app.core.database import get_db_session
from app.models.user_audit_log import AuditAction, UserAuditLog

logger = logging.getLogger(__name__)

MCP_TOOL_CALL_ACTION = AuditAction.MCP_TOOL_CALL.value
_MAX_ARG_KEYS = 8
_MAX_ARG_VALUE = 80


def summarize_arguments(arguments: Optional[Mapping[str, Any]]) -> dict:
    """Bounded, JSON-safe copy of tool arguments for the audit trail."""
    summary: dict = {}
    if not isinstance(arguments, Mapping):
        return summary
    for index, (key, value) in enumerate(arguments.items()):
        if index >= _MAX_ARG_KEYS:
            summary["_truncated"] = True
            break
        name = str(key)[:40]
        if value is None or isinstance(value, (bool, int, float)):
            summary[name] = value
        else:
            summary[name] = str(value)[:_MAX_ARG_VALUE]
    return summary


def record_tool_call(
    *,
    principal: Mapping[str, Any],
    tool: str,
    arguments: Optional[Mapping[str, Any]],
    result_count: Optional[int],
    outcome: str,
    duration_ms: int,
) -> None:
    """Persist one audit row. Failures are logged and never break the tool call."""
    details = {
        "api_key_id": principal.get("id"),
        "api_key_prefix": principal.get("prefix"),
        "tool": str(tool)[:64],
        "args": summarize_arguments(arguments),
        "result_count": result_count,
        "outcome": outcome,
        "duration_ms": duration_ms,
        "forwarded_for": principal.get("forwarded_for"),
    }
    log_fields = {f"mcp_{key}": value for key, value in details.items()}
    logger.info("MCP tool call", extra={"event_type": MCP_TOOL_CALL_ACTION, **log_fields})
    try:
        with get_db_session() as db:
            db.add(
                UserAuditLog(
                    action=MCP_TOOL_CALL_ACTION,
                    user_id=None,
                    target_user_id=None,
                    details=details,
                    ip_address=(principal.get("client_ip") or None),
                    user_agent=(principal.get("user_agent") or None),
                )
            )
            db.commit()
    except Exception:
        logger.error(
            "Failed to write MCP audit log row",
            extra={"event_type": "mcp_audit_write_failed", "tool": details["tool"]},
            exc_info=True,
        )
