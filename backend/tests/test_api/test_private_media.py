"""Private media must be authorized on every image and metadata request."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from jose import jwt

import main
from app.api.v1 import events as events_api
from app.api.v1.auth import get_media_principal
from app.core.config import settings
from app.models.event import Event
from app.models.event_frame import EventFrame
from app.models.user import User, UserRole
from app.utils.jwt import create_access_token


@pytest.fixture
def viewer(db_session):
    user = User(
        id=str(uuid4()), username=f"viewer_{uuid4().hex[:8]}",
        password_hash="x" * 60, role=UserRole.VIEWER, is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def private_media(tmp_path, monkeypatch, db_session):
    event = Event(
        id=str(uuid4()), camera_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc), description="Private test event",
        confidence=85, objects_detected="[]", source_type="protect",
    )
    frame = EventFrame(
        id=str(uuid4()), event_id=event.id, frame_number=1,
        frame_path=f"frames/{event.id}/frame_001.jpg",
        timestamp_offset_ms=500, file_size_bytes=4,
    )
    db_session.add_all([event, frame])
    db_session.commit()

    thumbnail_dir = tmp_path / "thumbnails"
    thumbnail = thumbnail_dir / "2026-09-23" / f"{event.id}.jpg"
    thumbnail.parent.mkdir(parents=True)
    thumbnail.write_bytes(b"jpeg")
    frame_dir = tmp_path / "frames"
    frame_file = frame_dir / event.id / "frame_001.jpg"
    frame_file.parent.mkdir(parents=True)
    frame_file.write_bytes(b"jpeg")
    monkeypatch.setattr(main, "THUMBNAIL_DIR", thumbnail_dir)
    monkeypatch.setattr(events_api, "FRAME_DIR", str(frame_dir))
    return event, thumbnail


def _paths(event, thumbnail):
    return (
        f"/api/v1/thumbnails/{thumbnail.parent.name}/{thumbnail.name}",
        f"/api/v1/events/{event.id}/frames",
        f"/api/v1/events/{event.id}/frames/1",
    )


def test_anonymous_cannot_read_media(api_client, private_media):
    for path in _paths(*private_media):
        assert api_client.get(path).status_code == 401


def test_viewer_can_read_private_media_without_public_cache(api_client, viewer, private_media):
    api_client.cookies.set("access_token", create_access_token(viewer.id, viewer.username))
    thumbnail_path, list_path, frame_path = _paths(*private_media)
    for path in (thumbnail_path, frame_path):
        response = api_client.get(path)
        assert response.status_code == 200
        assert response.content == b"jpeg"
        assert "no-store" in response.headers["cache-control"]

    frame_list = api_client.get(list_path)
    assert frame_list.status_code == 200
    assert "no-store" in frame_list.headers["cache-control"]
    assert len(frame_list.json()["frames"]) == 1
    assert "frame_path" not in frame_list.json()["frames"][0]


def test_disabled_user_loses_media_access(api_client, db_session, viewer, private_media):
    api_client.cookies.set("access_token", create_access_token(viewer.id, viewer.username))
    thumbnail_path, list_path, frame_path = _paths(*private_media)
    viewer.is_active = False
    db_session.commit()
    for path in (thumbnail_path, list_path, frame_path):
        assert api_client.get(path).status_code == 401


def test_expired_session_cannot_read_media(api_client, viewer, private_media):
    expired = jwt.encode(
        {"sub": viewer.id, "username": viewer.username, "exp": 1},
        settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM,
    )
    api_client.cookies.set("access_token", expired)
    for path in _paths(*private_media):
        assert api_client.get(path).status_code == 401


def test_frame_cannot_be_read_through_other_event(api_client, db_session, viewer, private_media):
    api_client.cookies.set("access_token", create_access_token(viewer.id, viewer.username))
    other = Event(
        id=str(uuid4()), camera_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc), description="Other event",
        confidence=85, objects_detected="[]", source_type="protect",
    )
    db_session.add(other)
    db_session.commit()
    assert api_client.get(f"/api/v1/events/{other.id}/frames/1").status_code == 404


def test_stored_frame_path_cannot_redirect_file_read(api_client, db_session, viewer, private_media, tmp_path):
    api_client.cookies.set("access_token", create_access_token(viewer.id, viewer.username))
    event, _ = private_media
    db_session.query(EventFrame).filter(EventFrame.event_id == event.id).update(
        {"frame_path": str(tmp_path / "outside.jpg")}
    )
    db_session.commit()
    response = api_client.get(f"/api/v1/events/{event.id}/frames/1")
    assert response.status_code == 200
    assert response.content == b"jpeg"


def test_copied_thumbnail_url_requires_cookie(api_client, viewer, private_media):
    api_client.cookies.set("access_token", create_access_token(viewer.id, viewer.username))
    thumbnail_path, _, _ = _paths(*private_media)
    assert api_client.get(thumbnail_path).status_code == 200
    api_client.cookies.clear()
    assert api_client.get(thumbnail_path).status_code == 401


def test_media_principal_accepts_only_a_middleware_authenticated_api_key():
    class State:
        api_key = {"id": "key-1", "scopes": ["read:events"]}

    class Request:
        state = State()

    assert get_media_principal(Request(), db=None) == State.api_key
