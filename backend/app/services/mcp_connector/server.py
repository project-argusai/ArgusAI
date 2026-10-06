"""MCP server definition for the read-only ArgusAI connector (issue #648).

Built on the official ``mcp`` Python SDK's low-level ``Server`` so every tool
has an explicit JSON Schema allowlist (``additionalProperties: false``) that
the SDK validates before dispatch. All tools are read-only: there are no
deletes, settings changes, alert-rule edits, or camera controls.

Each call runs its ORM query in a worker thread inside one short
``get_db_session()`` block, and writes one audit row.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Mapping, Optional

import anyio
import jsonschema
import mcp.types as types
from mcp.server.lowlevel import Server

from app.core.database import get_db_session
from app.services.mcp_connector import queries
from app.services.mcp_connector.audit import record_tool_call
from app.services.mcp_connector.time_window import TimeWindowError

logger = logging.getLogger(__name__)

SERVER_NAME = "argusai"
SERVER_VERSION = "1.0.0"
PRINCIPAL_STATE_KEY = "mcp_principal"

INSTRUCTIONS = (
    "Read-only access to ArgusAI, a home security camera system. Use these tools to answer questions "
    "about what happened at home: recent_events for a timeline, event_summary for a rolled-up overview "
    "(multi-camera incidents are grouped), camera_status for cameras online/offline, package_status for "
    "deliveries, and entity_sightings for when a named person or vehicle was seen. Times are ISO 8601 with "
    "the household's UTC offset. Descriptions are AI-generated from camera frames and can be wrong; say so "
    "when it matters. thumbnail_url links are short-lived."
)

_SINCE_DESCRIPTION = (
    "Start of the window: ISO 8601 (e.g. 2026-10-06T08:00:00-05:00) or relative: 15m, 1h, 24h, 7d, 2w, "
    "'today' or 'yesterday' (household local time). Max 90 days."
)
_SINCE = {"type": "string", "maxLength": 40, "description": _SINCE_DESCRIPTION}
_CAMERA = {"type": "string", "minLength": 1, "maxLength": 100, "description": "Camera name (case-insensitive) or id"}

READ_ONLY = types.ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

TOOLS: tuple[types.Tool, ...] = (
    types.Tool(
        name="recent_events",
        title="Recent events",
        description=(
            "List recent camera events, newest first: time, camera, short AI description, detected objects, "
            "identified people/vehicles, and a short-lived thumbnail URL. Default window is the last hour."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "since": {**_SINCE, "default": "1h"},
                "camera": _CAMERA,
                "limit": {"type": "integer", "minimum": 1, "maximum": queries.MAX_LIMIT, "default": 20},
                "object_type": {"type": "string", "enum": list(queries.OBJECT_TYPES)},
            },
            "additionalProperties": False,
        },
        annotations=READ_ONLY,
    ),
    types.Tool(
        name="event_summary",
        title="What happened",
        description=(
            "Rolled-up summary of a time window: totals by camera and object, doorbell rings, packages, named "
            "visitors, and incidents (events on several cameras that belong together are grouped). Default 'today'."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "window": {**_SINCE, "default": "today"},
                "camera": _CAMERA,
            },
            "additionalProperties": False,
        },
        annotations=READ_ONLY,
    ),
    types.Tool(
        name="camera_status",
        title="Camera status",
        description="Every camera with online/offline/disabled/unknown status and its most recent event.",
        inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        annotations=READ_ONLY,
    ),
    types.Tool(
        name="package_status",
        title="Package deliveries",
        description=(
            "Package deliveries detected in a window (default 'today') with carrier when known. Pickup is "
            "best effort: ArgusAI does not confirm pickups, and the result says so."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "since": {**_SINCE, "default": "today"},
                "camera": _CAMERA,
            },
            "additionalProperties": False,
        },
        annotations=READ_ONLY,
    ),
    types.Tool(
        name="entity_sightings",
        title="Person or vehicle sightings",
        description=(
            "When a named person or vehicle (as labelled in ArgusAI) was last seen, plus sightings in the window "
            "(default last 7 days). Suggests close names when there is no match."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1, "maxLength": 100, "description": "Entity name"},
                "since": {**_SINCE, "default": "7d"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        annotations=READ_ONLY,
    ),
)

_HANDLERS: dict[str, Callable[..., tuple[dict, int]]] = {
    "recent_events": lambda db, a: queries.recent_events(
        db, since=a.get("since"), camera=a.get("camera"), limit=a.get("limit"), object_type=a.get("object_type"),
    ),
    "event_summary": lambda db, a: queries.event_summary(db, window=a.get("window"), camera=a.get("camera")),
    "camera_status": lambda db, a: queries.camera_status(db),
    "package_status": lambda db, a: queries.package_status(db, since=a.get("since"), camera=a.get("camera")),
    "entity_sightings": lambda db, a: queries.entity_sightings(
        db, name=a.get("name"), since=a.get("since"), limit=a.get("limit"),
    ),
}
TOOL_NAMES = frozenset(tool.name for tool in TOOLS)
_TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
if TOOL_NAMES != frozenset(_HANDLERS):  # pragma: no cover - import-time guard
    raise RuntimeError("every MCP tool needs exactly one read-only handler")


def _run_tool(name: str, arguments: Mapping[str, Any]) -> tuple[dict, int]:
    with get_db_session() as db:
        try:
            return _HANDLERS[name](db, arguments)
        finally:
            # Read-only: end the transaction without committing anything.
            db.rollback()


def _result(payload: dict, *, is_error: bool = False) -> types.CallToolResult:
    text = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=str)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=payload,
        isError=is_error,
    )


async def execute_tool(
    name: str,
    arguments: Optional[Mapping[str, Any]],
    principal: Optional[Mapping[str, Any]],
) -> types.CallToolResult:
    """Run one tool for an authenticated principal and audit the call."""
    if not principal or not principal.get("id"):
        # The HTTP endpoint always sets a principal; refuse if it is missing.
        return _result({"error": "unauthenticated"}, is_error=True)
    args = dict(arguments or {})
    started = time.monotonic()
    count: Optional[int] = None
    if name not in TOOL_NAMES:
        outcome = "unknown_tool"
        result = _result({"error": f"Unknown tool: {str(name)[:64]}"}, is_error=True)
    else:
        try:
            # Validated here (not by the SDK) so rejected input is audited too.
            jsonschema.validate(instance=args, schema=_TOOLS_BY_NAME[name].inputSchema)
            payload, count = await anyio.to_thread.run_sync(_run_tool, name, args)
            outcome = "ok"
            result = _result(payload)
        except jsonschema.ValidationError as exc:
            outcome = "invalid_input"
            result = _result({"error": f"Invalid arguments: {exc.message[:200]}"}, is_error=True)
        except (queries.ToolInputError, TimeWindowError) as exc:
            outcome = "invalid_input"
            result = _result({"error": str(exc)}, is_error=True)
        except Exception:
            logger.error(
                "MCP tool failed",
                extra={"event_type": "mcp_tool_error", "tool": name},
                exc_info=True,
            )
            outcome = "error"
            result = _result({"error": "ArgusAI could not read that data right now."}, is_error=True)

    duration_ms = int((time.monotonic() - started) * 1000)
    try:
        await anyio.to_thread.run_sync(
            lambda: record_tool_call(
                principal=principal,
                tool=name,
                arguments=args,
                result_count=count,
                outcome=outcome,
                duration_ms=duration_ms,
            )
        )
    except Exception:
        # record_tool_call already swallows DB errors; never surface internals.
        logger.error("MCP audit hook failed", extra={"event_type": "mcp_audit_write_failed"}, exc_info=True)
    return result


def _principal_from_context(server: Server) -> Optional[Mapping[str, Any]]:
    try:
        request = server.request_context.request
    except LookupError:
        return None
    scope = getattr(request, "scope", None) or {}
    state = scope.get("state") or {}
    principal = state.get(PRINCIPAL_STATE_KEY)
    return principal if isinstance(principal, Mapping) else None


def build_server() -> Server:
    """A fresh low-level MCP server with the read-only tool set registered."""
    server: Server = Server(SERVER_NAME, version=SERVER_VERSION, instructions=INSTRUCTIONS)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return list(TOOLS)

    @server.call_tool(validate_input=False)  # execute_tool validates and audits
    async def _call_tool(name: str, arguments: dict) -> types.CallToolResult:
        return await execute_tool(name, arguments, _principal_from_context(server))

    return server


_server: Optional[Server] = None


def get_server() -> Server:
    global _server
    if _server is None:
        _server = build_server()
    return _server
