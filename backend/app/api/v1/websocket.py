"""
WebSocket API Endpoint (Story 5.4)

Provides real-time WebSocket connection for dashboard notifications.
Uses the existing WebSocketManager singleton for connection management.

Features:
- Auto-accept connections
- Heartbeat/ping-pong to keep connections alive
- Graceful disconnect handling
- Camera stream proxy (alternative path for Cloudflare Tunnel compatibility)
"""
import asyncio
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import get_websocket_manager
from app.services.ws_connection_limits import websocket_connection_limits
from app.api.v1.auth import (
    WS_CLOSE_AUTH,
    WS_CLOSE_LIMIT,
    WS_SESSION_RECHECK_SECONDS,
    require_websocket_user,
    websocket_session_is_active,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

# Heartbeat interval in seconds. The same interval rechecks the session.
HEARTBEAT_INTERVAL = WS_SESSION_RECHECK_SECONDS


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time notifications.

    Maintains connection with heartbeat pings and handles messages.
    Connected clients receive notification broadcasts from alert engine.

    Protocol:
    - Server sends ping every 30 seconds to keep connection alive
    - Client should respond with pong (handled automatically by browsers)
    - Server broadcasts notifications as JSON: {"type": "notification", "data": {...}}
    """
    user = await require_websocket_user(websocket)
    if user is None:
        return

    admission = await websocket_connection_limits().try_admit(str(user.id))
    if admission is None:
        await websocket.close(code=WS_CLOSE_LIMIT, reason="Connection limit reached")
        return

    manager = get_websocket_manager()
    try:
        await manager.connect(websocket)
        # Create heartbeat task
        heartbeat_task = asyncio.create_task(send_heartbeat(websocket))

        try:
            while True:
                # Wait for messages from client
                data = await websocket.receive_text()

                # Handle client messages (primarily for pong responses)
                if data == "pong":
                    logger.debug("Received pong from client")
                elif data == "ping":
                    # Client-initiated ping - respond with pong
                    await websocket.send_text("pong")
                else:
                    # Log other messages but don't process
                    logger.debug(f"Received WebSocket message: {data[:100]}")

        except WebSocketDisconnect:
            logger.info("WebSocket client disconnected")
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        await websocket_connection_limits().release(admission)
        await manager.disconnect(websocket)


async def send_heartbeat(websocket: WebSocket):
    """
    Send periodic heartbeat pings to keep connection alive.

    Args:
        websocket: Active WebSocket connection
    """
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if not websocket_session_is_active(websocket):
                await websocket.close(code=WS_CLOSE_AUTH, reason="Session expired")
                break
            try:
                await websocket.send_text("ping")
                logger.debug("Sent heartbeat ping")
            except Exception as e:
                logger.debug(f"Heartbeat failed: {e}")
                break
    except asyncio.CancelledError:
        pass


# Alternative camera stream endpoint under /ws path for Cloudflare Tunnel compatibility
# This is a proxy to the main camera stream endpoint at /api/v1/cameras/{id}/stream
@router.websocket("/ws/stream/{camera_id}")
async def stream_camera_ws(
    websocket: WebSocket,
    camera_id: str,
    quality: str = "medium"
):
    """
    Alternative WebSocket endpoint for live camera streaming.

    This endpoint uses the /ws path prefix which has better compatibility
    with Cloudflare Tunnel. It delegates to the main stream_camera endpoint.

    Args:
        websocket: WebSocket connection
        camera_id: UUID of camera
        quality: Stream quality (low, medium, high)
    """
    # Import here to avoid circular imports
    from app.api.v1.cameras import stream_camera
    await stream_camera(websocket, camera_id, quality)
