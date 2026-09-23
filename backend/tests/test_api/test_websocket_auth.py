"""Regression coverage for preaccept WebSocket authentication."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.auth import (
    authenticate_websocket,
    require_websocket_user,
    websocket_session_is_active,
)
from app.api.v1.websocket import websocket_endpoint, stream_camera_ws, send_heartbeat
from app.api.v1.cameras import stream_camera
from fastapi import WebSocketDisconnect


def socket(*, origin="http://localhost:3000", cookie=None, bearer=None):
    websocket = MagicMock()
    websocket.headers = {}
    if origin is not None:
        websocket.headers["origin"] = origin
    if bearer is not None:
        websocket.headers["authorization"] = f"Bearer {bearer}"
    websocket.cookies = {"access_token": cookie} if cookie else {}
    websocket.close = AsyncMock()
    websocket.accept = AsyncMock()
    return websocket


@pytest.mark.asyncio
async def test_anonymous_socket_is_rejected_before_accept():
    websocket = socket()
    assert await require_websocket_user(websocket) is None
    websocket.close.assert_awaited_once()
    websocket.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_cross_origin_cookie_socket_is_rejected_before_token_lookup():
    websocket = socket(origin="https://attacker.example", cookie="valid-cookie")
    with patch("app.api.v1.auth.authenticate_websocket") as authenticate:
        assert await require_websocket_user(websocket) is None
    authenticate.assert_not_called()
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_cookie_without_origin_is_rejected_but_api_bearer_is_allowed():
    cookie_socket = socket(origin=None, cookie="valid-cookie")
    assert await require_websocket_user(cookie_socket) is None
    cookie_socket.close.assert_awaited_once()

    bearer_socket = socket(origin=None, bearer="valid-bearer")
    user = MagicMock(is_active=True)
    with patch("app.api.v1.auth.authenticate_websocket", return_value=user), \
         patch("app.api.v1.auth.websocket_session_is_active", return_value=True):
        assert await require_websocket_user(bearer_socket) is user
    bearer_socket.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_query_token_cannot_authenticate_socket():
    websocket = socket()
    websocket.query_params = {"token": "logged-jwt"}
    assert await require_websocket_user(websocket) is None
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_disabled_user_is_rejected():
    websocket = socket(cookie="valid-cookie")
    disabled_user = MagicMock(is_active=False)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = disabled_user

    @contextmanager
    def db_session():
        yield db

    with patch("app.api.v1.auth.decode_access_token", return_value={"user_id": "user-1"}), \
         patch("app.core.database.get_db_session", db_session):
        assert authenticate_websocket(websocket) is None
        assert await require_websocket_user(websocket) is None
    websocket.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoked_session_is_rejected_before_accept():
    websocket = socket(cookie="valid-jwt-with-revoked-session")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    @contextmanager
    def db_session():
        yield db

    with patch("app.api.v1.auth.decode_access_token", return_value={"user_id": "user-1"}), \
         patch("app.core.database.get_db_session", db_session), \
         patch("app.api.v1.auth.authenticate_websocket", return_value=MagicMock()):
        assert websocket_session_is_active(websocket) is False
        assert await require_websocket_user(websocket) is None
    websocket.close.assert_awaited_once()
    websocket.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_session_and_user_are_allowed():
    websocket = socket(cookie="valid-jwt-and-session")
    session = MagicMock(user_id="user-1")
    session.is_expired.return_value = False
    user = MagicMock(is_active=True)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [session, user]

    @contextmanager
    def db_session():
        yield db

    with patch("app.api.v1.auth.decode_access_token", return_value={"user_id": "user-1"}), \
         patch("app.core.database.get_db_session", db_session), \
         patch("app.api.v1.auth.authenticate_websocket", return_value=user):
        assert await require_websocket_user(websocket) is user
    websocket.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_closes_socket_after_session_revocation():
    websocket = socket(cookie="valid-jwt-then-revoked")
    with patch("app.api.v1.websocket.HEARTBEAT_INTERVAL", 0), \
         patch("app.api.v1.websocket.websocket_session_is_active", return_value=False):
        await send_heartbeat(websocket)
    websocket.close.assert_awaited_once()
    websocket.send_text.assert_not_called()


@pytest.mark.asyncio
async def test_notification_route_does_not_register_anonymous_socket():
    websocket = socket()
    with patch("app.api.v1.websocket.get_websocket_manager") as manager:
        await websocket_endpoint(websocket)
    manager.assert_not_called()
    websocket.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_allowed_user_can_join_notification_socket():
    websocket = socket(cookie="valid-cookie")
    websocket.receive_text = AsyncMock(side_effect=WebSocketDisconnect())
    manager = MagicMock()
    manager.connect = AsyncMock()
    manager.disconnect = AsyncMock()
    with patch("app.api.v1.websocket.require_websocket_user", return_value=MagicMock()), \
         patch("app.api.v1.websocket.get_websocket_manager", return_value=manager):
        await websocket_endpoint(websocket)
    manager.connect.assert_awaited_once_with(websocket)
    manager.disconnect.assert_awaited_once_with(websocket)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", [stream_camera, stream_camera_ws])
async def test_camera_routes_do_not_accept_anonymous_socket(route):
    websocket = socket()
    await route(websocket, "camera-1")
    websocket.accept.assert_not_awaited()
    websocket.close.assert_awaited_once()
