"""Event deletion removes media inside configured roots and reports failures."""

import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  # register every table before create_all
from app.core.database import Base, get_db
from app.models.event import Event
from app.models.event_frame import EventFrame
from app.models.recognized_entity import RecognizedEntity
from app.services.event_media_deletion import EventMediaDeletionService
from main import app
from tests.conftest import make_camera, make_entity, make_event


def _roots(tmp_path):
    names = ("thumbnails", "frames", "videos", "clips")
    paths = {}
    for name in names:
        directory = tmp_path / name
        directory.mkdir()
        paths[name] = str(directory)
    return paths


def _service(tmp_path, unlink=None):
    roots = _roots(tmp_path)
    return EventMediaDeletionService(
        thumbnail_root=roots["thumbnails"],
        frames_root=roots["frames"],
        video_root=roots["videos"],
        clips_root=roots["clips"],
        unlink=unlink,
    ), roots


def _write(path, payload=b"media"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)
    return path


def _lay_out_event(db_session, roots, camera_id):
    event_id = str(uuid.uuid4())
    thumb_rel = f"2026-01-02/event_{event_id}.jpg"
    thumb = _write(os.path.join(roots["thumbnails"], thumb_rel))
    annotated = _write(os.path.join(
        roots["thumbnails"], f"2026-01-02/event_{event_id}_annotated.jpg"
    ))
    frame = _write(os.path.join(roots["frames"], event_id, "frame_001.jpg"))
    extra = _write(os.path.join(roots["frames"], event_id, "extra.bin"))
    video = _write(os.path.join(roots["videos"], f"{event_id}.mp4"), b"video")
    clip = _write(os.path.join(roots["clips"], f"{event_id}.mp4"), b"clip")
    reanalyze = _write(os.path.join(roots["clips"], f"reanalyze_{event_id}.mp4"), b"re")
    event = make_event(
        db_session=db_session,
        id=event_id,
        camera_id=camera_id,
        thumbnail_path=thumb_rel,
        video_path=f"{event_id}.mp4",
    )
    db_session.add(EventFrame(
        id=str(uuid.uuid4()),
        event_id=event_id,
        frame_number=1,
        frame_path=f"frames/{event_id}/frame_001.jpg",
        timestamp_offset_ms=0,
    ))
    db_session.commit()
    files = {
        "thumb": thumb,
        "annotated": annotated,
        "frame": frame,
        "extra": extra,
        "video": video,
        "clip": clip,
        "reanalyze": reanalyze,
    }
    return event, files


def test_single_delete_removes_all_media_and_rows(db_session, tmp_path):
    service, roots = _service(tmp_path)
    camera = make_camera(db_session=db_session)
    other_thumb = _write(os.path.join(roots["thumbnails"], "keep.jpg"), b"keep")
    event, files = _lay_out_event(db_session, roots, camera.id)

    result = service.delete_event_media(db_session, event)
    db_session.commit()

    assert result.fully_deleted is True
    assert result.failures == []
    assert result.thumbnails_deleted == 2
    assert result.frames_deleted == 2
    assert result.videos_deleted == 1
    assert result.clips_deleted == 2
    for path in files.values():
        assert not os.path.exists(path)
    assert not os.path.isdir(os.path.join(roots["frames"], event.id))
    assert os.path.exists(other_thumb)
    assert db_session.query(Event).filter(Event.id == event.id).first() is None
    assert db_session.query(EventFrame).filter(EventFrame.event_id == event.id).count() == 0


def test_bulk_delete_removes_media_for_every_event(db_session, tmp_path):
    service, roots = _service(tmp_path)
    camera = make_camera(db_session=db_session)
    first, first_files = _lay_out_event(db_session, roots, camera.id)
    second, second_files = _lay_out_event(db_session, roots, camera.id)

    results = [
        service.delete_event_media(db_session, first),
        service.delete_event_media(db_session, second),
    ]
    db_session.commit()

    assert all(result.fully_deleted for result in results)
    for path in {**first_files, **second_files}.values():
        assert not os.path.exists(path)
    assert db_session.query(Event).count() == 0


def test_unlink_failure_is_partial_and_retry_finishes(db_session, tmp_path):
    locked = {"on": True}

    def unlink(path):
        if locked["on"] and path.endswith(".mp4") and "/videos/" in path.replace("\\", "/"):
            raise OSError("permission denied")
        os.remove(path)

    service, roots = _service(tmp_path, unlink=unlink)
    camera = make_camera(db_session=db_session)
    event, files = _lay_out_event(db_session, roots, camera.id)

    result = service.delete_event_media(db_session, event)
    db_session.commit()
    db_session.refresh(event)

    assert result.fully_deleted is False
    assert event.video_path == f"{event.id}.mp4"
    assert event.thumbnail_path is None
    assert os.path.exists(files["video"])
    assert not os.path.exists(files["thumb"])
    assert not os.path.exists(files["frame"])
    assert db_session.query(EventFrame).filter(EventFrame.event_id == event.id).count() == 0
    assert any(item.reason == "unlink_failed" and item.kind == "video" for item in result.failures)

    locked["on"] = False
    retry = service.delete_event_media(db_session, event)
    db_session.commit()

    assert retry.fully_deleted is True
    assert not os.path.exists(files["video"])
    assert db_session.query(Event).filter(Event.id == event.id).first() is None


def test_missing_media_is_idempotent_success(db_session, tmp_path):
    service, _roots_map = _service(tmp_path)
    camera = make_camera(db_session=db_session)
    event = make_event(
        db_session=db_session,
        camera_id=camera.id,
        thumbnail_path="2026-01-02/missing.jpg",
        video_path="missing.mp4",
    )

    result = service.delete_event_media(db_session, event)
    db_session.commit()

    assert result.fully_deleted is True
    assert result.thumbnails_deleted == 0
    assert db_session.query(Event).filter(Event.id == event.id).first() is None


def test_stored_paths_outside_media_root_are_refused(db_session, tmp_path):
    service, roots = _service(tmp_path)
    camera = make_camera(db_session=db_session)
    outside = _write(str(tmp_path / "outside" / "secret.jpg"), b"secret")
    outside_video = _write(str(tmp_path / "outside" / "clip.mp4"), b"secret-video")
    event = make_event(
        db_session=db_session,
        camera_id=camera.id,
        thumbnail_path=str(outside),
        video_path=str(outside_video),
    )
    frame = EventFrame(
        id=str(uuid.uuid4()),
        event_id=event.id,
        frame_number=1,
        frame_path=f"frames/{event.id}/../../outside/secret.jpg",
        timestamp_offset_ms=0,
    )
    db_session.add(frame)
    db_session.commit()

    result = service.delete_event_media(db_session, event)
    db_session.commit()
    db_session.refresh(event)

    assert result.fully_deleted is False
    assert os.path.exists(outside)
    assert os.path.exists(outside_video)
    assert db_session.query(Event).filter(Event.id == event.id).first() is not None
    assert db_session.query(EventFrame).filter(EventFrame.id == frame.id).first() is not None
    reasons = {item.reason for item in result.failures}
    assert "outside_root" in reasons
    assert event.thumbnail_path == str(outside)
    assert event.video_path == str(outside_video)


def test_symlink_inside_media_root_is_refused(db_session, tmp_path):
    service, roots = _service(tmp_path)
    camera = make_camera(db_session=db_session)
    target = _write(str(tmp_path / "outside" / "real.jpg"), b"real")
    link = os.path.join(roots["thumbnails"], "link.jpg")
    os.symlink(target, link)
    event = make_event(
        db_session=db_session,
        camera_id=camera.id,
        thumbnail_path="link.jpg",
    )

    result = service.delete_event_media(db_session, event)
    db_session.commit()

    assert result.fully_deleted is False
    assert os.path.islink(link)
    assert os.path.exists(target)
    assert any(item.reason in {"symlink", "outside_root"} for item in result.failures)


@pytest.fixture
def media_api(tmp_path, monkeypatch):
    roots = _roots(tmp_path)
    engine = create_engine(
        f"sqlite:///{tmp_path}/api.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        "app.services.event_media_deletion.default_media_roots",
        lambda: {
            "thumbnail_root": roots["thumbnails"],
            "frames_root": roots["frames"],
            "video_root": roots["videos"],
            "clips_root": roots["clips"],
        },
    )
    client = TestClient(app)
    try:
        yield client, session_factory, roots
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def test_api_single_and_bulk_delete_remove_media(media_api):
    client, session_factory, roots = media_api
    db = session_factory()
    camera = make_camera(db_session=db)
    first, first_files = _lay_out_event(db, roots, camera.id)
    second, second_files = _lay_out_event(db, roots, camera.id)
    first_id = first.id
    second_id = second.id
    db.close()

    single = client.delete(f"/api/v1/events/{first_id}")
    assert single.status_code == 204
    for path in first_files.values():
        assert not os.path.exists(path)

    bulk = client.delete(
        "/api/v1/events/bulk",
        params={"event_ids": [second_id]},
    )
    assert bulk.status_code == 200
    body = bulk.json()
    assert body["success"] is True
    assert body["deleted_count"] == 1
    assert body["partial"] is False
    assert body["frames_deleted"] >= 1
    assert body["videos_deleted"] == 1
    assert "failed_items" in body
    for path in second_files.values():
        assert not os.path.exists(path)

    check = session_factory()
    assert check.query(Event).count() == 0
    check.close()


def test_api_unlink_failure_does_not_claim_success(media_api, monkeypatch):
    client, session_factory, roots = media_api

    real_remove = os.remove

    def unlink(path):
        if os.path.basename(path).endswith(".mp4") and os.path.dirname(path) == roots["videos"]:
            raise OSError("locked")
        real_remove(path)

    original = EventMediaDeletionService.__init__

    def init(self, *args, **kwargs):
        kwargs["unlink"] = unlink
        original(self, *args, **kwargs)

    monkeypatch.setattr(EventMediaDeletionService, "__init__", init)

    db = session_factory()
    camera = make_camera(db_session=db)
    event, files = _lay_out_event(db, roots, camera.id)
    kept, kept_files = _lay_out_event(db, roots, camera.id)
    event_id = event.id
    kept_id = kept.id
    db.close()

    single = client.delete(f"/api/v1/events/{event_id}")
    assert single.status_code == 409
    payload = single.json()
    assert payload["success"] is False
    assert payload["deleted"] is False
    assert any(item["reason"] == "unlink_failed" for item in payload["failed_items"])
    assert os.path.exists(files["video"])

    bulk = client.delete(
        "/api/v1/events/bulk",
        params={"event_ids": [event_id, kept_id, "missing-id"]},
    )
    assert bulk.status_code == 200
    body = bulk.json()
    assert body["success"] is False
    assert body["partial"] is False or body["deleted_count"] == 0
    assert body["deleted_count"] == 0
    assert body["not_found_count"] == 1
    assert body["failed_count"] == 2
    assert os.path.exists(files["video"])
    assert os.path.exists(kept_files["video"])

    check = session_factory()
    assert check.query(Event).filter(Event.id.in_([event_id, kept_id])).count() == 2
    check.close()


def test_api_outside_path_is_refused(media_api):
    client, session_factory, roots = media_api
    outside = _write(os.path.join(os.path.dirname(roots["thumbnails"]), "secret.jpg"), b"nope")
    db = session_factory()
    camera = make_camera(db_session=db)
    event = make_event(
        db_session=db,
        camera_id=camera.id,
        thumbnail_path=outside,
    )
    event_id = event.id
    db.close()

    response = client.delete(f"/api/v1/events/{event_id}")
    assert response.status_code == 409
    body = response.json()
    assert any(item["reason"] == "outside_root" for item in body["failed_items"])
    assert all(item["stored_path"] == "" for item in body["failed_items"])
    assert outside not in response.text
    assert os.path.exists(outside)
    check = session_factory()
    assert check.query(Event).filter(Event.id == event_id).first() is not None
    check.close()


def test_orphan_reconcile_dry_run_and_apply(db_session, tmp_path):
    service, roots = _service(tmp_path)
    camera = make_camera(db_session=db_session)
    event, files = _lay_out_event(db_session, roots, camera.id)
    orphan_thumb = _write(os.path.join(roots["thumbnails"], "2020-01-01", "orphan.jpg"), b"old")
    orphan_frame = _write(os.path.join(roots["frames"], "gone-event", "frame_001.jpg"), b"old")
    entity_thumb = _write(os.path.join(roots["thumbnails"], "entity.jpg"), b"person")
    make_entity(db_session=db_session, thumbnail_path="entity.jpg")

    dry = service.reconcile_orphans(db_session, dry_run=True)
    assert dry.success is True
    assert dry.deleted_files == 0
    assert dry.orphan_files >= 2
    assert os.path.exists(orphan_thumb)
    assert os.path.exists(orphan_frame)
    assert os.path.exists(files["thumb"])
    assert os.path.exists(entity_thumb)

    applied = service.reconcile_orphans(db_session, dry_run=False)
    assert applied.success is True
    assert applied.deleted_files >= 2
    assert not os.path.exists(orphan_thumb)
    assert not os.path.exists(orphan_frame)
    assert os.path.exists(files["thumb"])
    assert os.path.exists(files["frame"])
    assert os.path.exists(files["video"])
    assert os.path.exists(entity_thumb)
    assert db_session.query(Event).filter(Event.id == event.id).first() is not None
    assert db_session.query(RecognizedEntity).count() == 1


def test_orphan_reconcile_fails_closed_when_references_cannot_be_read(db_session, tmp_path, monkeypatch):
    service, roots = _service(tmp_path)
    orphan = _write(os.path.join(roots["thumbnails"], "orphan.jpg"), b"old")

    def boom(self, db):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(EventMediaDeletionService, "_reference_snapshot", boom)
    report = service.reconcile_orphans(db_session, dry_run=False)

    assert report.skipped is True
    assert report.success is False
    assert report.deleted_files == 0
    assert os.path.exists(orphan)


def test_api_orphan_dry_run_does_not_delete(media_api):
    client, _session_factory, roots = media_api
    orphan = _write(os.path.join(roots["videos"], "nobody.mp4"), b"old")

    response = client.post("/api/v1/events/media-orphans/reconcile")
    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["deleted_files"] == 0
    assert body["orphan_files"] >= 1
    assert os.path.exists(orphan)

    applied = client.post("/api/v1/events/media-orphans/reconcile?dry_run=false")
    assert applied.status_code == 200
    assert applied.json()["deleted_files"] >= 1
    assert not os.path.exists(orphan)
