"""ProtectService.get_cached_camera_online reads cached state only (issue #648)."""
from types import SimpleNamespace

from app.services.protect_service import ProtectService


def _fake_service(connections=None, last=None):
    return SimpleNamespace(_connections=connections or {}, _last_camera_status=last or {})


def test_bootstrap_value_wins():
    camera = SimpleNamespace(is_connected=False)
    client = SimpleNamespace(bootstrap=SimpleNamespace(cameras={"cam-1": camera}))
    svc = _fake_service({"ctrl": client}, {"cam-1": True})
    assert ProtectService.get_cached_camera_online(svc, "ctrl", "cam-1") is False


def test_falls_back_to_last_websocket_status_then_unknown():
    svc = _fake_service({}, {"cam-1": True})
    assert ProtectService.get_cached_camera_online(svc, "ctrl", "cam-1") is True
    assert ProtectService.get_cached_camera_online(svc, "ctrl", "cam-2") is None
    assert ProtectService.get_cached_camera_online(svc, "ctrl", None) is None
