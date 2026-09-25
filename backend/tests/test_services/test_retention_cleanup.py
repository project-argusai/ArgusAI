"""Regression tests for retention media paths, settings, and child-row cleanup."""
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, _enable_sqlite_foreign_keys
from app.models.ai_usage import AIUsage
from app.models.event import Event
from app.models.event_embedding import EventEmbedding
from app.models.event_frame import EventFrame
from app.models.recognized_entity import EntityEvent, RecognizedEntity
from app.models.system_setting import SystemSetting
from app.services.cleanup_service import CleanupService, resolve_thumbnail_fs_path
from app.services.retention_jobs import (
    register_retention_jobs,
    scheduled_cleanup_job,
    scheduled_video_cleanup_job,
)
from app.services.retention_settings import (
    get_video_retention_days,
    is_auto_cleanup_enabled,
    reconcile_retention_policy,
)


def _aware(days_ago: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago)


class TestThumbnailPathResolution:
    def test_api_url_maps_under_thumbnail_dir(self, tmp_path):
        base = tmp_path / "thumbnails"
        day = base / "2026-01-02"
        day.mkdir(parents=True)
        target = day / "event.jpg"
        target.write_bytes(b"jpeg")

        resolved = resolve_thumbnail_fs_path(
            "/api/v1/thumbnails/2026-01-02/event.jpg",
            str(base),
        )
        assert resolved == os.path.normpath(str(target))

    def test_legacy_relative_and_data_prefixes(self, tmp_path):
        base = str(tmp_path / "thumbnails")
        os.makedirs(os.path.join(base, "2026-01-02"), exist_ok=True)
        assert resolve_thumbnail_fs_path(
            "thumbnails/2026-01-02/a.jpg", base
        ).endswith(os.path.join("2026-01-02", "a.jpg"))
        assert resolve_thumbnail_fs_path(
            "data/thumbnails/2026-01-02/a.jpg", base
        ).endswith(os.path.join("2026-01-02", "a.jpg"))

    def test_parent_traversal_is_rejected(self, tmp_path):
        assert resolve_thumbnail_fs_path(
            "thumbnails/../../secret.txt", str(tmp_path)
        ) is None
        assert resolve_thumbnail_fs_path(
            "/api/v1/thumbnails/../../secret.txt", str(tmp_path)
        ) is None

    def test_absolute_path_outside_thumbnail_dir_is_rejected(self, tmp_path):
        outside = tmp_path / "outside.jpg"
        outside.write_bytes(b"nope")
        assert resolve_thumbnail_fs_path(str(outside), str(tmp_path / "thumbnails")) is None


class _CleanupHarness:
    def __init__(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.thumbnail_dir = tempfile.mkdtemp()
        self.video_dir = tempfile.mkdtemp()
        self.frames_dir = tempfile.mkdtemp()
        self.service = CleanupService(session_factory=self.SessionLocal)
        self.service.thumbnail_base_dir = self.thumbnail_dir
        self.service.video_base_dir = self.video_dir
        self.service.frames_base_dir = self.frames_dir
        self.service._child_tables_cache = None

    def close(self):
        self.engine.dispose()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        shutil.rmtree(self.thumbnail_dir, ignore_errors=True)
        shutil.rmtree(self.video_dir, ignore_errors=True)
        shutil.rmtree(self.frames_dir, ignore_errors=True)

    def add_event(self, event_id, days_ago, thumbnail_path=None, video_path=None):
        db = self.SessionLocal()
        try:
            db.add(Event(
                id=event_id,
                camera_id="cam-1",
                timestamp=_aware(days_ago),
                description="desc",
                confidence=80,
                objects_detected='["person"]',
                thumbnail_path=thumbnail_path,
                video_path=video_path,
                alert_triggered=False,
            ))
            db.commit()
        finally:
            db.close()


@pytest.fixture
def harness():
    box = _CleanupHarness()
    try:
        yield box
    finally:
        box.close()


def _write(path: str, payload: bytes = b"data") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)


def _age(path: str, days: int) -> None:
    stamp = (datetime.now() - timedelta(days=days)).timestamp()
    os.utime(path, (stamp, stamp))


class TestEventMediaCleanup:
    @pytest.mark.asyncio
    async def test_api_url_thumbnail_and_annotated_sibling_are_deleted(self, harness):
        day = "2025-01-01"
        original = os.path.join(harness.thumbnail_dir, day, "old.jpg")
        annotated = os.path.join(harness.thumbnail_dir, day, "old_annotated.jpg")
        _write(original, b"x" * 2048)
        _write(annotated, b"y" * 1024)
        harness.add_event(
            "old-1",
            45,
            thumbnail_path=f"/api/v1/thumbnails/{day}/old.jpg",
        )

        stats = await harness.service.cleanup_old_events(retention_days=30)

        assert stats["events_deleted"] == 1
        assert stats["thumbnails_deleted"] == 2
        assert stats["thumbnails_failed"] == 0
        assert not os.path.exists(original)
        assert not os.path.exists(annotated)

    @pytest.mark.asyncio
    async def test_recent_thumbnail_is_kept(self, harness):
        path = os.path.join(harness.thumbnail_dir, "2026-09-01", "keep.jpg")
        _write(path, b"keep")
        harness.add_event("recent-1", 2, thumbnail_path="/api/v1/thumbnails/2026-09-01/keep.jpg")

        stats = await harness.service.cleanup_old_events(retention_days=30)

        assert stats["events_deleted"] == 0
        assert os.path.exists(path)

    @pytest.mark.asyncio
    async def test_event_video_file_deleted_when_video_path_is_null(self, harness):
        video = os.path.join(harness.video_dir, "old-vid.mp4")
        _write(video, b"v" * 4096)
        harness.add_event("old-vid", 40, video_path=None)

        stats = await harness.service.cleanup_old_events(retention_days=30)

        assert stats["events_deleted"] == 1
        assert stats["videos_deleted"] == 1
        assert not os.path.exists(video)

    @pytest.mark.asyncio
    async def test_child_rows_and_preexisting_orphans_are_removed(self, harness):
        now = datetime.now(timezone.utc)
        db = harness.SessionLocal()
        try:
            db.add(Event(
                id="old-child",
                camera_id="cam-1",
                timestamp=_aware(40),
                description="old",
                confidence=50,
                objects_detected="[]",
                alert_triggered=False,
            ))
            db.add(Event(
                id="live-child",
                camera_id="cam-1",
                timestamp=_aware(1),
                description="live",
                confidence=50,
                objects_detected="[]",
                alert_triggered=False,
            ))
            db.add(RecognizedEntity(
                id="entity-1",
                entity_type="person",
                reference_embedding="[0.1]",
                first_seen_at=now,
                last_seen_at=now,
                occurrence_count=1,
            ))
            db.add(EntityEvent(
                entity_id="entity-1",
                event_id="old-child",
                similarity_score=0.9,
            ))
            db.add(EntityEvent(
                entity_id="entity-1",
                event_id="live-child",
                similarity_score=0.8,
            ))
            # Row whose event is already gone (FK enforcement was off).
            db.add(EntityEvent(
                entity_id="entity-1",
                event_id="missing-event",
                similarity_score=0.5,
            ))
            db.add(EventFrame(
                id="frame-old",
                event_id="old-child",
                frame_number=1,
                frame_path="frames/old-child/frame_001.jpg",
                timestamp_offset_ms=0,
            ))
            db.add(EventFrame(
                id="frame-orphan",
                event_id="missing-event",
                frame_number=1,
                frame_path="frames/missing/frame_001.jpg",
                timestamp_offset_ms=0,
            ))
            db.add(EventEmbedding(
                id="emb-old",
                event_id="old-child",
                embedding="[0.1]",
                model_version="clip-test",
            ))
            db.add(EventEmbedding(
                id="emb-live",
                event_id="live-child",
                embedding="[0.2]",
                model_version="clip-test",
            ))
            db.add(AIUsage(
                timestamp=now,
                provider="openai",
                success=True,
                tokens_used=10,
                response_time_ms=20,
                cost_estimate=0.01,
            ))
            db.commit()
        finally:
            db.close()

        stats = await harness.service.cleanup_old_events(retention_days=30)

        db = harness.SessionLocal()
        try:
            assert stats["events_deleted"] == 1
            assert stats["dependents_deleted"] >= 3
            assert stats["orphan_dependents_deleted"] >= 2
            assert db.query(Event).filter(Event.id == "live-child").count() == 1
            assert db.query(EntityEvent).filter(EntityEvent.event_id == "old-child").count() == 0
            assert db.query(EntityEvent).filter(EntityEvent.event_id == "missing-event").count() == 0
            assert db.query(EntityEvent).filter(EntityEvent.event_id == "live-child").count() == 1
            assert db.query(EventFrame).count() == 0
            assert db.query(EventEmbedding).filter(EventEmbedding.event_id == "live-child").count() == 1
            assert db.query(EventEmbedding).filter(EventEmbedding.event_id == "old-child").count() == 0
            # ai_usage has no event_id; cost history is not event media.
            assert db.query(AIUsage).count() == 1
            assert db.query(RecognizedEntity).count() == 1
        finally:
            db.close()


class TestVideoAndOrphanMedia:
    @pytest.mark.asyncio
    async def test_video_cleanup_removes_old_and_orphan_files_only(self, harness):
        recent = os.path.join(harness.video_dir, "recent-event.mp4")
        old_named = os.path.join(harness.video_dir, "old-event.mp4")
        linked = os.path.join(harness.video_dir, "linked.mp4")
        orphan = os.path.join(harness.video_dir, "orphan-clip.mp4")
        fresh_orphan = os.path.join(harness.video_dir, "still-writing.mp4")
        for path in (recent, old_named, linked, orphan, fresh_orphan):
            _write(path, b"v" * 100)
        _age(recent, 40)  # old mtime, but the event is inside the window
        _age(orphan, 40)
        _age(old_named, 1)  # new mtime, but the event is past video retention
        harness.add_event("recent-event", 3, video_path=None)
        harness.add_event("old-event", 20, video_path=None)
        harness.add_event("linked-event", 20, video_path="videos/linked.mp4")

        stats = await harness.service.cleanup_old_videos(video_retention_days=7)

        assert os.path.exists(recent)
        assert os.path.exists(fresh_orphan)
        assert not os.path.exists(old_named)
        assert not os.path.exists(linked)
        assert not os.path.exists(orphan)
        assert stats["videos_deleted"] >= 3
        assert stats["orphans_deleted"] >= 1
        assert stats["events_updated"] == 1

        db = harness.SessionLocal()
        try:
            linked_row = db.query(Event).filter(Event.id == "linked-event").one()
            assert linked_row.video_path is None
            recent_row = db.query(Event).filter(Event.id == "recent-event").one()
            assert recent_row.id == "recent-event"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_video_cleanup_skips_forever(self, harness):
        path = os.path.join(harness.video_dir, "keep.mp4")
        _write(path)
        _age(path, 90)
        stats = await harness.service.cleanup_old_videos(video_retention_days=0)
        assert stats["skipped"] is True
        assert os.path.exists(path)

    def test_orphan_sweep_keeps_entity_and_in_window_thumbnails(self, harness):
        now = datetime.now(timezone.utc)
        entity_file = os.path.join(harness.thumbnail_dir, "2020-01-01", "entity.jpg")
        live_file = os.path.join(harness.thumbnail_dir, "2020-01-01", "live.jpg")
        orphan_file = os.path.join(harness.thumbnail_dir, "2020-01-01", "orphan.jpg")
        recent_dir = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        recent_file = os.path.join(harness.thumbnail_dir, recent_dir, "unreferenced.jpg")
        _write(entity_file, b"e" * 100)
        _write(live_file, b"l" * 100)
        _write(orphan_file, b"o" * 100)
        _write(recent_file, b"r" * 100)
        for path in (entity_file, live_file, orphan_file):
            _age(path, 400)

        harness.add_event(
            "live-event",
            2,
            thumbnail_path="/api/v1/thumbnails/2020-01-01/live.jpg",
        )
        db = harness.SessionLocal()
        try:
            db.add(RecognizedEntity(
                id="vip",
                entity_type="person",
                reference_embedding="[0.1]",
                first_seen_at=now,
                last_seen_at=now,
                occurrence_count=2,
                thumbnail_path="/api/v1/thumbnails/2020-01-01/entity.jpg",
            ))
            db.commit()
        finally:
            db.close()

        live_frames = os.path.join(harness.frames_dir, "live-event")
        orphan_frames = os.path.join(harness.frames_dir, "gone-event")
        fresh_frames = os.path.join(harness.frames_dir, "incoming-event")
        _write(os.path.join(live_frames, "frame_001.jpg"))
        _write(os.path.join(orphan_frames, "frame_001.jpg"))
        _write(os.path.join(fresh_frames, "frame_001.jpg"))
        _age(os.path.join(live_frames, "frame_001.jpg"), 400)
        _age(os.path.join(orphan_frames, "frame_001.jpg"), 400)
        _age(live_frames, 400)
        _age(orphan_frames, 400)

        stats = harness.service.cleanup_orphan_media(retention_days=30)

        assert os.path.exists(entity_file)
        assert os.path.exists(live_file)
        assert os.path.exists(recent_file)
        assert not os.path.exists(orphan_file)
        assert os.path.isdir(live_frames)
        assert os.path.isdir(fresh_frames)
        assert not os.path.exists(orphan_frames)
        assert stats["thumbnails_deleted"] == 1
        assert stats["frame_dirs_deleted"] == 1
        assert stats["skipped"] is False

    def test_orphan_sweep_skips_when_entity_protection_lookup_fails(
        self, harness, monkeypatch
    ):
        """A failed named-entity thumbnail lookup deletes nothing and reports skipped."""
        orphan = os.path.join(harness.thumbnail_dir, "2020-01-01", "orphan.jpg")
        entity_file = os.path.join(harness.thumbnail_dir, "2020-01-01", "entity.jpg")
        _write(orphan, b"o" * 100)
        _write(entity_file, b"e" * 100)
        _age(orphan, 400)
        _age(entity_file, 400)
        orphan_frames = os.path.join(harness.frames_dir, "gone-event")
        _write(os.path.join(orphan_frames, "frame_001.jpg"))
        _age(os.path.join(orphan_frames, "frame_001.jpg"), 400)
        _age(orphan_frames, 400)

        def _raise(_db):
            raise RuntimeError("protected entity lookup failed")

        monkeypatch.setattr(
            harness.service, "_protected_entity_thumbnail_keys", _raise
        )

        stats = harness.service.cleanup_orphan_media(retention_days=30)

        assert os.path.exists(orphan)
        assert os.path.exists(entity_file)
        assert os.path.isdir(orphan_frames)
        assert stats["skipped"] is True
        assert stats["thumbnails_deleted"] == 0
        assert stats["frames_deleted"] == 0
        assert stats["frame_dirs_deleted"] == 0

    def test_orphan_media_skips_when_retention_forever(self, harness):
        orphan = os.path.join(harness.thumbnail_dir, "2020-01-01", "orphan.jpg")
        _write(orphan)
        _age(orphan, 400)
        stats = harness.service.cleanup_orphan_media(retention_days=-1)
        assert stats["skipped"] is True
        assert os.path.exists(orphan)


class TestRetentionSettings:
    @pytest.fixture
    def db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        session = Session()
        try:
            yield session
        finally:
            session.close()
            engine.dispose()
            os.remove(path)

    def test_ui_key_wins_and_both_keys_are_synced(self, db):
        db.add(SystemSetting(key="settings_retention_days", value="7"))
        db.add(SystemSetting(key="data_retention_days", value="30"))
        db.commit()

        assert reconcile_retention_policy(db) == 7
        db.expire_all()
        stored = {row.key: row.value for row in db.query(SystemSetting).all()}
        assert stored["settings_retention_days"] == "7"
        assert stored["data_retention_days"] == "7"

    def test_legacy_key_is_copied_when_ui_key_missing(self, db):
        db.add(SystemSetting(key="data_retention_days", value="90"))
        db.commit()

        assert reconcile_retention_policy(db) == 90
        db.expire_all()
        ui = db.query(SystemSetting).filter(
            SystemSetting.key == "settings_retention_days"
        ).one()
        assert ui.value == "90"

    def test_missing_keys_default_without_writing(self, db):
        assert reconcile_retention_policy(db) == 30
        assert db.query(SystemSetting).count() == 0

    def test_auto_cleanup_defaults_on_and_can_disable(self, db):
        assert is_auto_cleanup_enabled(db) is True
        db.add(SystemSetting(key="settings_auto_cleanup", value="False"))
        db.commit()
        assert is_auto_cleanup_enabled(db) is False

    def test_video_retention_days(self, db):
        assert get_video_retention_days(db) == 30
        db.add(SystemSetting(key="settings_video_retention_days", value="7"))
        db.commit()
        assert get_video_retention_days(db) == 7
        db.query(SystemSetting).filter(
            SystemSetting.key == "settings_video_retention_days"
        ).update({"value": "0"})
        db.commit()
        assert get_video_retention_days(db) == 0


class TestScheduledJobs:
    def test_video_cleanup_job_is_registered(self):
        class _Scheduler:
            def __init__(self):
                self.jobs = []

            def add_job(self, func, **kwargs):
                self.jobs.append({"func": func, **kwargs})

        scheduler = _Scheduler()
        register_retention_jobs(scheduler)
        by_id = {job["id"]: job for job in scheduler.jobs}
        assert set(by_id) == {"daily_cleanup", "daily_video_cleanup"}
        assert by_id["daily_cleanup"]["func"] is scheduled_cleanup_job
        assert by_id["daily_video_cleanup"]["func"] is scheduled_video_cleanup_job
        event_trigger = str(by_id["daily_cleanup"]["trigger"])
        video_trigger = str(by_id["daily_video_cleanup"]["trigger"])
        assert "hour='2'" in event_trigger and "minute='0'" in event_trigger
        assert "hour='2'" in video_trigger and "minute='15'" in video_trigger

    @pytest.mark.asyncio
    async def test_cleanup_job_skips_when_auto_cleanup_disabled(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "app.services.retention_jobs.is_auto_cleanup_enabled",
            lambda: False,
        )
        monkeypatch.setattr(
            "app.services.retention_jobs.reconcile_retention_policy",
            lambda: called.append("reconcile") or 7,
        )
        await scheduled_cleanup_job()
        await scheduled_video_cleanup_job()
        assert called == []

    @pytest.mark.asyncio
    async def test_cleanup_job_skips_event_delete_when_forever(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.retention_jobs.is_auto_cleanup_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            "app.services.retention_jobs.reconcile_retention_policy",
            lambda: -1,
        )

        class _Service:
            def __init__(self):
                self.orphan_calls = 0

            def delete_orphan_dependents(self):
                self.orphan_calls += 1
                return {"entity_events": 3}

            async def cleanup_old_events(self, **kwargs):
                raise AssertionError("events must not be deleted when retention <= 0")

            def cleanup_orphan_media(self, **kwargs):
                raise AssertionError("media must not be swept when retention <= 0")

        service = _Service()
        monkeypatch.setattr(
            "app.services.retention_jobs.get_cleanup_service",
            lambda: service,
        )
        await scheduled_cleanup_job()
        assert service.orphan_calls == 1

    @pytest.mark.asyncio
    async def test_cleanup_job_runs_events_and_orphan_media(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.retention_jobs.is_auto_cleanup_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            "app.services.retention_jobs.reconcile_retention_policy",
            lambda: 7,
        )

        class _Service:
            def __init__(self):
                self.event_days = None
                self.media_days = None

            async def cleanup_old_events(self, retention_days):
                self.event_days = retention_days
                return {"events_deleted": 2, "space_freed_mb": 1.5}

            def cleanup_orphan_media(self, retention_days):
                self.media_days = retention_days
                return {"thumbnails_deleted": 4}

        service = _Service()
        monkeypatch.setattr(
            "app.services.retention_jobs.get_cleanup_service",
            lambda: service,
        )
        await scheduled_cleanup_job()
        assert service.event_days == 7
        assert service.media_days == 7

    @pytest.mark.asyncio
    async def test_video_job_uses_configured_days(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.retention_jobs.is_auto_cleanup_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            "app.services.retention_jobs.get_video_retention_days",
            lambda: 7,
        )

        class _Service:
            def __init__(self):
                self.days = None

            async def cleanup_old_videos(self, video_retention_days):
                self.days = video_retention_days
                return {"videos_deleted": 5, "space_freed_mb": 10}

        service = _Service()
        monkeypatch.setattr(
            "app.services.retention_jobs.get_cleanup_service",
            lambda: service,
        )
        await scheduled_video_cleanup_job()
        assert service.days == 7

    @pytest.mark.asyncio
    async def test_video_job_skips_forever(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.retention_jobs.is_auto_cleanup_enabled",
            lambda: True,
        )
        monkeypatch.setattr(
            "app.services.retention_jobs.get_video_retention_days",
            lambda: 0,
        )
        monkeypatch.setattr(
            "app.services.retention_jobs.get_cleanup_service",
            lambda: (_ for _ in ()).throw(AssertionError("should not run")),
        )
        await scheduled_video_cleanup_job()


def test_sqlite_foreign_keys_enabled_on_connect():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
