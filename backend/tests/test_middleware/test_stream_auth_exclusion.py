"""Stream paths excluded from AuthMiddleware must be the WebSocket upgrades only."""

from fastapi import FastAPI

from app.middleware.auth_middleware import AuthMiddleware


def _middleware() -> AuthMiddleware:
    return AuthMiddleware(FastAPI())


def test_only_camera_websocket_stream_suffix_skips_http_auth():
    middleware = _middleware()
    assert middleware._is_excluded("/api/v1/cameras/abc/stream")
    assert middleware._is_excluded("/ws")
    assert middleware._is_excluded("/ws/stream/abc")

    # HTTP snapshot, info, and metrics stay on AuthMiddleware. They do not
    # match the /stream segment suffix, so an API key still needs read:cameras.
    assert not middleware._is_excluded("/api/v1/cameras/abc/stream/snapshot")
    assert not middleware._is_excluded("/api/v1/cameras/abc/stream/info")
    assert not middleware._is_excluded("/api/v1/cameras/stream/metrics")
    assert not middleware._is_excluded("/api/v1/system/ai-processing-stream")
    assert not middleware._is_excluded("/api/v1/system/ai-processing-hot-stream")
    assert not middleware._is_excluded("/api/v1/events/abc/video")
