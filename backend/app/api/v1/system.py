"""
System Settings API

Endpoints for system-level configuration and monitoring:
    - Retention policy management (GET/PUT /retention)
    - Storage monitoring (GET /storage)
    - Backup and restore (POST /backup, GET /backup/{timestamp}/download, POST /restore)
"""
from fastapi import APIRouter, HTTPException, status, Depends, File, UploadFile, Form, Header, Request, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, List, get_origin, get_args
from pydantic import BaseModel, Field
from pathlib import Path
import asyncio
import json
import logging
import tempfile
import shutil
import time


def _matches_filters(record: dict, filters: dict) -> bool:
    """Check if a rich event record matches the client's filter rules."""
    if not filters:
        return True

    # Camera filter
    cam_ids = filters.get("camera_ids")
    if cam_ids and record.get("camera_id") not in cam_ids:
        return False

    # Simple boolean flags
    for flag in ("low_confidence", "regenerated", "ai_fallback_used", "ocr_used", "entity_is_new"):
        if flag in filters:
            record_val = record.get(flag) or (record.get("entity_final") or {}).get(flag) or (record.get("entity_early") or {}).get(flag)
            if bool(record_val) != bool(filters[flag]):
                return False

    # Post-processing outcomes (e.g. "homekit_triggered", "face_processed", etc.)
    pp_filters = filters.get("post_processing", {})
    pp_summary = record.get("post_processing_summary", {})
    for key, should_be_true in pp_filters.items():
        val = pp_summary.get(key)
        if isinstance(val, dict):
            val = val.get("success", val.get("attempted", False))
        if bool(val) != bool(should_be_true):
            return False

    # Minimum AI confidence
    min_conf = filters.get("min_confidence")
    if min_conf is not None:
        conf = record.get("ai_confidence")
        if conf is None or conf < min_conf:
            return False

    # Allowed providers
    providers = filters.get("providers")
    if providers and record.get("provider") not in providers:
        return False

    return True


def _filter_hot_update(record: dict, filters: dict) -> Optional[dict]:
    """Filter a hot_update record according to client preferences (used by both SSE and WS).

    Supports rich filtering on the hot lists themselves:
      - camera_ids, min_camera_count, min_camera_score
      - entity_types, entity_ids, min_score, entity_is_new
    """
    if not record or record.get("type") != "hot_update":
        return None

    hot_cameras = record.get("hot_cameras", []) or []
    top_entities = record.get("top_recent_entities", []) or []

    # Camera filters
    cam_ids = filters.get("camera_ids")
    if cam_ids:
        if not isinstance(cam_ids, (list, set)):
            cam_ids = [cam_ids]
        hot_cameras = [c for c in hot_cameras if c.get("camera_id") in cam_ids]

    min_cam_count = filters.get("min_camera_count")
    if min_cam_count is not None:
        hot_cameras = [c for c in hot_cameras if c.get("count", 0) >= min_cam_count]

    min_cam_score = filters.get("min_camera_score")
    if min_cam_score is not None:
        hot_cameras = [c for c in hot_cameras if (c.get("score") or 0) >= min_cam_score]

    # Entity filters
    ent_types = filters.get("entity_types")
    if ent_types:
        if not isinstance(ent_types, (list, set)):
            ent_types = [ent_types]
        top_entities = [e for e in top_entities if e.get("type") in ent_types]

    ent_ids = filters.get("entity_ids")
    if ent_ids:
        if not isinstance(ent_ids, (list, set)):
            ent_ids = [ent_ids]
        top_entities = [e for e in top_entities if e.get("entity_id") in ent_ids]

    min_score = filters.get("min_score")
    if min_score is not None:
        top_entities = [e for e in top_entities if (e.get("score") or 0) >= min_score]

    if filters.get("entity_is_new") is True:
        top_entities = [e for e in top_entities if e.get("is_new")]

    filtered = dict(record)
    filtered["hot_cameras"] = hot_cameras
    filtered["top_recent_entities"] = top_entities

    return filtered


from app.schemas.system import (
    RetentionPolicyUpdate,
    RetentionPolicyResponse,
    StorageResponse,
    SystemSettings,
    SystemSettingsUpdate,
    CostCapStatus,
    AIResilienceResponse,
    CircuitBreakerConfigSchema,
    CircuitBreakerStatusResponse,
)
from app.services.backup_service import BackupResult, RestoreResult, BackupInfo, ValidationResult
from app.services.service_container import container
from app.core.database import get_db
from app.models.system_setting import SystemSetting
from app.models.user import User, UserRole
from app.api.v1.auth import get_current_user
from app.utils.encryption import encrypt_password, decrypt_password, mask_sensitive, is_encrypted
from app.core.config import settings

def require_debug_access(
    request: Request,
    current_user: User = Depends(get_current_user),
    x_debug_token: Optional[str] = Header(None, alias="X-Debug-Token")
) -> User:
    """
    Dependency that protects debug endpoints.

    Requirements when DEBUG_ENDPOINTS_ENABLED=true:
    - User must be an admin
    - If DEBUG_TOKEN is configured in settings, the X-Debug-Token header must match it

    This significantly raises the bar for accidental or malicious use of debug endpoints.
    """
    client_ip = request.client.host if request and request.client else None

    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access debug endpoint",
            extra={
                "event_type": "debug_access_denied",
                "reason": "not_admin",
                "user_id": current_user.id,
                "username": current_user.username,
                "ip_address": client_ip,
            }
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to access debug endpoints"
        )

    if settings.DEBUG_TOKEN:
        if x_debug_token != settings.DEBUG_TOKEN:
            logger.warning(
                "Debug endpoint access denied - invalid debug token",
                extra={
                    "event_type": "debug_access_denied",
                    "reason": "invalid_debug_token",
                    "user_id": current_user.id,
                    "username": current_user.username,
                    "ip_address": client_ip,
                }
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or missing X-Debug-Token header"
            )

    # Log successful access
    logger.info(
        "Debug endpoint accessed",
        extra={
            "event_type": "debug_endpoint_accessed",
            "user_id": current_user.id,
            "username": current_user.username,
            "role": current_user.role.value if hasattr(current_user.role, 'value') else current_user.role,
            "ip_address": client_ip,
        }
    )

    return current_user

logger = logging.getLogger(__name__)

# Keys that contain sensitive data and should be encrypted
SENSITIVE_SETTING_KEYS = [
    "settings_primary_api_key",
    "settings_fallback_api_key",
    "ai_api_key_openai",
    "ai_api_key_claude",
    "ai_api_key_gemini",
    "ai_api_key_grok",  # Story P2-5.2: xAI Grok API key
    "settings_tunnel_token",  # Story P11-1.1: Cloudflare Tunnel token
    "smtp_password",  # Story P16-1.7: SMTP password for email invitations
]

router = APIRouter(
    prefix="/system",
    tags=["system"]
)


# Debug endpoints - only registered when DEBUG_ENDPOINTS_ENABLED=true (Story P14-1.2)
# SECURITY: These endpoints expose sensitive internal information.
# By not registering them at all when disabled (vs. auth check), we return
# 404 instead of 401/403, avoiding confirmation that the endpoints exist.
if settings.DEBUG_ENDPOINTS_ENABLED:
    logger.warning(
        "Debug endpoints enabled - protected by admin role + optional DEBUG_TOKEN",
        extra={"event_type": "debug_endpoints_enabled"}
    )

    @router.get("/debug/ai-keys", include_in_schema=False)
    def debug_ai_keys(
        request: Request,
        current_user: User = Depends(require_debug_access),
        db: Session = Depends(get_db)
    ):
        """Debug endpoint to check if AI keys are saved in database.

        Requires:
        - DEBUG_ENDPOINTS_ENABLED=true in settings
        - User must be an admin
        - X-Debug-Token header must match DEBUG_TOKEN (if configured)
        """
        keys_to_check = [
            'ai_api_key_openai',
            'ai_api_key_claude',
            'ai_api_key_gemini',
            'settings_primary_api_key',
            'settings_primary_model',
        ]

        results = {}
        accessed_keys = []

        for key in keys_to_check:
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if setting:
                value = setting.value
                if value.startswith('encrypted:'):
                    results[key] = f"encrypted (length: {len(value)})"
                elif value.startswith('****'):
                    results[key] = f"masked: {value}"
                else:
                    results[key] = f"plaintext (first 4 chars): {value[:4]}... (length: {len(value)})"
                accessed_keys.append(key)
            else:
                results[key] = "NOT FOUND"

        # Audit log - what was actually accessed
        logger.info(
            "Debug endpoint accessed: AI keys",
            extra={
                "event_type": "debug_ai_keys_accessed",
                "user_id": current_user.id,
                "username": current_user.username,
                "keys_queried": accessed_keys,
                "results_summary": results,
            }
        )

        return results

    @router.get("/debug/ai-processing-stats", include_in_schema=False)
    def debug_ai_processing_stats(
        request: Request,
        current_user: User = Depends(require_debug_access),
    ):
        """Debug endpoint returning current runtime stats from the AIProcessingCoordinator.

        Returns counters for processed events, fallbacks, context usage, OCR,
        low confidence descriptions, regenerations, etc.

        Requires:
        - DEBUG_ENDPOINTS_ENABLED=true
        - Admin role
        - X-Debug-Token (if configured)
        """
        coordinator = container.ai_processing_coordinator
        stats = coordinator.get_processing_stats()

        logger.info(
            "Debug endpoint accessed: AI processing stats",
            extra={
                "event_type": "debug_ai_processing_stats_accessed",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )

        return {
            "status": "ok",
            "coordinator": "AIProcessingCoordinator",
            "stats": stats,
            "note": "These are lightweight in-memory counters. Use Prometheus (/metrics) for long-term observability.",
        }

    @router.get("/debug/network", include_in_schema=False)
    def debug_network_test(request: Request, current_user: User = Depends(require_debug_access)):
        """Debug endpoint to test network connectivity from server context.

        Requires admin role + optional X-Debug-Token header.
        WARNING: This endpoint contains hardcoded internal network details.
        """
        import socket
        import ssl

        results = {}
        host = "10.0.1.254"
        port = 7441

        logger.info(
            "Debug endpoint accessed: Network test",
            extra={
                "event_type": "debug_network_test_accessed",
                "user_id": current_user.id,
                "username": current_user.username,
                "target_host": host,
                "target_port": port,
            }
        )

        # Test 1: Raw socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, port))
            results["tcp_connect"] = "success"

            # Test 2: SSL wrap
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            ssock = context.wrap_socket(sock, server_hostname=host)
            results["ssl_wrap"] = f"success - {ssock.cipher()[0]}"
            ssock.close()
        except Exception as e:
            results["socket_error"] = f"{type(e).__name__}: {e}"

        # Test 3: PyAV
        try:
            import av
            url = "rtsps://homebridge:2003Isaac@10.0.1.254:7441/5e90Pa1x8zldOgmF?enableSrtp"
            container = av.open(url, options={'rtsp_transport': 'tcp'}, timeout=10)
            results["pyav_connect"] = f"success - {len(container.streams)} streams"
            container.close()
        except Exception as e:
            results["pyav_error"] = f"{type(e).__name__}: {e}"

        return results
else:
    logger.debug(
        "Debug endpoints disabled (default secure configuration)",
        extra={"event_type": "debug_endpoints_disabled"}
    )


@router.get("/ai-processing-stats")
def get_ai_processing_stats(
    current_user: User = Depends(get_current_user),
):
    """Admin endpoint returning current runtime stats from the AIProcessingCoordinator.

    Always available to admins (does not require DEBUG_ENDPOINTS_ENABLED).
    Returns lightweight in-memory counters for processed events, fallbacks,
    context usage, OCR, low-confidence descriptions, regenerations, etc.

    Requires admin role.
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access AI processing stats",
            extra={
                "event_type": "admin_ai_processing_stats_access_denied",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    coordinator = container.ai_processing_coordinator
    stats = coordinator.get_processing_stats()

    logger.info(
        "Admin accessed AI processing stats",
        extra={
            "event_type": "admin_ai_processing_stats_accessed",
            "user_id": current_user.id,
            "username": current_user.username,
        },
    )

    return {
        "status": "ok",
        "coordinator": "AIProcessingCoordinator",
        "stats": stats,
        "source": "in-memory counters (Prometheus /metrics recommended for historical data)",
    }


@router.get("/ai-processing-snapshot")
def get_ai_processing_snapshot(
    limit: int = 30,
    current_user: User = Depends(get_current_user),
):
    """Admin endpoint returning a live snapshot of the AIProcessingCoordinator.

    Combines current stats + recent processing activity in one call.
    Very useful for real-time dashboards and debugging.

    Requires admin role.
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access AI processing snapshot",
            extra={
                "event_type": "admin_ai_processing_snapshot_access_denied",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    coordinator = container.ai_processing_coordinator
    stats = coordinator.get_processing_stats()
    recent = coordinator.get_recent_activity(limit=limit)
    hot_cameras = coordinator.get_hot_cameras(limit=limit)
    top_entities = coordinator.get_top_recent_entities(limit=limit)

    logger.info(
        "Admin accessed AI processing snapshot",
        extra={
            "event_type": "admin_ai_processing_snapshot_accessed",
            "user_id": current_user.id,
            "username": current_user.username,
            "limit": limit,
        },
    )

    return {
        "status": "ok",
        "coordinator": "AIProcessingCoordinator",
        "stats": stats,
        "recent_activity": recent,
        "recent_count": len(recent),
        "hot_cameras": hot_cameras,
        "top_recent_entities": top_entities,
    }


@router.get("/ai-processing-recent")
def get_ai_processing_recent(
    limit: int = Query(50, description="Maximum number of recent processing records to return (max 100)"),
    current_user: User = Depends(get_current_user),
):
    """Admin endpoint returning the most recent AI processing activity records.

    Returns the rich per-event records produced by AIProcessingCoordinator,
    including AI economics (cost, tokens, latency, provider, confidence, prompt variant),
    entity linking results (early + final), post-processing outcomes,
    context usage, OCR/fallback/regeneration flags, cost-cap skips, and errors.

    This is the dedicated, lightweight way to fetch the recent activity ring buffer
    (as opposed to the combined snapshot endpoint).

    Requires admin role.
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access AI processing recent activity",
            extra={
                "event_type": "admin_ai_processing_recent_access_denied",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    # Cap the limit to prevent abuse
    safe_limit = max(1, min(limit, 100))

    coordinator = container.ai_processing_coordinator
    recent = coordinator.get_recent_activity(limit=safe_limit)

    logger.info(
        "Admin accessed AI processing recent activity",
        extra={
            "event_type": "admin_ai_processing_recent_accessed",
            "user_id": current_user.id,
            "username": current_user.username,
            "limit": safe_limit,
            "returned": len(recent),
        },
    )

    return {
        "status": "ok",
        "coordinator": "AIProcessingCoordinator",
        "recent_activity": recent,
        "count": len(recent),
        "limit": safe_limit,
    }


@router.get("/ai-cost-trends")
def get_ai_cost_trends(
    days_back: int = Query(30, description="Number of days of history to include (1-365)"),
    bucket: str = Query("day", description="Time granularity: 'day' or 'hour'"),
    current_user: User = Depends(get_current_user),
):
    """Admin endpoint returning aggregated AI cost and token usage trends over time.

    Pulls from the rich economics data stored by AIProcessingCoordinator
    (ai_cost, tokens_used, provider_used, response time, etc.).

    Requires admin role.
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access AI cost trends",
            extra={
                "event_type": "admin_ai_cost_trends_access_denied",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    # Basic validation
    safe_days = max(1, min(days_back, 365))
    safe_bucket = bucket if bucket in ("day", "hour") else "day"

    coordinator = container.ai_processing_coordinator
    trends = coordinator.get_ai_cost_trends(days_back=safe_days, bucket=safe_bucket)

    logger.info(
        "Admin accessed AI cost trends",
        extra={
            "event_type": "admin_ai_cost_trends_accessed",
            "user_id": current_user.id,
            "username": current_user.username,
            "days_back": safe_days,
            "bucket": safe_bucket,
            "points": len(trends),
        },
    )

    return {
        "status": "ok",
        "coordinator": "AIProcessingCoordinator",
        "trends": trends,
        "count": len(trends),
        "days_back": safe_days,
        "bucket": safe_bucket,
    }


@router.get("/ai-context-usage-stats")
def get_ai_context_usage_stats(
    days_back: int = Query(30, description="Number of days of history to include (1-365)"),
    current_user: User = Depends(get_current_user),
):
    """Admin endpoint returning context usage statistics over time.

    Shows how often context-enhanced prompts were used, average gather time,
    and breakdown by context type (entity, similar events, time patterns).

    Requires admin role.
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access AI context usage stats",
            extra={
                "event_type": "admin_ai_context_usage_stats_access_denied",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    safe_days = max(1, min(days_back, 365))

    coordinator = container.ai_processing_coordinator
    stats = coordinator.get_context_usage_stats(days_back=safe_days)

    logger.info(
        "Admin accessed AI context usage stats",
        extra={
            "event_type": "admin_ai_context_usage_stats_accessed",
            "user_id": current_user.id,
            "username": current_user.username,
            "days_back": safe_days,
        },
    )

    return {
        "status": "ok",
        "coordinator": "AIProcessingCoordinator",
        "stats": stats,
        "days_back": safe_days,
    }


@router.get("/ai-processing-hot")
def get_ai_processing_hot(
    limit: int = Query(10, description="Maximum number of items to return per list"),
    camera_ids: Optional[str] = Query(None, description="Comma-separated camera IDs"),
    entity_types: Optional[str] = Query(None, description="Comma-separated entity types"),
    entity_ids: Optional[str] = Query(None, description="Comma-separated entity IDs"),
    min_camera_count: Optional[int] = Query(None, description="Minimum event count for cameras"),
    min_camera_score: Optional[float] = Query(None, description="Minimum camera popularity score"),
    min_score: Optional[float] = Query(None, description="Minimum entity score"),
    entity_is_new: Optional[str] = Query(None, description="true/false — only new entities"),
    current_user: User = Depends(get_current_user),
):
    """Admin endpoint returning the current 'hot' cameras and top recent entities.

    Very lightweight and fast — ideal for dashboard widgets that want the
    trending items right now (with exponential decay).

    Supports the same rich per-client hot-list filtering as the hot streams:

      Camera filters: camera_ids, min_camera_count, min_camera_score
      Entity filters:  entity_types, entity_ids, min_score, entity_is_new

    Requires admin role.
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access AI processing hot data",
            extra={
                "event_type": "admin_ai_processing_hot_access_denied",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    # Build filters dict (same shape as WS + SSE)
    filters: dict = {}
    if camera_ids:
        filters["camera_ids"] = [c.strip() for c in camera_ids.split(",") if c.strip()]
    if entity_types:
        filters["entity_types"] = [t.strip() for t in entity_types.split(",") if t.strip()]
    if entity_ids:
        filters["entity_ids"] = [e.strip() for e in entity_ids.split(",") if e.strip()]
    if min_camera_count is not None:
        filters["min_camera_count"] = min_camera_count
    if min_camera_score is not None:
        filters["min_camera_score"] = min_camera_score
    if min_score is not None:
        filters["min_score"] = min_score
    if entity_is_new is not None:
        filters["entity_is_new"] = entity_is_new.lower() in ("true", "1", "yes")

    coordinator = container.ai_processing_coordinator

    # Fetch a bit more than the final limit so filtering has room to work
    raw_cameras = coordinator.get_hot_cameras(limit=max(limit, 30))
    raw_entities = coordinator.get_top_recent_entities(limit=max(limit, 30))

    record = {
        "type": "hot_update",
        "hot_cameras": raw_cameras,
        "top_recent_entities": raw_entities,
    }

    filtered = _filter_hot_update(record, filters) or {"hot_cameras": [], "top_recent_entities": []}

    # Apply final client limit after filtering
    hot_cameras = filtered["hot_cameras"][:limit]
    top_entities = filtered["top_recent_entities"][:limit]

    logger.info(
        "Admin accessed AI processing hot data",
        extra={
            "event_type": "admin_ai_processing_hot_accessed",
            "user_id": current_user.id,
            "username": current_user.username,
            "limit": limit,
            "filters": filters,
        },
    )

    return {
        "status": "ok",
        "coordinator": "AIProcessingCoordinator",
        "hot_cameras": hot_cameras,
        "top_recent_entities": top_entities,
        "filters_applied": filters,
    }


@router.get("/ai-processing-hot-stream")
async def ai_processing_hot_stream(
    camera_ids: Optional[str] = Query(None, description="Comma-separated camera IDs to include"),
    entity_types: Optional[str] = Query(None, description="Comma-separated entity types (person,vehicle,package,animal)"),
    entity_ids: Optional[str] = Query(None, description="Comma-separated entity IDs"),
    min_camera_count: Optional[int] = Query(None, description="Minimum event count for a camera to appear"),
    min_camera_score: Optional[float] = Query(None, description="Minimum popularity score for cameras"),
    min_score: Optional[float] = Query(None, description="Minimum score for entities"),
    entity_is_new: Optional[str] = Query(None, description="true/false — only return entities that are new"),
    current_user: User = Depends(get_current_user),
):
    """Admin-only Server-Sent Events (SSE) stream that only pushes hot list updates.

    Clients receive `hot_update` messages whenever the "hot cameras" or
    "top recent entities" lists change (exponential decay scoring).

    This is the lightweight counterpart to the full event stream — perfect for
    dashboard "trending now" widgets.

    Query parameters for rich per-client filtering on the hot lists themselves
    (symmetric with the hot WebSocket):

      Camera filters:
        - camera_ids: comma-separated (e.g. cam-living,cam-front)
        - min_camera_count: integer
        - min_camera_score: float

      Entity filters:
        - entity_types: comma-separated (person,vehicle,package,animal)
        - entity_ids: comma-separated
        - min_score: float (0.0–1.0+)
        - entity_is_new: "true" or "false"

    Heartbeat:
    - Server sends `{"type": "ping"}` approximately every 20 seconds.
    - Client should reply with `{"command": "pong"}` (or any message) to keep the connection alive.
    - If no activity is seen for ~60s the server will close the connection.

    Requires admin role.

    Recommended client behavior:
    - Implement exponential backoff reconnect (1s → 30s max).
    - Re-apply the same query parameters after reconnect.
    - Treat both onclose and onerror as reconnect triggers.
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access AI processing hot stream",
            extra={
                "event_type": "admin_ai_processing_hot_stream_access_denied",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    # Build a single filters dict (same shape used by the hot WebSocket)
    filters: dict = {}

    if camera_ids:
        filters["camera_ids"] = [c.strip() for c in camera_ids.split(",") if c.strip()]
    if entity_types:
        filters["entity_types"] = [t.strip() for t in entity_types.split(",") if t.strip()]
    if entity_ids:
        filters["entity_ids"] = [e.strip() for e in entity_ids.split(",") if e.strip()]

    if min_camera_count is not None:
        filters["min_camera_count"] = min_camera_count
    if min_camera_score is not None:
        filters["min_camera_score"] = min_camera_score
    if min_score is not None:
        filters["min_score"] = min_score
    if entity_is_new is not None:
        filters["entity_is_new"] = entity_is_new.lower() in ("true", "1", "yes")

    coordinator = container.ai_processing_coordinator
    queue = await coordinator.subscribe_to_new_events()

    async def event_generator():
        """Generator for the hot list stream with heartbeat support."""
        try:
            yield ": connected\n\n"

            while True:
                try:
                    record = await asyncio.wait_for(queue.get(), timeout=20)

                    if record.get("type") != "hot_update":
                        continue

                    filtered_record = _filter_hot_update(record, filters)
                    if filtered_record:
                        yield f"data: {json.dumps(filtered_record, default=str)}\n\n"

                except asyncio.TimeoutError:
                    # Send explicit JSON ping (consistent with WebSocket)
                    yield 'data: {"type": "ping"}\n\n'

                except Exception as e:
                    logger.warning(f"Error in AI processing hot stream: {e}")
                    break
        finally:
            try:
                coordinator._event_subscribers.remove(queue)
            except ValueError:
                pass

    logger.info(
        "Admin connected to AI processing hot list stream",
        extra={
            "event_type": "admin_ai_processing_hot_stream_connected",
            "user_id": current_user.id,
            "username": current_user.username,
            "filters": filters,
        },
    )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/ai-processing-stream")
async def ai_processing_stream(
    current_user: User = Depends(get_current_user),
):
    """Admin-only Server-Sent Events (SSE) stream of newly processed events.

    Each message contains the full rich record for a newly processed event
    (same structure as items returned by /ai-processing-recent).

    Requires admin role. Intended for real-time dashboards.
    """
    if current_user.role != UserRole.ADMIN:
        logger.warning(
            "Non-admin attempted to access AI processing stream",
            extra={
                "event_type": "admin_ai_processing_stream_access_denied",
                "user_id": current_user.id,
                "username": current_user.username,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    coordinator = container.ai_processing_coordinator
    queue = await coordinator.subscribe_to_new_events()

    async def event_generator():
        try:
            yield ": connected\n\n"  # initial comment to open the stream

            while True:
                try:
                    record = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"data: {json.dumps(record, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                except Exception as e:
                    logger.warning(f"Error in AI processing stream: {e}")
                    break
        finally:
            try:
                coordinator._event_subscribers.remove(queue)
            except ValueError:
                pass

    logger.info(
        "Admin connected to AI processing live stream",
        extra={
            "event_type": "admin_ai_processing_stream_connected",
            "user_id": current_user.id,
            "username": current_user.username,
        },
    )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.websocket("/ai-processing-ws")
async def ai_processing_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Bidirectional WebSocket for real-time AI event streaming + client commands.

    Supports two auth methods:
    - Normal session cookie (for browser clients)
    - Query parameter ?token=JWT (for scripts / non-browser clients)

    Heartbeat:
    - Server sends {"type": "ping"} approximately every 20 seconds.
    - Client should reply with {"command": "pong"} (or the server will close the connection after ~60s of inactivity).

    Supported client commands (send as JSON):
      {"command": "pause", "camera_id": "cam-123"}
      {"command": "resume", "camera_id": "cam-123"}
      {"command": "filter", "filters": {...}}
      {"command": "clear_filter"}
      {"command": "get_stats"}
      {"command": "ping"} / {"command": "pong"}

    Advanced filtering example:
      {"command": "filter", "filters": {
          "camera_ids": ["cam-living", "cam-front"],
          "low_confidence": true,
          "post_processing": {"homekit_triggered": true, "face_processed": true},
          "min_confidence": 70,
          "providers": ["grok", "openai"]
      }}

    Special "hot updates only" mode (useful for dashboards that only care about the hot lists):
      {"command": "filter", "filters": {"hot_updates_only": true}}

    Special server messages:
      {"type": "event", "data": {...}}           // normal processed event
      {"type": "hot_update", "hot_cameras": [...], "top_recent_entities": [...]}
      {"type": "stats", "data": {...}}
      {"type": "filter_applied", "filters": {...}}
      {"type": "ping"} / {"type": "pong"}

    Requires admin role.

    Recommended client behavior: implement exponential backoff reconnect + re-apply last filters on reconnect.
    """
    # Support query-param token for non-browser clients
    if not current_user and token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username = payload.get("sub")
            if username:
                from app.core.database import get_db_session
                with get_db_session() as db:
                    current_user = db.query(User).filter(User.username == username).first()
        except JWTError:
            pass

    if not current_user or current_user.role != UserRole.ADMIN:
        await websocket.close(code=1008, reason="Admin role required")
        return

    await websocket.accept()

    coordinator = container.ai_processing_coordinator
    queue = await coordinator.subscribe_to_new_events_ws()

    # Per-connection filter state
    websocket.active_filters = {}
    paused_cameras: set = set()
    allowed_cameras: Optional[set] = None  # None = receive all

    logger.info(
        "Admin connected to AI processing WebSocket",
        extra={
            "event_type": "admin_ai_processing_ws_connected",
            "user_id": current_user.id,
            "username": current_user.username,
        },
    )

    async def reader():
        """Reads events from the internal queue and forwards them to the client,
        while also sending periodic pings for heartbeat detection."""
        last_activity = time.time()

        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=20)
                last_activity = time.time()

                # Hot list updates (new type of message)
                if data.get("type") == "hot_update":
                    await websocket.send_json(data)
                    continue

                # Regular processed event
                camera_id = data.get("camera_id")
                if allowed_cameras is not None and camera_id not in allowed_cameras:
                    continue
                if camera_id in paused_cameras:
                    continue

                active_filters = getattr(websocket, "active_filters", {})
                hot_only = getattr(websocket, "hot_updates_only", False)

                # If client only wants hot list updates, skip regular events
                if hot_only and data.get("type") != "hot_update":
                    continue

                if active_filters and not _matches_filters(data, active_filters):
                    continue

                await websocket.send_json({"type": "event", "data": data})

            except asyncio.TimeoutError:
                # Send a server-initiated ping
                try:
                    await websocket.send_json({"type": "ping", "ts": time.time()})
                except Exception:
                    break

                # If we haven't heard anything (including pong) for a long time, close
                if time.time() - last_activity > 60:
                    break

            except Exception:
                break

        # Connection is considered dead
        try:
            await websocket.close(code=1000, reason="Heartbeat timeout")
        except Exception:
            pass

    async def writer():
        while True:
            try:
                message = await websocket.receive_json()
            except Exception:
                break

            cmd = message.get("command")

            if cmd == "pause":
                cam = message.get("camera_id")
                if cam:
                    paused_cameras.add(cam)
            elif cmd == "resume":
                cam = message.get("camera_id")
                if cam:
                    paused_cameras.discard(cam)
            elif cmd == "filter":
                filters = message.get("filters", {})
                if "camera_ids" in message and "camera_ids" not in filters:
                    filters["camera_ids"] = message["camera_ids"]

                websocket.active_filters = filters

                # Support "hot updates only" mode for clients that only want the hot lists
                if "hot_updates_only" in filters:
                    websocket.hot_updates_only = bool(filters["hot_updates_only"])

                await websocket.send_json({"type": "filter_applied", "filters": filters})
            elif cmd == "clear_filter":
                websocket.active_filters = {}
                websocket.hot_updates_only = False
                await websocket.send_json({"type": "filter_applied", "filters": {}})
            elif cmd == "get_stats":
                await websocket.send_json({
                    "type": "stats",
                    "data": coordinator.get_processing_stats()
                })
            elif cmd == "ping":
                # Client sent a ping → reply with pong
                await websocket.send_json({"type": "pong", "ts": time.time()})
            elif cmd == "pong":
                # Client responded to our ping — update last seen
                pass  # We can extend with last_pong tracking if needed later

    try:
        # Send initial stats on connect
        await websocket.send_json({
            "type": "stats",
            "data": coordinator.get_processing_stats()
        })

        await asyncio.gather(reader(), writer())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        try:
            coordinator._event_subscribers.remove(queue)
        except ValueError:
            pass


@router.websocket("/ai-processing-hot-ws")
async def ai_processing_hot_ws(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Lightweight bidirectional WebSocket that **only** streams hot list updates (`hot_update` messages).

    Ideal for dashboard widgets that only care about the current "Top Cameras" and
    "Top Recent Entities" (with exponential decay popularity scoring). This endpoint
    never sends full event records — only compact hot-list snapshots.

    Supports the same command protocol as the main AI WS (filter, pause, get_stats, ping/pong).

    Supports two auth methods:
    - Normal session cookie (for browser clients)
    - Query parameter ?token=JWT (for scripts / non-browser clients)

    Requires admin role.

    Heartbeat (strict, symmetric with main WS):
    - Server sends {"type": "ping", "ts": ...} ~every 20s when idle.
    - Client must reply with {"command": "pong"} (or any message).
    - No valid pong for ~60s → server closes with code 1000 + reason "Heartbeat timeout".

    Recommended client behavior (copy-paste ready example below):
    - Exponential backoff reconnect (1s → 30s cap).
    - Re-apply your last `filters` object after every reconnect.
    - Treat `onclose`/`onerror` as reconnect triggers.
    - Always reply promptly to pings.

    ------------------------------------------------------------------------
    Advanced per-client filtering ON THE HOT LISTS THEMSELVES
    (send via the normal filter command — these keys are specific to hot updates):

    {
      "command": "filter",
      "filters": {
        "camera_ids": ["cam-living", "cam-front"],   // only these cameras
        "min_camera_count": 5,                       // camera must appear in ≥N events
        "min_camera_score": 8.5,                     // camera popularity score threshold

        "entity_types": ["person", "vehicle"],
        "entity_ids": ["ent-uuid-123"],
        "min_score": 0.82,                           // entity similarity / popularity score
        "entity_is_new": true                        // only entities never seen before
      }
    }

    The server applies the filters to the `hot_cameras` and `top_recent_entities`
    arrays inside every `hot_update` before sending it to *this* client only.
    Other clients on the same WS can have completely different hot-list filters.

    ------------------------------------------------------------------------
    Example robust JavaScript client (heartbeat + reconnect + hot-list filters):

    ```js
    let ws;
    let reconnectAttempts = 0;
    let lastFilters = {
      // Example: only high-confidence new people + busy cameras
      entity_types: ["person"],
      entity_is_new: true,
      min_score: 0.80,
      min_camera_score: 6.0,
      min_camera_count: 3
    };
    let token = null; // set if using token auth

    function connectHotWS() {
      let url = "ws://localhost:8000/api/v1/system/ai-processing-hot-ws";
      if (token) url += `?token=${encodeURIComponent(token)}`;

      ws = new WebSocket(url);

      ws.onopen = () => {
        console.log("[HotWS] Connected");
        reconnectAttempts = 0;

        // Re-apply hot-list filters on every (re)connect
        if (lastFilters) {
          ws.send(JSON.stringify({ command: "filter", filters: lastFilters }));
        }
        ws.send(JSON.stringify({ command: "get_stats" }));
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);

        if (msg.type === "ping") {
          ws.send(JSON.stringify({ command: "pong" }));
          return;
        }

        if (msg.type === "hot_update") {
          // msg.data = { hot_cameras: [...], top_recent_entities: [...] }
          console.log("Hot lists (after your filters):", msg.data);
          // Update your Top 5 cameras / Top visitors widgets here
        } else if (msg.type === "stats") {
          console.log("Coordinator stats:", msg.data);
        } else if (msg.type === "filter_applied") {
          console.log("Hot-list filters applied for this connection:", msg.filters);
        }
      };

      ws.onclose = (event) => {
        console.warn("[HotWS] Closed", event.code, event.reason);
        if (event.code !== 1000) scheduleReconnect();
      };

      ws.onerror = () => scheduleReconnect();
    }

    function scheduleReconnect() {
      const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000) + Math.random() * 800;
      reconnectAttempts++;
      console.log(`[HotWS] Reconnecting in ${Math.round(delay)}ms (attempt ${reconnectAttempts})`);
      setTimeout(connectHotWS, delay);
    }

    connectHotWS();
    ```
    """
    if not current_user and token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username = payload.get("sub")
            if username:
                from app.core.database import get_db_session
                with get_db_session() as db:
                    current_user = db.query(User).filter(User.username == username).first()
        except JWTError:
            pass

    if not current_user or current_user.role != UserRole.ADMIN:
        await websocket.close(code=1008, reason="Admin role required")
        return

    await websocket.accept()

    coordinator = container.ai_processing_coordinator
    queue = await coordinator.subscribe_to_new_events_ws()

    # Per-connection filter state (same as main WS)
    websocket.active_filters = {}
    websocket.hot_updates_only = True  # Force hot-only mode
    paused_cameras: set = set()
    allowed_cameras: Optional[set] = None

    logger.info(
        "Admin connected to AI processing hot-only WebSocket",
        extra={
            "event_type": "admin_ai_processing_hot_ws_connected",
            "user_id": current_user.id,
            "username": current_user.username,
        },
    )

    async def reader():
        """Reads hot updates from the queue and forwards them (with per-client filtering), with strict heartbeat pings."""
        last_activity = time.time()
        last_pong = time.time()

        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=20)
                last_activity = time.time()

                if data.get("type") == "pong":
                    last_pong = time.time()
                    continue

                if data.get("type") != "hot_update":
                    continue

                active_filters = getattr(websocket, "active_filters", {})

                if active_filters:
                    filtered = _filter_hot_update(data, active_filters)
                    if not filtered:
                        continue
                    data = filtered

                await websocket.send_json({"type": "hot_update", "data": data})

            except asyncio.TimeoutError:
                # Send server-initiated ping
                try:
                    await websocket.send_json({"type": "ping", "ts": time.time()})
                except Exception:
                    break

                # Require recent pong activity (stricter than just any message)
                if time.time() - last_pong > 60:
                    break

            except Exception:
                break

        try:
            await websocket.close(code=1000, reason="Heartbeat timeout")
        except Exception:
            pass

    async def writer():
        while True:
            try:
                message = await websocket.receive_json()
            except Exception:
                break

            cmd = message.get("command")

            if cmd == "pause":
                cam = message.get("camera_id")
                if cam:
                    paused_cameras.add(cam)
            elif cmd == "resume":
                cam = message.get("camera_id")
                if cam:
                    paused_cameras.discard(cam)
            elif cmd == "filter":
                filters = message.get("filters", {})
                if "camera_ids" in message and "camera_ids" not in filters:
                    filters["camera_ids"] = message["camera_ids"]
                websocket.active_filters = filters
                await websocket.send_json({"type": "filter_applied", "filters": filters})
            elif cmd == "clear_filter":
                websocket.active_filters = {}
                websocket.hot_updates_only = True
                await websocket.send_json({"type": "filter_applied", "filters": {}})
            elif cmd == "get_stats":
                await websocket.send_json({
                    "type": "stats",
                    "data": coordinator.get_processing_stats()
                })
            elif cmd == "ping":
                await websocket.send_json({"type": "pong", "ts": time.time()})

    try:
        await websocket.send_json({
            "type": "stats",
            "data": coordinator.get_processing_stats()
        })

        await asyncio.gather(reader(), writer())
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Hot WebSocket error: {e}")
    finally:
        try:
            coordinator._event_subscribers.remove(queue)
        except ValueError:
            pass


def get_retention_policy_from_db(db: Optional[Session] = None) -> int:
    """
    Get current retention policy from system_settings table

    Args:
        db: Optional database session (creates new session if not provided)

    Returns:
        Retention days (default 30 if not set)
    """
    def _get_retention(db_session: Session) -> int:
        """Inner function to get retention policy from a session."""
        try:
            setting = db_session.query(SystemSetting).filter(
                SystemSetting.key == "data_retention_days"
            ).first()

            if setting and setting.value:
                try:
                    return int(setting.value)
                except ValueError:
                    logger.warning(f"Invalid retention policy value: {setting.value}, using default 30")
                    return 30
            else:
                # Default: 30 days
                logger.info("No retention policy set, using default 30 days")
                return 30

        except Exception as e:
            logger.error(f"Error getting retention policy: {e}", exc_info=True)
            return 30

    if db is None:
        # Create our own session with context manager for automatic cleanup
        from app.core.database import get_db_session
        with get_db_session() as db_session:
            return _get_retention(db_session)
    else:
        # Use provided session - caller manages lifecycle
        return _get_retention(db)


def set_retention_policy_in_db(retention_days: int, db: Optional[Session] = None):
    """
    Set retention policy in system_settings table

    Args:
        retention_days: Number of days to retain events
        db: Optional database session (creates new session if not provided)
    """
    def _set_retention(db_session: Session):
        """Inner function to set retention policy with a session."""
        try:
            setting = db_session.query(SystemSetting).filter(
                SystemSetting.key == "data_retention_days"
            ).first()

            if setting:
                setting.value = str(retention_days)
            else:
                setting = SystemSetting(
                    key="data_retention_days",
                    value=str(retention_days)
                )
                db_session.add(setting)

            db_session.commit()
            logger.info(f"Retention policy updated: {retention_days} days")

        except Exception as e:
            logger.error(f"Error setting retention policy: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update retention policy"
            )

    if db is None:
        # Create our own session with context manager for automatic cleanup
        from app.core.database import get_db_session
        with get_db_session() as db_session:
            _set_retention(db_session)
    else:
        # Use provided session - caller manages lifecycle
        _set_retention(db)


def calculate_next_cleanup() -> Optional[str]:
    """
    Calculate next cleanup time (2:00 AM next day)

    Returns:
        ISO 8601 timestamp of next cleanup, or None if error
    """
    try:
        now = datetime.now(timezone.utc)
        # Next 2:00 AM
        next_cleanup = now.replace(hour=2, minute=0, second=0, microsecond=0)

        # If it's already past 2:00 AM today, go to tomorrow
        if now.hour >= 2:
            next_cleanup += timedelta(days=1)

        return next_cleanup.isoformat()

    except Exception as e:
        logger.error(f"Error calculating next cleanup: {e}", exc_info=True)
        return None


@router.get("/retention", response_model=RetentionPolicyResponse)
async def get_retention_policy(db: Session = Depends(get_db)):
    """
    Get current data retention policy

    Returns current retention policy configuration including:
    - Number of days events are retained
    - Whether retention is set to forever (retention_days <= 0)
    - Next scheduled cleanup time

    **Response:**
    ```json
    {
        "retention_days": 30,
        "next_cleanup": "2025-11-18T02:00:00Z",
        "forever": false
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        retention_days = get_retention_policy_from_db(db)
        forever = retention_days <= 0
        next_cleanup = calculate_next_cleanup() if not forever else None

        return RetentionPolicyResponse(
            retention_days=retention_days,
            next_cleanup=next_cleanup,
            forever=forever
        )

    except Exception as e:
        logger.error(f"Error getting retention policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve retention policy"
        )


@router.put("/retention", response_model=RetentionPolicyResponse)
async def update_retention_policy(
    policy: RetentionPolicyUpdate,
    db: Session = Depends(get_db)
):
    """
    Update data retention policy

    Update how long events are retained before automatic cleanup.

    **Valid retention_days values:**
    - -1 or 0: Keep events forever (no automatic cleanup)
    - 7: Keep for 7 days
    - 30: Keep for 30 days (default)
    - 90: Keep for 90 days
    - 365: Keep for 1 year

    **Request Body:**
    ```json
    {
        "retention_days": 30
    }
    ```

    **Response:**
    ```json
    {
        "retention_days": 30,
        "next_cleanup": "2025-11-18T02:00:00Z",
        "forever": false
    }
    ```

    **Status Codes:**
    - 200: Success
    - 400: Invalid retention_days value
    - 500: Internal server error
    """
    try:
        # Validation is handled by Pydantic schema
        set_retention_policy_in_db(policy.retention_days, db)

        forever = policy.retention_days <= 0
        next_cleanup = calculate_next_cleanup() if not forever else None

        return RetentionPolicyResponse(
            retention_days=policy.retention_days,
            next_cleanup=next_cleanup,
            forever=forever
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating retention policy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update retention policy"
        )


@router.get("/storage", response_model=StorageResponse)
async def get_storage_info():
    """
    Get storage usage information

    Returns detailed storage statistics including:
    - Database size (SQLite file size via PRAGMA queries)
    - Thumbnails directory size (recursive calculation)
    - Total storage used
    - Number of events stored

    **Response:**
    ```json
    {
        "database_mb": 15.2,
        "thumbnails_mb": 8.5,
        "total_mb": 23.7,
        "event_count": 1234
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        cleanup_service = container.cleanup_service
        storage_info = await cleanup_service.get_storage_info()

        return StorageResponse(**storage_info)

    except Exception as e:
        logger.error(f"Error getting storage info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve storage information"
        )


# Settings key prefix for all system settings
SETTINGS_PREFIX = "settings_"


def _get_setting_from_db(db: Session, key: str, default: any = None) -> any:
    """Get a single setting value from database"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    return setting.value if setting else default


def _set_setting_in_db(db: Session, key: str, value: any):
    """Set a single setting value in database, encrypting sensitive values"""
    # Convert to string if needed
    str_value = str(value) if not isinstance(value, str) else value

    # Encrypt sensitive values (API keys)
    if key in SENSITIVE_SETTING_KEYS and str_value and not is_encrypted(str_value):
        str_value = encrypt_password(str_value)
        logger.debug(f"Encrypted sensitive setting: {key}")

    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting:
        setting.value = str_value
    else:
        setting = SystemSetting(key=key, value=str_value)
        db.add(setting)
    db.commit()


@router.get("/settings", response_model=SystemSettings)
async def get_settings(db: Session = Depends(get_db)):
    """
    Get all system settings

    Returns complete system configuration including general settings,
    AI model configuration, motion detection parameters, and data retention settings.

    **Note:** API keys are masked for security (only last 4 characters shown).

    **Response:**
    ```json
    {
        "system_name": "ArgusAI",
        "timezone": "America/Los_Angeles",
        "primary_api_key": "****abcd",
        ...
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        # Load all settings from database, use defaults if not set
        settings_dict = {}

        # Fields that contain sensitive data (API keys, tunnel token)
        sensitive_fields = ["primary_api_key", "fallback_api_key", "tunnel_token"]

        # Get all settings fields from the schema
        for field_name, field_info in SystemSettings.model_fields.items():
            db_value = _get_setting_from_db(db, f"{SETTINGS_PREFIX}{field_name}")

            if db_value is not None:
                # Decrypt and mask sensitive fields for response
                if field_name in sensitive_fields:
                    if is_encrypted(db_value):
                        # Decrypt to get original, then mask for display
                        try:
                            decrypted = decrypt_password(db_value)
                            settings_dict[field_name] = mask_sensitive(decrypted)
                        except ValueError:
                            settings_dict[field_name] = "****[invalid]"
                    else:
                        # Old unencrypted value - mask it
                        settings_dict[field_name] = mask_sensitive(db_value)
                # Convert string back to appropriate type
                elif field_info.annotation == bool:
                    settings_dict[field_name] = db_value.lower() in ('true', '1', 'yes')
                elif field_info.annotation == int:
                    settings_dict[field_name] = int(db_value)
                elif field_info.annotation == float:
                    settings_dict[field_name] = float(db_value)
                # Story P8-2.3: Handle Literal types with integer values
                elif get_origin(field_info.annotation) is Literal:
                    literal_args = get_args(field_info.annotation)
                    if literal_args and all(isinstance(arg, int) for arg in literal_args):
                        settings_dict[field_name] = int(db_value)
                    else:
                        settings_dict[field_name] = db_value
                else:
                    settings_dict[field_name] = db_value
            else:
                # Use default from schema
                if field_info.default is not None:
                    settings_dict[field_name] = field_info.default

        return SystemSettings(**settings_dict)

    except Exception as e:
        logger.error(f"Error getting settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve settings"
        )


@router.put("/settings", response_model=SystemSettings)
async def update_settings(
    settings_update: SystemSettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    Update system settings (partial update)

    Accepts partial updates - only provided fields will be updated.
    Automatically handles type conversion and validation.

    **Request Body:**
    ```json
    {
        "system_name": "My Custom Name",
        "motion_sensitivity": 75
    }
    ```

    **Response:**
    Returns complete updated settings object.

    **Status Codes:**
    - 200: Success
    - 400: Validation error
    - 500: Internal server error
    """
    try:
        # Update only provided fields
        update_data = settings_update.model_dump(exclude_unset=True)

        # Fields that should be saved WITHOUT the settings_ prefix
        # These are read directly by AI service (Story P2-5.2, P2-5.3)
        # and cost cap service (Story P3-7.3)
        no_prefix_fields = {
            'ai_api_key_openai',
            'ai_api_key_grok',
            'ai_api_key_claude',
            'ai_api_key_gemini',
            'ai_provider_order',
            'ai_daily_cost_cap',   # Story P3-7.3
            'ai_monthly_cost_cap',  # Story P3-7.3
            'store_analysis_frames',  # Story P3-7.5
            # Story P4-3.4: Context-Enhanced AI Prompts Settings
            'enable_context_enhanced_prompts',
            'context_ab_test_percentage',
            'context_similarity_threshold',
            'context_time_window_days',
            # Story P4-7.3: Anomaly Detection Settings
            'anomaly_low_threshold',
            'anomaly_high_threshold',
            'anomaly_enabled',
            # Story P4-8.1: Face Recognition Privacy Settings
            'face_recognition_enabled',
            # Story P4-8.2: Person Matching Settings
            'person_match_threshold',
            'auto_create_persons',
            'update_appearance_on_high_match',
            # Story P4-8.3: Vehicle Recognition Settings
            'vehicle_recognition_enabled',
            'vehicle_match_threshold',
            'auto_create_vehicles',
        }

        for field_name, value in update_data.items():
            if value is not None:  # Only update non-None values
                # Skip masked sensitive values (API keys, tunnel token)
                if field_name in ('primary_api_key', 'fallback_api_key', 'tunnel_token') and isinstance(value, str) and value.startswith('****'):
                    logger.debug(f"Skipping masked value for {field_name}")
                    continue

                # AI provider fields are saved without prefix (Story P2-5.2, P2-5.3)
                if field_name in no_prefix_fields:
                    _set_setting_in_db(db, field_name, value)
                    logger.info(f"Saved AI provider setting: {field_name}")
                else:
                    _set_setting_in_db(db, f"{SETTINGS_PREFIX}{field_name}", value)

        # If API key was updated (and not a masked value), also save it with provider-specific key name
        # so AI service can find it
        if 'primary_api_key' in update_data and update_data['primary_api_key']:
            api_key = update_data['primary_api_key']

            # Skip masked values (they start with ****)
            if api_key.startswith('****'):
                logger.debug("Skipping masked API key value")
            else:
                # Get the model to determine the provider
                model = update_data.get('primary_model')
                if not model:
                    # Get current model from database
                    model_setting = _get_setting_from_db(db, f"{SETTINGS_PREFIX}primary_model")
                    model = model_setting or 'gpt-4o-mini'

                # Map model to provider key name
                model_to_key = {
                    'gpt-4o-mini': 'ai_api_key_openai',
                    'claude-3-haiku': 'ai_api_key_claude',
                    'gemini-flash': 'ai_api_key_gemini',
                }
                provider_key = model_to_key.get(model)
                if provider_key:
                    _set_setting_in_db(db, provider_key, api_key)
                    logger.info(f"Saved API key for provider: {provider_key}")

        # Return complete updated settings
        return await get_settings(db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating settings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update settings"
        )


# ============================================================================
# AI API Key Management
# ============================================================================


class TestKeyRequest(BaseModel):
    """Request body for API key test endpoint"""
    provider: Literal["openai", "anthropic", "google", "grok"] = Field(
        ..., description="AI provider to test"
    )
    api_key: str = Field(..., min_length=1, description="API key to test")


class TestKeyResponse(BaseModel):
    """Response from API key test endpoint"""
    valid: bool = Field(..., description="Whether the key is valid")
    message: str = Field(..., description="Result message")
    provider: str = Field(..., description="Provider that was tested")


@router.post("/test-key", response_model=TestKeyResponse)
async def test_api_key(request: TestKeyRequest):
    """
    Test an AI provider API key without saving it

    Makes a lightweight validation request to the specified AI provider
    to verify the API key works. The key is NOT stored.

    **Request Body:**
    ```json
    {
        "provider": "openai",
        "api_key": "sk-..."
    }
    ```

    **Response:**
    ```json
    {
        "valid": true,
        "message": "API key validated successfully",
        "provider": "openai"
    }
    ```

    **Status Codes:**
    - 200: Key validation result returned
    - 400: Invalid request
    - 500: Internal server error
    """
    try:
        provider = request.provider
        api_key = request.api_key

        # Log test attempt (masked key)
        logger.info(f"Testing API key for provider: {provider}, key: {mask_sensitive(api_key)}")

        if provider == "openai":
            valid, message = await _test_openai_key(api_key)
        elif provider == "anthropic":
            valid, message = await _test_anthropic_key(api_key)
        elif provider == "google":
            valid, message = await _test_google_key(api_key)
        elif provider == "grok":
            valid, message = await _test_grok_key(api_key)
        else:
            return TestKeyResponse(
                valid=False,
                message=f"Unknown provider: {provider}",
                provider=provider
            )

        return TestKeyResponse(
            valid=valid,
            message=message,
            provider=provider
        )

    except Exception as e:
        logger.error(f"Error testing API key: {e}", exc_info=True)
        return TestKeyResponse(
            valid=False,
            message=f"Error testing key: {str(e)}",
            provider=request.provider
        )


async def _test_openai_key(api_key: str) -> tuple[bool, str]:
    """Test OpenAI API key with a minimal request"""
    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        # Make a minimal request - list models is lightweight
        models = client.models.list()
        # If we get here, the key is valid
        return True, "OpenAI API key validated successfully"
    except openai.AuthenticationError:
        return False, "Invalid API key - authentication failed"
    except openai.RateLimitError:
        return True, "API key valid (rate limited, but authenticated)"
    except Exception as e:
        return False, f"OpenAI API error: {str(e)}"


async def _test_anthropic_key(api_key: str) -> tuple[bool, str]:
    """Test Anthropic API key with a minimal request"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        # Make a minimal message request to test the key
        # Using count_tokens is not available, so we make a small completion
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "test"}]
        )
        return True, "Anthropic API key validated successfully"
    except anthropic.AuthenticationError:
        return False, "Invalid API key - authentication failed"
    except anthropic.RateLimitError:
        return True, "API key valid (rate limited, but authenticated)"
    except Exception as e:
        return False, f"Anthropic API error: {str(e)}"


async def _test_google_key(api_key: str) -> tuple[bool, str]:
    """Test Google AI API key with a minimal request"""
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        # List models to verify the key works
        models = list(genai.list_models())
        return True, "Google AI API key validated successfully"
    except Exception as e:
        error_msg = str(e).lower()
        if "api key" in error_msg or "invalid" in error_msg or "401" in error_msg:
            return False, "Invalid API key - authentication failed"
        return False, f"Google AI API error: {str(e)}"


async def _test_grok_key(api_key: str) -> tuple[bool, str]:
    """Test xAI Grok API key with a minimal request (Story P2-5.2)"""
    try:
        import openai
        # Grok uses OpenAI-compatible API with custom base URL
        client = openai.OpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        # List models to verify the key works
        models = client.models.list()
        return True, "xAI Grok API key validated successfully"
    except openai.AuthenticationError:
        return False, "Invalid API key - authentication failed"
    except openai.RateLimitError:
        return True, "API key valid (rate limited, but authenticated)"
    except Exception as e:
        error_msg = str(e).lower()
        if "api key" in error_msg or "invalid" in error_msg or "401" in error_msg or "unauthorized" in error_msg:
            return False, "Invalid API key - authentication failed"
        return False, f"xAI Grok API error: {str(e)}"


def get_decrypted_api_key(db: Session, provider: str) -> Optional[str]:
    """
    Get decrypted API key for a specific provider from system settings

    This is used by the AI service to retrieve API keys for making requests.

    Args:
        db: Database session
        provider: AI provider name ("openai", "anthropic", "google")

    Returns:
        Decrypted API key or None if not set
    """
    # Map provider to settings key
    key_map = {
        "openai": "settings_primary_api_key",  # or specific key
        "anthropic": "settings_primary_api_key",
        "google": "settings_primary_api_key",
    }

    db_key = key_map.get(provider)
    if not db_key:
        return None

    # Get encrypted value from database
    encrypted_value = _get_setting_from_db(db, db_key)
    if not encrypted_value:
        return None

    # Decrypt if encrypted
    if is_encrypted(encrypted_value):
        try:
            return decrypt_password(encrypted_value)
        except ValueError:
            logger.error(f"Failed to decrypt API key for {provider}")
            return None
    else:
        # Return unencrypted value (legacy)
        return encrypted_value


# ============================================================================
# AI Provider Status API (Story P2-5.2)
# ============================================================================


class AIProviderStatus(BaseModel):
    """Status of AI provider configuration"""
    provider: str = Field(..., description="Provider identifier")
    configured: bool = Field(..., description="Whether API key is configured")


class AIProvidersStatusResponse(BaseModel):
    """Response listing all AI providers and their configuration status"""
    providers: List[AIProviderStatus] = Field(..., description="List of provider statuses")
    order: List[str] = Field(..., description="Provider order for fallback chain")


@router.get("/ai-providers", response_model=AIProvidersStatusResponse)
async def get_ai_providers_status(db: Session = Depends(get_db)):
    """
    Get configuration status for all AI providers

    Returns a list of all supported AI providers and whether they have
    API keys configured. This is used by the frontend to show provider
    status in the settings UI.

    **Response:**
    ```json
    {
        "providers": [
            {"provider": "openai", "configured": true},
            {"provider": "grok", "configured": false},
            {"provider": "anthropic", "configured": true},
            {"provider": "google", "configured": false}
        ]
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        # Map providers to their database key names
        provider_key_map = {
            "openai": "ai_api_key_openai",
            "grok": "ai_api_key_grok",
            "anthropic": "ai_api_key_claude",
            "google": "ai_api_key_gemini",
        }

        providers = []
        for provider_id, db_key in provider_key_map.items():
            # Check if the key exists and has a value
            setting = db.query(SystemSetting).filter(SystemSetting.key == db_key).first()
            is_configured = bool(setting and setting.value and setting.value.strip())

            providers.append(AIProviderStatus(
                provider=provider_id,
                configured=is_configured
            ))

        # Get saved provider order or use default
        order_setting = db.query(SystemSetting).filter(
            SystemSetting.key == "ai_provider_order"
        ).first()

        default_order = ["openai", "grok", "anthropic", "google"]
        if order_setting and order_setting.value:
            try:
                import json
                order = json.loads(order_setting.value)
            except (json.JSONDecodeError, TypeError):
                order = default_order
        else:
            order = default_order

        return AIProvidersStatusResponse(providers=providers, order=order)

    except Exception as e:
        logger.error(f"Error getting AI providers status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get AI providers status"
        )


# ============================================================================
# AI Provider Stats API (Story P2-5.3)
# ============================================================================


class AIProviderStatsResponse(BaseModel):
    """Response for AI provider usage statistics"""
    total_events: int = Field(..., description="Total events with provider_used set")
    events_per_provider: dict[str, int] = Field(..., description="Event count by provider")
    date_range: Literal["24h", "7d", "30d", "all"] = Field(..., description="Date range filter applied")
    time_range: dict[str, Optional[str]] = Field(..., description="Actual time range (start, end)")


@router.get("/ai-stats", response_model=AIProviderStatsResponse)
async def get_ai_provider_stats(
    date_range: Literal["24h", "7d", "30d", "all"] = "7d",
    db: Session = Depends(get_db)
):
    """
    Get AI provider usage statistics (Story P2-5.3)

    Returns a breakdown of how many events were processed by each AI provider.
    Useful for monitoring provider usage and fallback behavior.

    **Query Parameters:**
    - `date_range`: Time filter - "24h", "7d", "30d", or "all" (default: "7d")

    **Response:**
    ```json
    {
        "total_events": 1234,
        "events_per_provider": {
            "openai": 1000,
            "grok": 150,
            "claude": 75,
            "gemini": 9
        },
        "date_range": "7d",
        "time_range": {
            "start": "2025-11-28T00:00:00Z",
            "end": "2025-12-05T23:59:59Z"
        }
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    from app.models.event import Event
    from sqlalchemy import func

    try:
        # Calculate time range
        now = datetime.now(timezone.utc)
        if date_range == "24h":
            start_time = now - timedelta(hours=24)
        elif date_range == "7d":
            start_time = now - timedelta(days=7)
        elif date_range == "30d":
            start_time = now - timedelta(days=30)
        else:  # "all"
            start_time = None

        # Build query for events with provider_used set
        query = db.query(
            Event.provider_used,
            func.count(Event.id).label('count')
        ).filter(Event.provider_used.isnot(None))

        if start_time:
            query = query.filter(Event.timestamp >= start_time)

        # Group by provider
        results = query.group_by(Event.provider_used).all()

        # Build response
        events_per_provider = {}
        total = 0
        for provider, count in results:
            if provider:  # Skip None values
                events_per_provider[provider] = count
                total += count

        # Get actual time range from data
        if start_time:
            time_range_data = {
                "start": start_time.isoformat(),
                "end": now.isoformat()
            }
        else:
            # Get actual min/max from data
            min_max = db.query(
                func.min(Event.timestamp),
                func.max(Event.timestamp)
            ).filter(Event.provider_used.isnot(None)).first()
            time_range_data = {
                "start": min_max[0].isoformat() if min_max[0] else None,
                "end": min_max[1].isoformat() if min_max[1] else None
            }

        return AIProviderStatsResponse(
            total_events=total,
            events_per_provider=events_per_provider,
            date_range=date_range,
            time_range=time_range_data
        )

    except Exception as e:
        logger.error(f"Error getting AI provider stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get AI provider statistics"
        )


# ============================================================================
# AI Usage Cost Tracking API (Story P3-7.1)
# ============================================================================


from app.schemas.system import (
    AIUsageResponse,
    AIUsageByDate,
    AIUsageByCamera,
    AIUsageByProvider,
    AIUsageByMode,
    AIUsagePeriod
)
from app.models.ai_usage import AIUsage


@router.get("/ai-usage", response_model=AIUsageResponse)
async def get_ai_usage(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get AI usage and cost statistics (Story P3-7.1)

    Returns aggregated AI usage data including costs broken down by date,
    camera, provider, and analysis mode.

    **Query Parameters:**
    - `start_date`: Start date in ISO 8601 format (default: 30 days ago)
    - `end_date`: End date in ISO 8601 format (default: now)

    **Response:**
    ```json
    {
        "total_cost": 0.0523,
        "total_requests": 142,
        "period": {
            "start": "2025-11-09T00:00:00Z",
            "end": "2025-12-09T23:59:59Z"
        },
        "by_date": [...],
        "by_camera": [...],
        "by_provider": [...],
        "by_mode": [...]
    }
    ```

    **Status Codes:**
    - 200: Success
    - 400: Invalid date format
    - 500: Internal server error
    """
    from app.models.event import Event
    from app.models.camera import Camera
    from sqlalchemy import func, cast, Date

    try:
        # Parse date range (default: last 30 days)
        now = datetime.now(timezone.utc)
        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use ISO 8601 format."
                )
        else:
            end_dt = now

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use ISO 8601 format."
                )
        else:
            start_dt = now - timedelta(days=30)

        # Base query with date filter
        base_query = db.query(AIUsage).filter(
            AIUsage.timestamp >= start_dt,
            AIUsage.timestamp <= end_dt
        )

        # Get all records for aggregation
        records = base_query.all()

        # Calculate totals
        total_cost = sum(r.cost_estimate or 0.0 for r in records)
        total_requests = len(records)

        # Aggregate by date
        by_date_dict = {}
        for r in records:
            date_key = r.timestamp.strftime("%Y-%m-%d")
            if date_key not in by_date_dict:
                by_date_dict[date_key] = {"cost": 0.0, "requests": 0}
            by_date_dict[date_key]["cost"] += r.cost_estimate or 0.0
            by_date_dict[date_key]["requests"] += 1

        by_date = [
            AIUsageByDate(date=date, cost=data["cost"], requests=data["requests"])
            for date, data in sorted(by_date_dict.items(), reverse=True)
        ]

        # Aggregate by provider
        by_provider_dict = {}
        for r in records:
            provider = r.provider or "unknown"
            if provider not in by_provider_dict:
                by_provider_dict[provider] = {"cost": 0.0, "requests": 0}
            by_provider_dict[provider]["cost"] += r.cost_estimate or 0.0
            by_provider_dict[provider]["requests"] += 1

        by_provider = [
            AIUsageByProvider(provider=provider, cost=data["cost"], requests=data["requests"])
            for provider, data in sorted(by_provider_dict.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        # Aggregate by analysis mode
        by_mode_dict = {}
        for r in records:
            mode = r.analysis_mode or "unknown"
            if mode not in by_mode_dict:
                by_mode_dict[mode] = {"cost": 0.0, "requests": 0}
            by_mode_dict[mode]["cost"] += r.cost_estimate or 0.0
            by_mode_dict[mode]["requests"] += 1

        by_mode = [
            AIUsageByMode(mode=mode, cost=data["cost"], requests=data["requests"])
            for mode, data in sorted(by_mode_dict.items(), key=lambda x: x[1]["cost"], reverse=True)
        ]

        # Note: AIUsage doesn't have camera_id directly - we'd need to join through Event
        # For now, return empty list for by_camera (can be implemented if Event-AIUsage link exists)
        by_camera = []

        return AIUsageResponse(
            total_cost=round(total_cost, 6),
            total_requests=total_requests,
            period=AIUsagePeriod(
                start=start_dt.isoformat(),
                end=end_dt.isoformat()
            ),
            by_date=by_date,
            by_camera=by_camera,
            by_provider=by_provider,
            by_mode=by_mode
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting AI usage stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get AI usage statistics"
        )


# ============================================================================
# Backup and Restore API (Story 6.4, FF-007)
# ============================================================================


class BackupOptions(BaseModel):
    """Options for selective backup (FF-007)"""
    include_database: bool = Field(default=True, description="Include events, cameras, alert rules")
    include_thumbnails: bool = Field(default=True, description="Include thumbnail images")
    include_settings: bool = Field(default=True, description="Include system settings")
    include_ai_config: bool = Field(default=True, description="Include AI provider config (keys excluded)")
    include_protect_config: bool = Field(default=True, description="Include Protect controller config")

    class Config:
        json_schema_extra = {
            "example": {
                "include_database": True,
                "include_thumbnails": True,
                "include_settings": True,
                "include_ai_config": True,
                "include_protect_config": True
            }
        }


class RestoreOptions(BaseModel):
    """Options for selective restore (FF-007)"""
    restore_database: bool = Field(default=True, description="Restore events, cameras, alert rules")
    restore_thumbnails: bool = Field(default=True, description="Restore thumbnail images")
    restore_settings: bool = Field(default=True, description="Restore system settings")

    class Config:
        json_schema_extra = {
            "example": {
                "restore_database": True,
                "restore_thumbnails": True,
                "restore_settings": True
            }
        }


class BackupResponse(BaseModel):
    """Response from backup creation"""
    success: bool = Field(..., description="Whether backup was successful")
    timestamp: str = Field(..., description="Backup timestamp identifier")
    size_bytes: int = Field(..., description="Backup file size in bytes")
    download_url: str = Field(..., description="URL to download the backup")
    message: str = Field(..., description="Status message")
    database_size_bytes: int = Field(default=0, description="Database size in backup")
    thumbnails_count: int = Field(default=0, description="Number of thumbnails in backup")
    thumbnails_size_bytes: int = Field(default=0, description="Thumbnails size in backup")
    settings_count: int = Field(default=0, description="Number of settings in backup")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "timestamp": "2025-01-15-14-30-00",
                "size_bytes": 15728640,
                "download_url": "/api/v1/system/backup/2025-01-15-14-30-00/download",
                "message": "Backup created successfully",
                "database_size_bytes": 10485760,
                "thumbnails_count": 150,
                "thumbnails_size_bytes": 5242880,
                "settings_count": 15
            }
        }


class RestoreResponse(BaseModel):
    """Response from restore operation"""
    success: bool = Field(..., description="Whether restore was successful")
    message: str = Field(..., description="Status message")
    events_restored: int = Field(default=0, description="Number of events restored")
    settings_restored: int = Field(default=0, description="Number of settings restored")
    thumbnails_restored: int = Field(default=0, description="Number of thumbnails restored")
    warnings: List[str] = Field(default_factory=list, description="Any warnings during restore")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Restore completed successfully",
                "events_restored": 1234,
                "settings_restored": 15,
                "thumbnails_restored": 150,
                "warnings": []
            }
        }


class BackupListItem(BaseModel):
    """Information about an available backup"""
    timestamp: str = Field(..., description="Backup timestamp identifier")
    size_bytes: int = Field(..., description="Backup file size in bytes")
    created_at: str = Field(..., description="ISO 8601 creation time")
    app_version: str = Field(..., description="App version at backup time")
    database_size_bytes: int = Field(default=0, description="Database size in backup")
    thumbnails_count: int = Field(default=0, description="Number of thumbnails")
    download_url: str = Field(..., description="URL to download")


class BackupListResponse(BaseModel):
    """Response listing available backups"""
    backups: List[BackupListItem] = Field(..., description="List of available backups")
    total_count: int = Field(..., description="Total number of backups")


class BackupContentsResponse(BaseModel):
    """Information about what's contained in a backup (FF-007)"""
    has_database: bool = Field(default=False, description="Backup includes database")
    has_thumbnails: bool = Field(default=False, description="Backup includes thumbnails")
    has_settings: bool = Field(default=False, description="Backup includes settings")
    database_size_bytes: int = Field(default=0, description="Database size in bytes")
    thumbnails_count: int = Field(default=0, description="Number of thumbnails")
    settings_count: int = Field(default=0, description="Number of settings")


class ValidationResponse(BaseModel):
    """Response from backup validation"""
    valid: bool = Field(..., description="Whether backup is valid")
    message: str = Field(..., description="Validation result message")
    app_version: Optional[str] = Field(None, description="Backup app version")
    backup_timestamp: Optional[str] = Field(None, description="Backup creation time")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    contents: Optional[BackupContentsResponse] = Field(None, description="What's in the backup (FF-007)")


@router.post("/backup", response_model=BackupResponse)
async def create_backup(options: Optional[BackupOptions] = None):
    """
    Create a system backup with optional selective components (FF-007)

    Creates a ZIP archive containing selected components:
    - **database.db**: Complete SQLite database (events, cameras, rules)
    - **thumbnails/**: All event thumbnail images
    - **settings.json**: System settings (API keys excluded for security)
    - **metadata.json**: Backup metadata (timestamp, version, file counts)

    The backup can be downloaded using the `download_url` in the response.

    **Request Body (optional):**
    ```json
    {
        "include_database": true,
        "include_thumbnails": true,
        "include_settings": true,
        "include_ai_config": true,
        "include_protect_config": true
    }
    ```

    **Response:**
    ```json
    {
        "success": true,
        "timestamp": "2025-01-15-14-30-00",
        "size_bytes": 15728640,
        "download_url": "/api/v1/system/backup/2025-01-15-14-30-00/download",
        "message": "Backup created successfully"
    }
    ```

    **Status Codes:**
    - 200: Backup created successfully
    - 507: Insufficient disk space
    - 500: Internal server error
    """
    try:
        backup_service = container.backup_service
        # Use default options if none provided
        opts = options or BackupOptions()
        result = await backup_service.create_backup(
            include_database=opts.include_database,
            include_thumbnails=opts.include_thumbnails,
            include_settings=opts.include_settings
        )

        if not result.success:
            # Check if it's a disk space issue
            if "disk space" in result.message.lower():
                raise HTTPException(
                    status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
                    detail=result.message
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result.message
            )

        return BackupResponse(
            success=result.success,
            timestamp=result.timestamp,
            size_bytes=result.size_bytes,
            download_url=result.download_url,
            message=result.message,
            database_size_bytes=result.database_size_bytes,
            thumbnails_count=result.thumbnails_count,
            thumbnails_size_bytes=result.thumbnails_size_bytes,
            settings_count=result.settings_count
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create backup: {str(e)}"
        )


@router.get("/backup/{timestamp}/download")
async def download_backup(timestamp: str):
    """
    Download a backup file

    Downloads the backup ZIP file for the specified timestamp.
    The file is streamed to support large backups.

    **Path Parameters:**
    - `timestamp`: Backup timestamp from create_backup response (e.g., "2025-01-15-14-30-00")

    **Response:**
    - Content-Type: application/zip
    - Content-Disposition: attachment; filename=liveobject-backup-{timestamp}.zip

    **Status Codes:**
    - 200: Backup file streamed
    - 404: Backup not found
    """
    try:
        backup_service = container.backup_service
        zip_path = backup_service.get_backup_path(timestamp)

        if not zip_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backup not found: {timestamp}"
            )

        filename = f"liveobject-backup-{timestamp}.zip"

        return FileResponse(
            path=zip_path,
            media_type="application/zip",
            filename=filename,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download backup: {str(e)}"
        )


@router.get("/backup/list", response_model=BackupListResponse)
async def list_backups():
    """
    List all available backups

    Returns a list of all backup files with metadata, sorted by timestamp (newest first).

    **Response:**
    ```json
    {
        "backups": [
            {
                "timestamp": "2025-01-15-14-30-00",
                "size_bytes": 15728640,
                "created_at": "2025-01-15T14:30:00Z",
                "app_version": "1.0.0",
                "download_url": "/api/v1/system/backup/2025-01-15-14-30-00/download"
            }
        ],
        "total_count": 1
    }
    ```

    **Status Codes:**
    - 200: List retrieved successfully
    - 500: Internal server error
    """
    try:
        backup_service = container.backup_service
        backups = backup_service.list_backups()

        backup_items = [
            BackupListItem(
                timestamp=b.timestamp,
                size_bytes=b.size_bytes,
                created_at=b.created_at,
                app_version=b.app_version,
                database_size_bytes=b.database_size_bytes,
                thumbnails_count=b.thumbnails_count,
                download_url=b.download_url
            )
            for b in backups
        ]

        return BackupListResponse(
            backups=backup_items,
            total_count=len(backup_items)
        )

    except Exception as e:
        logger.error(f"Error listing backups: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list backups: {str(e)}"
        )


@router.post("/backup/validate", response_model=ValidationResponse)
async def validate_backup(file: UploadFile = File(...)):
    """
    Validate a backup file before restore

    Checks the backup ZIP file for:
    - Valid ZIP format
    - Required files present (database.db, metadata.json)
    - Metadata format and version compatibility

    **Request:**
    - Content-Type: multipart/form-data
    - Field: file (ZIP file)

    **Response:**
    ```json
    {
        "valid": true,
        "message": "Backup is valid",
        "app_version": "1.0.0",
        "backup_timestamp": "2025-01-15T14:30:00Z",
        "warnings": ["Backup from version 0.9.0, current version is 1.0.0"]
    }
    ```

    **Status Codes:**
    - 200: Validation result returned
    - 400: Invalid file format
    - 500: Internal server error
    """
    try:
        # Check file type
        if not file.filename or not file.filename.endswith('.zip'):
            return ValidationResponse(
                valid=False,
                message="File must be a ZIP archive"
            )

        # Save to temp file for validation
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            backup_service = container.backup_service
            result = backup_service.validate_backup(tmp_path)

            # FF-007: Include backup contents info
            contents = None
            if result.contents:
                contents = BackupContentsResponse(
                    has_database=result.contents.has_database,
                    has_thumbnails=result.contents.has_thumbnails,
                    has_settings=result.contents.has_settings,
                    database_size_bytes=result.contents.database_size_bytes,
                    thumbnails_count=result.contents.thumbnails_count,
                    settings_count=result.contents.settings_count
                )

            return ValidationResponse(
                valid=result.valid,
                message=result.message,
                app_version=result.app_version,
                backup_timestamp=result.backup_timestamp,
                warnings=result.warnings or [],
                contents=contents
            )
        finally:
            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

    except Exception as e:
        logger.error(f"Error validating backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate backup: {str(e)}"
        )


@router.post("/restore", response_model=RestoreResponse)
async def restore_from_backup(
    file: UploadFile = File(...),
    restore_database: bool = Form(default=True),
    restore_thumbnails: bool = Form(default=True),
    restore_settings: bool = Form(default=True)
):
    """
    Restore system from a backup file with selective components (FF-007)

    **WARNING: This operation may replace existing data based on selected components!**

    Process:
    1. Validates the backup file
    2. Stops background tasks (camera capture, event processing)
    3. Creates a backup of current database (if restoring database)
    4. Replaces selected components (database, thumbnails, settings)
    5. Restarts background tasks

    **Request:**
    - Content-Type: multipart/form-data
    - Field: file (ZIP file)
    - Field: restore_database (boolean, default true)
    - Field: restore_thumbnails (boolean, default true)
    - Field: restore_settings (boolean, default true)

    **Response:**
    ```json
    {
        "success": true,
        "message": "Restore completed successfully",
        "events_restored": 1234,
        "settings_restored": 15,
        "thumbnails_restored": 150,
        "warnings": []
    }
    ```

    **Status Codes:**
    - 200: Restore completed successfully
    - 400: Invalid backup file
    - 500: Restore failed
    """
    try:
        # Check file type
        if not file.filename or not file.filename.endswith('.zip'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be a ZIP archive"
            )

        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            backup_service = container.backup_service

            # Validate first
            validation = backup_service.validate_backup(tmp_path)
            if not validation.valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid backup: {validation.message}"
                )

            # Get callbacks for stopping/starting background tasks
            # These are imported from main.py patterns but we'll handle in-process
            async def stop_tasks():
                """Stop background tasks for restore"""
                # Import here to avoid circular imports
                from app.api.v1.cameras import camera_service
                from app.services.event_processor import shutdown_event_processor

                try:
                    camera_service.stop_all_cameras(timeout=5.0)
                    await shutdown_event_processor(timeout=10.0)
                except Exception as e:
                    logger.warning(f"Error stopping tasks: {e}")

            async def start_tasks():
                """Restart background tasks after restore"""
                from app.api.v1.cameras import camera_service
                from app.services.event_processor import initialize_event_processor
                from app.core.database import get_db_session
                from app.models.camera import Camera

                try:
                    await initialize_event_processor()

                    # Restart enabled cameras
                    with get_db_session() as db:
                        enabled_cameras = db.query(Camera).filter(Camera.is_enabled == True).all()
                        for camera in enabled_cameras:
                            camera_service.start_camera(camera)
                except Exception as e:
                    logger.warning(f"Error restarting tasks: {e}")

            # Perform restore with selective options (FF-007)
            result = await backup_service.restore_from_backup(
                tmp_path,
                stop_tasks_callback=stop_tasks,
                start_tasks_callback=start_tasks,
                restore_database=restore_database,
                restore_thumbnails=restore_thumbnails,
                restore_settings=restore_settings
            )

            if not result.success:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=result.message
                )

            return RestoreResponse(
                success=result.success,
                message=result.message,
                events_restored=result.events_restored,
                settings_restored=result.settings_restored,
                thumbnails_restored=result.thumbnails_restored,
                warnings=result.warnings or []
            )

        finally:
            # Cleanup temp file
            tmp_path.unlink(missing_ok=True)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore failed: {str(e)}"
        )


@router.delete("/backup/{timestamp}")
async def delete_backup(timestamp: str):
    """
    Delete a specific backup

    Permanently removes the backup file for the specified timestamp.

    **Path Parameters:**
    - `timestamp`: Backup timestamp (e.g., "2025-01-15-14-30-00")

    **Response:**
    ```json
    {
        "message": "Backup deleted successfully"
    }
    ```

    **Status Codes:**
    - 200: Backup deleted
    - 404: Backup not found
    """
    try:
        backup_service = container.backup_service
        deleted = backup_service.delete_backup(timestamp)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Backup not found: {timestamp}"
            )

        return {"message": "Backup deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting backup: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete backup: {str(e)}"
        )


# Story P3-7.3: Cost Cap Status Endpoint
from app.schemas.system import CostCapStatus as CostCapStatusSchema


@router.get("/ai-cost-status", response_model=CostCapStatusSchema)
async def get_ai_cost_status(db: Session = Depends(get_db)):
    """
    Get current AI cost cap status (Story P3-7.3)

    Returns current daily and monthly costs, caps, percentages, and pause status.

    **Response:**
    ```json
    {
        "daily_cost": 0.75,
        "daily_cap": 1.00,
        "daily_percent": 75.0,
        "monthly_cost": 12.50,
        "monthly_cap": 20.00,
        "monthly_percent": 62.5,
        "is_paused": false,
        "pause_reason": null
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    try:
        cost_cap_service = container.cost_cap_service
        cap_status = cost_cap_service.get_cap_status(db, use_cache=False)

        return CostCapStatusSchema(
            daily_cost=cap_status.daily_cost,
            daily_cap=cap_status.daily_cap,
            daily_percent=cap_status.daily_percent,
            monthly_cost=cap_status.monthly_cost,
            monthly_cap=cap_status.monthly_cap,
            monthly_percent=cap_status.monthly_percent,
            is_paused=cap_status.is_paused,
            pause_reason=cap_status.pause_reason
        )

    except Exception as e:
        logger.error(f"Error getting AI cost status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve AI cost status"
        )


# =============================================================================
# AI Resilience / Circuit Breaker Management (Phase A - A.5)
# =============================================================================

@router.get("/ai-resilience", response_model=AIResilienceResponse)
async def get_ai_resilience_status(db: Session = Depends(get_db)):
    """
    Get current circuit breaker configuration and live runtime state
    for all AI providers + global default.

    Used by the AI Resilience settings page.
    """
    try:
        # AI provider wiring (incl. the resilience service + circuit breakers) is
        # lazy — it only runs on the first AI processing call (event_processor,
        # reanalyze, etc.), not at startup. A freshly-restarted process that has
        # not yet processed an AI event would otherwise report an empty stub.
        # Ensure it's configured so admins see real circuit-breaker state.
        if container.ai_service.resilience_service is None:
            await container.ai_service.load_api_keys_from_db(db)
        return container.ai_service.get_ai_resilience_status(db)
    except Exception as e:
        logger.error(f"Failed to get AI resilience status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve AI resilience status"
        )


@router.put("/ai-resilience/{provider}", response_model=CircuitBreakerStatusResponse)
async def update_ai_resilience_config(
    provider: str,
    config: CircuitBreakerConfigSchema,
    db: Session = Depends(get_db)
):
    """
    Update circuit breaker configuration for a provider (or 'default').
    Uses full object replacement.
    """
    valid = ["default", "openai", "grok", "claude", "gemini"]
    if provider not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Must be one of {valid}"
        )

    try:
        return container.ai_service.update_circuit_breaker_config(provider, config.model_dump(), db)
    except Exception as e:
        logger.error(f"Failed to update circuit breaker for {provider}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration for {provider}"
        )


_AI_MODEL_PROVIDERS = ["openai", "grok", "claude", "gemini"]


@router.get("/ai-models")
async def list_ai_models(db: Session = Depends(get_db)):
    """List, per provider: whether it's configured, the currently-active model,
    any admin model override, and the models the provider currently offers.

    Powers the AI settings "choose a model" UI so an operator can pick from what
    is actually available rather than relying on a hardcoded (and deprecating)
    model id. Querying live model lists takes a few seconds (admin, on-demand).
    """
    from app.utils.encryption import decrypt_password
    from app.models.system_setting import SystemSetting
    from app.services.ai_providers.model_resolver import list_available_models

    # Ensure providers are configured so we can report the active model.
    if container.ai_service.resilience_service is None or not container.ai_service.providers:
        try:
            await container.ai_service.load_api_keys_from_db(db)
        except Exception as e:
            logger.warning(f"list_ai_models: provider configuration failed: {e}")

    wanted = ([f"ai_api_key_{p}" for p in _AI_MODEL_PROVIDERS]
              + [f"settings_{p}_model" for p in _AI_MODEL_PROVIDERS])
    rows = {r.key: r.value for r in
            db.query(SystemSetting).filter(SystemSetting.key.in_(wanted)).all()}

    active = {}
    try:
        for prov_enum, prov in container.ai_service.providers.items():
            active[prov_enum.value] = getattr(prov, "model_name", None) or getattr(prov, "model", None)
    except Exception:
        pass

    providers = []
    for p in _AI_MODEL_PROVIDERS:
        enc = rows.get(f"ai_api_key_{p}")
        key = decrypt_password(enc) if enc else None
        providers.append({
            "provider": p,
            "configured": bool(key),
            "active_model": active.get(p),
            "override": rows.get(f"settings_{p}_model") or None,
            "available_models": list_available_models(p, key) if key else [],
        })
    return {"providers": providers}


@router.put("/ai-models/{provider}")
async def set_ai_model(provider: str, payload: dict, db: Session = Depends(get_db)):
    """Pin a provider's model, or clear the pin to revert to dynamic resolution.

    Body: {"model": "<model-id>"} to pin, or {"model": null} to clear.
    """
    if provider not in _AI_MODEL_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Must be one of {_AI_MODEL_PROVIDERS}",
        )
    from app.models.system_setting import SystemSetting
    from app.services.ai_providers.model_resolver import clear_cache

    model = (payload or {}).get("model")
    key = f"settings_{provider}_model"
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if model:
        if row:
            row.value = model
        else:
            db.add(SystemSetting(key=key, value=model))
    elif row:
        db.delete(row)
    db.commit()

    # Drop cached resolutions and reconfigure so the change takes effect now.
    clear_cache()
    try:
        await container.ai_service.load_api_keys_from_db(db)
    except Exception as e:
        logger.warning(f"set_ai_model: reconfigure failed: {e}")

    return {"provider": provider, "model": model or None,
            "status": "pinned" if model else "cleared (dynamic resolution)"}


@router.post("/ai-resilience/{provider}/reset")
async def reset_ai_circuit_breaker(provider: str, db: Session = Depends(get_db)):
    """Manually reset a circuit breaker to CLOSED state."""
    valid = ["default", "openai", "grok", "claude", "gemini"]
    if provider not in valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Must be one of {valid}"
        )

    try:
        container.ai_service.reset_circuit_breaker(provider)
        return {"message": f"Circuit breaker for '{provider}' has been reset to CLOSED"}
    except Exception as e:
        logger.error(f"Failed to reset circuit breaker for {provider}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset {provider}"
        )


# ============================================================================
# Delete All Data Endpoint
# ============================================================================


class DeleteDataResponse(BaseModel):
    """Response from delete all data operation"""
    deleted_count: int = Field(..., description="Number of events deleted")
    success: bool = Field(..., description="Whether deletion was successful")


@router.delete("/data", response_model=DeleteDataResponse)
async def delete_all_data(db: Session = Depends(get_db)):
    """
    Delete all event data from the system

    This permanently deletes:
    - All events and their thumbnails
    - All motion events
    - All event embeddings and feedback
    - All AI usage records

    **WARNING: This action cannot be undone!**

    **Response:**
    ```json
    {
        "deleted_count": 1234,
        "success": true
    }
    ```

    **Status Codes:**
    - 200: Data deleted successfully
    - 500: Internal server error
    """
    from app.models.event import Event
    from app.models.motion_event import MotionEvent
    from app.models.event_embedding import EventEmbedding
    from app.models.event_feedback import EventFeedback
    from app.models.recognized_entity import EntityEvent
    from app.models.event_frame import EventFrame

    try:
        # Count events before deletion
        event_count = db.query(Event).count()

        # Delete related records first (foreign key constraints)
        db.query(EventFeedback).delete()
        db.query(EventEmbedding).delete()
        db.query(EntityEvent).delete()
        db.query(EventFrame).delete()
        db.query(MotionEvent).delete()

        # Delete all events
        db.query(Event).delete()

        # Delete AI usage records
        db.query(AIUsage).delete()

        db.commit()

        # Clean up thumbnail and frame files
        import shutil
        thumbnails_dir = Path("data/thumbnails")
        frames_dir = Path("data/frames")
        videos_dir = Path("data/videos")

        for dir_path in [thumbnails_dir, frames_dir, videos_dir]:
            if dir_path.exists():
                for item in dir_path.iterdir():
                    try:
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    except Exception as e:
                        logger.warning(f"Failed to delete {item}: {e}")

        logger.info(f"Deleted all data: {event_count} events")

        return DeleteDataResponse(
            deleted_count=event_count,
            success=True
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting all data: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete data: {str(e)}"
        )


# ============================================================================
# SSL Status Endpoint (Story P9-5.1)
# ============================================================================


class SSLStatusResponse(BaseModel):
    """Response containing SSL/HTTPS configuration status"""
    ssl_enabled: bool = Field(..., description="Whether SSL is configured and enabled")
    ssl_ready: bool = Field(..., description="Whether SSL is fully operational (enabled + valid certs)")
    certificate_valid: bool = Field(default=False, description="Whether the certificate is valid")
    certificate_expires: Optional[str] = Field(None, description="Certificate expiration date (ISO 8601)")
    certificate_issuer: Optional[str] = Field(None, description="Certificate issuer name")
    certificate_subject: Optional[str] = Field(None, description="Certificate subject (CN)")
    tls_version: str = Field(default="N/A", description="Minimum TLS version configured")
    ssl_port: int = Field(default=443, description="HTTPS port")
    http_redirect: bool = Field(default=False, description="Whether HTTP to HTTPS redirect is enabled")

    class Config:
        json_schema_extra = {
            "example": {
                "ssl_enabled": True,
                "ssl_ready": True,
                "certificate_valid": True,
                "certificate_expires": "2026-12-23T00:00:00Z",
                "certificate_issuer": "Let's Encrypt Authority X3",
                "certificate_subject": "argusai.example.com",
                "tls_version": "TLSv1_2",
                "ssl_port": 443,
                "http_redirect": True
            }
        }


@router.get("/ssl-status", response_model=SSLStatusResponse)
async def get_ssl_status():
    """
    Get SSL/HTTPS configuration status (Story P9-5.1)

    Returns the current SSL configuration including certificate information
    if certificates are configured. This endpoint helps users verify their
    SSL setup and monitor certificate expiration.

    **Response:**
    ```json
    {
        "ssl_enabled": true,
        "ssl_ready": true,
        "certificate_valid": true,
        "certificate_expires": "2026-12-23T00:00:00Z",
        "certificate_issuer": "Let's Encrypt Authority X3",
        "certificate_subject": "argusai.example.com",
        "tls_version": "TLSv1_2",
        "ssl_port": 443,
        "http_redirect": true
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Internal server error
    """
    from app.core.config import settings as app_settings

    try:
        response = SSLStatusResponse(
            ssl_enabled=app_settings.SSL_ENABLED,
            ssl_ready=app_settings.ssl_ready,
            tls_version=app_settings.SSL_MIN_VERSION,
            ssl_port=app_settings.SSL_PORT,
            http_redirect=app_settings.SSL_REDIRECT_HTTP and app_settings.SSL_ENABLED
        )

        # If SSL is ready, parse certificate information
        if app_settings.ssl_ready and app_settings.SSL_CERT_FILE:
            try:
                cert_info = _parse_certificate(app_settings.SSL_CERT_FILE)
                response.certificate_valid = cert_info.get("valid", False)
                response.certificate_expires = cert_info.get("expires")
                response.certificate_issuer = cert_info.get("issuer")
                response.certificate_subject = cert_info.get("subject")
            except Exception as e:
                logger.warning(f"Failed to parse certificate: {e}")
                response.certificate_valid = False

        return response

    except Exception as e:
        logger.error(f"Error getting SSL status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve SSL status"
        )


def _parse_certificate(cert_path: str) -> dict:
    """
    Parse certificate file and extract metadata.

    Args:
        cert_path: Path to the PEM certificate file

    Returns:
        Dictionary with certificate info: valid, expires, issuer, subject
    """
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()

        cert = x509.load_pem_x509_certificate(cert_data, default_backend())

        # Check validity
        now = datetime.now(timezone.utc)
        is_valid = cert.not_valid_before_utc <= now <= cert.not_valid_after_utc

        # Extract issuer (CN or O)
        issuer_parts = []
        for attr in cert.issuer:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                issuer_parts.insert(0, attr.value)
            elif attr.oid == x509.oid.NameOID.ORGANIZATION_NAME:
                issuer_parts.append(attr.value)
        issuer = ", ".join(issuer_parts) if issuer_parts else "Unknown"

        # Extract subject (CN)
        subject = None
        for attr in cert.subject:
            if attr.oid == x509.oid.NameOID.COMMON_NAME:
                subject = attr.value
                break

        return {
            "valid": is_valid,
            "expires": cert.not_valid_after_utc.isoformat(),
            "issuer": issuer,
            "subject": subject
        }

    except Exception as e:
        logger.error(f"Error parsing certificate {cert_path}: {e}")
        return {"valid": False, "error": str(e)}


# Story P11-1.1: Cloudflare Tunnel Endpoints
# Story P11-1.2: Enhanced with uptime and reconnect tracking

class TunnelStatusResponse(BaseModel):
    """Response schema for tunnel status."""
    status: str = Field(..., description="Tunnel status: disconnected, connecting, connected, error")
    is_connected: bool = Field(..., description="Whether tunnel is currently connected")
    is_running: bool = Field(..., description="Whether tunnel process is running")
    hostname: Optional[str] = Field(None, description="Tunnel hostname if connected")
    error: Optional[str] = Field(None, description="Error message if status is error")
    enabled: bool = Field(..., description="Whether tunnel is enabled in settings")
    # Story P11-1.2: Enhanced status fields (AC-1.2.4)
    uptime_seconds: float = Field(default=0.0, description="Tunnel uptime in seconds")
    last_connected: Optional[str] = Field(None, description="ISO timestamp of last connection")
    reconnect_count: int = Field(default=0, description="Number of reconnection attempts")


class TunnelStartRequest(BaseModel):
    """Request schema to start tunnel."""
    token: Optional[str] = Field(None, description="Tunnel token (uses saved token if not provided)")


class TunnelActionResponse(BaseModel):
    """Response schema for tunnel start/stop actions."""
    success: bool
    message: str
    status: Optional[TunnelStatusResponse] = None


@router.get("/tunnel/status", response_model=TunnelStatusResponse)
async def get_tunnel_status(db: Session = Depends(get_db)):
    """
    Get Cloudflare Tunnel status (Story P11-1.2 AC-1.2.4)

    Returns current tunnel connection status, hostname, uptime, and configuration state.

    **Response:**
    ```json
    {
        "status": "connected",
        "is_connected": true,
        "is_running": true,
        "hostname": "my-tunnel.trycloudflare.com",
        "error": null,
        "enabled": true,
        "uptime_seconds": 3600.5,
        "last_connected": "2025-12-25T12:00:00+00:00",
        "reconnect_count": 0
    }
    ```

    **Status Codes:**
    - 200: Success
    """
    tunnel_service = container.tunnel_service
    status_dict = tunnel_service.get_status_dict()

    # Get enabled setting from database
    enabled_setting = _get_setting_from_db(db, f"{SETTINGS_PREFIX}tunnel_enabled", "false")
    is_enabled = enabled_setting.lower() in ('true', '1', 'yes') if enabled_setting else False

    return TunnelStatusResponse(
        status=status_dict["status"],
        is_connected=status_dict["is_connected"],
        is_running=status_dict["is_running"],
        hostname=status_dict["hostname"],
        error=status_dict["error"],
        enabled=is_enabled,
        # Story P11-1.2: Enhanced fields
        uptime_seconds=status_dict.get("uptime_seconds", 0.0),
        last_connected=status_dict.get("last_connected"),
        reconnect_count=status_dict.get("reconnect_count", 0),
    )


@router.post("/tunnel/start", response_model=TunnelActionResponse)
async def start_tunnel(
    request: TunnelStartRequest = None,
    db: Session = Depends(get_db)
):
    """
    Start Cloudflare Tunnel

    Starts the cloudflared tunnel process. Uses token from request body
    or falls back to saved token in settings.

    **Request Body (optional):**
    ```json
    {
        "token": "your-tunnel-token"
    }
    ```

    **Response:**
    ```json
    {
        "success": true,
        "message": "Tunnel started successfully",
        "status": { ... }
    }
    ```

    **Status Codes:**
    - 200: Success
    - 400: No token available or invalid token
    - 500: Failed to start tunnel
    """
    tunnel_service = container.tunnel_service

    # Get token from request or database
    token = None
    if request and request.token:
        token = request.token
        # Save token to database (encrypted)
        _set_setting_in_db(db, f"{SETTINGS_PREFIX}tunnel_token", token)
        logger.info(
            "Tunnel token saved from start request",
            extra={"event_type": "tunnel_token_saved"}
        )
    else:
        # Get saved token
        encrypted_token = _get_setting_from_db(db, f"{SETTINGS_PREFIX}tunnel_token")
        if encrypted_token:
            try:
                token = decrypt_password(encrypted_token)
            except ValueError:
                logger.error(
                    "Failed to decrypt saved tunnel token",
                    extra={"event_type": "tunnel_token_decrypt_failed"}
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Saved tunnel token is invalid. Please provide a new token."
                )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tunnel token provided and no saved token found. Please provide a token."
        )

    # Start tunnel
    try:
        success = await tunnel_service.start(token)

        if success:
            # Update enabled setting
            _set_setting_in_db(db, f"{SETTINGS_PREFIX}tunnel_enabled", "true")

            # Get updated status
            status_response = await get_tunnel_status(db)

            return TunnelActionResponse(
                success=True,
                message="Tunnel started successfully",
                status=status_response
            )
        else:
            return TunnelActionResponse(
                success=False,
                message=tunnel_service.error_message or "Failed to start tunnel",
                status=await get_tunnel_status(db)
            )

    except Exception as e:
        logger.error(
            f"Error starting tunnel: {e}",
            extra={"event_type": "tunnel_start_error", "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start tunnel: {str(e)}"
        )


class TunnelTestRequest(BaseModel):
    """Request schema for tunnel connectivity test."""
    token: str = Field(..., min_length=10, description="Tunnel token to test")


class TunnelTestResponse(BaseModel):
    """Response schema for tunnel connectivity test."""
    success: bool = Field(..., description="Whether test succeeded")
    error: Optional[str] = Field(None, description="Error message if test failed")
    latency_ms: Optional[int] = Field(None, description="Connection latency in milliseconds")
    hostname: Optional[str] = Field(None, description="Tunnel hostname if connected")


@router.post("/tunnel/test", response_model=TunnelTestResponse)
async def test_tunnel_connectivity(
    request: TunnelTestRequest,
    db: Session = Depends(get_db)
):
    """
    Test tunnel connectivity without persisting configuration (Story P13-2.4)

    Starts tunnel with provided token, waits for connection,
    and returns result. Stops tunnel after test unless it was
    already running with the same configuration.

    **Request Body:**
    ```json
    {
        "token": "your-tunnel-token"
    }
    ```

    **Response:**
    ```json
    {
        "success": true,
        "error": null,
        "latency_ms": 2500,
        "hostname": "my-tunnel.trycloudflare.com"
    }
    ```

    **Status Codes:**
    - 200: Test result returned
    - 400: Invalid token format
    - 500: Internal server error
    """
    import asyncio
    import time

    tunnel_service = container.tunnel_service
    was_running = tunnel_service.is_running
    original_token = None

    # Get the currently saved token to compare
    encrypted_token = _get_setting_from_db(db, f"{SETTINGS_PREFIX}tunnel_token")
    if encrypted_token:
        try:
            original_token = decrypt_password(encrypted_token)
        except ValueError:
            original_token = None

    start_time = time.time()

    try:
        # If tunnel is running with a different token, stop it first
        if was_running:
            await tunnel_service.stop()
            # Brief wait for cleanup
            await asyncio.sleep(1)

        # Start with test token
        success = await tunnel_service.start(request.token)

        if not success:
            return TunnelTestResponse(
                success=False,
                error=tunnel_service.error_message or "Failed to start tunnel",
                latency_ms=None,
                hostname=None,
            )

        # Wait for connection (max 30 seconds)
        for _ in range(30):
            await asyncio.sleep(1)
            if tunnel_service.is_connected:
                break

        latency_ms = int((time.time() - start_time) * 1000)

        if tunnel_service.is_connected:
            hostname = tunnel_service.hostname
            logger.info(
                f"Tunnel test successful: {hostname} in {latency_ms}ms",
                extra={"event_type": "tunnel_test_success", "hostname": hostname, "latency_ms": latency_ms}
            )
            return TunnelTestResponse(
                success=True,
                error=None,
                latency_ms=latency_ms,
                hostname=hostname,
            )
        else:
            error_msg = tunnel_service.error_message or "Connection timeout after 30 seconds"
            logger.warning(
                f"Tunnel test failed: {error_msg}",
                extra={"event_type": "tunnel_test_failed", "error": error_msg}
            )
            return TunnelTestResponse(
                success=False,
                error=error_msg,
                latency_ms=latency_ms,
                hostname=None,
            )

    except Exception as e:
        logger.error(
            f"Tunnel test error: {e}",
            extra={"event_type": "tunnel_test_error", "error": str(e)}
        )
        return TunnelTestResponse(
            success=False,
            error=str(e),
            latency_ms=None,
            hostname=None,
        )

    finally:
        # Restore original state if test token differs from saved token
        if not was_running or (original_token and original_token != request.token):
            # Stop the test tunnel
            await tunnel_service.stop()

            # Restart with original token if it was running
            if was_running and original_token:
                await asyncio.sleep(1)
                await tunnel_service.start(original_token)


@router.post("/tunnel/stop", response_model=TunnelActionResponse)
async def stop_tunnel(db: Session = Depends(get_db)):
    """
    Stop Cloudflare Tunnel

    Gracefully stops the cloudflared tunnel process.

    **Response:**
    ```json
    {
        "success": true,
        "message": "Tunnel stopped successfully",
        "status": { ... }
    }
    ```

    **Status Codes:**
    - 200: Success
    - 500: Failed to stop tunnel
    """
    tunnel_service = container.tunnel_service

    try:
        await tunnel_service.stop()

        # Update enabled setting
        _set_setting_in_db(db, f"{SETTINGS_PREFIX}tunnel_enabled", "false")

        return TunnelActionResponse(
            success=True,
            message="Tunnel stopped successfully",
            status=await get_tunnel_status(db)
        )

    except Exception as e:
        logger.error(
            f"Error stopping tunnel: {e}",
            extra={"event_type": "tunnel_stop_error", "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to stop tunnel: {str(e)}"
        )


# Story P16-1.7: SMTP Email Settings Endpoints


class SMTPSettingsResponse(BaseModel):
    """Response schema for SMTP settings."""
    enabled: bool = Field(default=False, description="Whether SMTP is enabled")
    host: str = Field(default="", description="SMTP server hostname")
    port: int = Field(default=587, description="SMTP server port")
    username: str = Field(default="", description="SMTP username")
    password_configured: bool = Field(default=False, description="Whether password is configured (not returned)")
    from_email: str = Field(default="", description="From email address")
    from_name: str = Field(default="ArgusAI", description="From display name")
    use_tls: bool = Field(default=False, description="Use TLS (port 465)")
    use_starttls: bool = Field(default=True, description="Use STARTTLS (port 587)")


class SMTPSettingsUpdate(BaseModel):
    """Request schema for updating SMTP settings."""
    enabled: Optional[bool] = Field(None, description="Enable/disable SMTP")
    host: Optional[str] = Field(None, description="SMTP server hostname")
    port: Optional[int] = Field(None, ge=1, le=65535, description="SMTP server port")
    username: Optional[str] = Field(None, description="SMTP username")
    password: Optional[str] = Field(None, description="SMTP password (will be encrypted)")
    from_email: Optional[str] = Field(None, description="From email address")
    from_name: Optional[str] = Field(None, description="From display name")
    use_tls: Optional[bool] = Field(None, description="Use TLS (port 465)")
    use_starttls: Optional[bool] = Field(None, description="Use STARTTLS (port 587)")


class SMTPTestRequest(BaseModel):
    """Request schema for SMTP test."""
    test_email: str = Field(..., description="Email address to send test to")


class SMTPTestResponse(BaseModel):
    """Response schema for SMTP test."""
    success: bool = Field(..., description="Whether test succeeded")
    message: str = Field(..., description="Test result message")


@router.get("/smtp/settings", response_model=SMTPSettingsResponse)
async def get_smtp_settings(db: Session = Depends(get_db)):
    """
    Get SMTP configuration settings (Story P16-1.7)

    Returns current SMTP settings. Password is never returned,
    only whether it is configured.

    **Response:**
    ```json
    {
        "enabled": true,
        "host": "smtp.example.com",
        "port": 587,
        "username": "user@example.com",
        "password_configured": true,
        "from_email": "noreply@example.com",
        "from_name": "ArgusAI",
        "use_tls": false,
        "use_starttls": true
    }
    ```
    """
    prefix = SETTINGS_PREFIX

    # Get settings from database
    enabled = _get_setting_from_db(db, f"{prefix}smtp_enabled", "false")
    host = _get_setting_from_db(db, f"{prefix}smtp_host", "")
    port_str = _get_setting_from_db(db, f"{prefix}smtp_port", "587")
    username = _get_setting_from_db(db, f"{prefix}smtp_username", "")
    password = _get_setting_from_db(db, f"{prefix}smtp_password", "")
    from_email = _get_setting_from_db(db, f"{prefix}smtp_from_email", "")
    from_name = _get_setting_from_db(db, f"{prefix}smtp_from_name", "ArgusAI")
    use_tls = _get_setting_from_db(db, f"{prefix}smtp_use_tls", "false")
    use_starttls = _get_setting_from_db(db, f"{prefix}smtp_use_starttls", "true")

    return SMTPSettingsResponse(
        enabled=enabled.lower() in ('true', '1', 'yes'),
        host=host,
        port=int(port_str) if port_str else 587,
        username=username,
        password_configured=bool(password),
        from_email=from_email,
        from_name=from_name,
        use_tls=use_tls.lower() in ('true', '1', 'yes'),
        use_starttls=use_starttls.lower() in ('true', '1', 'yes'),
    )


@router.put("/smtp/settings", response_model=SMTPSettingsResponse)
async def update_smtp_settings(
    settings_update: SMTPSettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    Update SMTP configuration settings (Story P16-1.7)

    Updates SMTP settings. Password will be encrypted before storage.

    **Request Body:**
    ```json
    {
        "enabled": true,
        "host": "smtp.example.com",
        "port": 587,
        "username": "user@example.com",
        "password": "secret",
        "from_email": "noreply@example.com",
        "from_name": "ArgusAI",
        "use_tls": false,
        "use_starttls": true
    }
    ```
    """
    prefix = SETTINGS_PREFIX

    # Update each provided setting
    if settings_update.enabled is not None:
        _set_setting_in_db(db, f"{prefix}smtp_enabled", "true" if settings_update.enabled else "false")

    if settings_update.host is not None:
        _set_setting_in_db(db, f"{prefix}smtp_host", settings_update.host)

    if settings_update.port is not None:
        _set_setting_in_db(db, f"{prefix}smtp_port", str(settings_update.port))

    if settings_update.username is not None:
        _set_setting_in_db(db, f"{prefix}smtp_username", settings_update.username)

    if settings_update.password is not None:
        # Password will be encrypted by _set_setting_in_db since it's in SENSITIVE_SETTING_KEYS
        _set_setting_in_db(db, f"{prefix}smtp_password", settings_update.password)

    if settings_update.from_email is not None:
        _set_setting_in_db(db, f"{prefix}smtp_from_email", settings_update.from_email)

    if settings_update.from_name is not None:
        _set_setting_in_db(db, f"{prefix}smtp_from_name", settings_update.from_name)

    if settings_update.use_tls is not None:
        _set_setting_in_db(db, f"{prefix}smtp_use_tls", "true" if settings_update.use_tls else "false")

    if settings_update.use_starttls is not None:
        _set_setting_in_db(db, f"{prefix}smtp_use_starttls", "true" if settings_update.use_starttls else "false")

    db.commit()

    logger.info(
        "SMTP settings updated",
        extra={"event_type": "smtp_settings_updated"}
    )

    return await get_smtp_settings(db)


@router.post("/smtp/test", response_model=SMTPTestResponse)
async def test_smtp_connection(
    request: SMTPTestRequest,
    db: Session = Depends(get_db)
):
    """
    Test SMTP connection (Story P16-1.7)

    Tests SMTP connection by sending a test email.

    **Request Body:**
    ```json
    {
        "test_email": "test@example.com"
    }
    ```

    **Response:**
    ```json
    {
        "success": true,
        "message": "Test email sent successfully"
    }
    ```
    """
    from app.services.email_service import EmailService

    email_service = EmailService(db)

    if not email_service.is_configured():
        return SMTPTestResponse(
            success=False,
            message="SMTP is not configured. Please configure SMTP settings first."
        )

    # Send test email
    test_subject = "ArgusAI SMTP Test"
    test_html = """
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #2563eb;">ArgusAI SMTP Test</h2>
        <p>This is a test email from ArgusAI to verify your SMTP configuration.</p>
        <p>If you received this email, your SMTP settings are working correctly!</p>
        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
        <p style="color: #6b7280; font-size: 12px;">
            This email was sent automatically by ArgusAI.
        </p>
    </body>
    </html>
    """
    test_text = """
ArgusAI SMTP Test

This is a test email from ArgusAI to verify your SMTP configuration.

If you received this email, your SMTP settings are working correctly!

---
This email was sent automatically by ArgusAI.
    """

    success = await email_service.send_email(
        to_email=request.test_email,
        subject=test_subject,
        html_content=test_html,
        text_content=test_text,
    )

    if success:
        return SMTPTestResponse(
            success=True,
            message=f"Test email sent successfully to {request.test_email}"
        )
    else:
        return SMTPTestResponse(
            success=False,
            message="Failed to send test email. Check server logs for details."
        )
