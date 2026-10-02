"""A full connection pool must not wedge the process.

The entities page fires many thumbnail reads at once. Each used to keep a
pooled connection until the file response finished, and authentication checked
that pool out on the asyncio thread. A full pool then blocked the event loop
for the checkout timeout, so /health and the Protect reconnect stopped.

These tests use a one-connection QueuePool (the failure mode) even though the
file SQLite engine itself is NullPool.
"""
import asyncio
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool

import main
from app.core.config import settings
from app.core.database import Base, engine as app_engine
from app.core.database import get_db
from app.middleware import auth_middleware
from app.models.event import Event
from app.models.recognized_entity import EntityEvent, RecognizedEntity
from app.models.user import User, UserRole
from app.utils.jwt import create_access_token
from main import app


pytestmark = pytest.mark.real_auth_middleware


def test_sqlite_file_engine_does_not_use_queue_pool():
    """Production SQLite must not wait on QueuePool's checkout lock."""
    url = settings.DATABASE_URL
    if not url.startswith("sqlite"):
        pytest.skip("queue-pool settings apply only when the app database is Postgres")
    if ":memory:" in url or "mode=memory" in url:
        assert isinstance(app_engine.pool, StaticPool)
    else:
        assert isinstance(app_engine.pool, NullPool)


def _tiny_pool():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    pool_engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=2,
    )
    Base.metadata.create_all(bind=pool_engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=pool_engine)
    return pool_engine, factory, path


def _seed(factory, thumbnail_dir):
    now = datetime.now(timezone.utc)
    user = User(
        id=str(uuid.uuid4()),
        username=f"viewer_{uuid.uuid4().hex[:8]}",
        password_hash="x" * 60,
        role=UserRole.VIEWER,
        is_active=True,
    )
    entity = RecognizedEntity(
        id=str(uuid.uuid4()),
        entity_type="unknown",
        name=None,
        reference_embedding="[0.1]",
        first_seen_at=now,
        last_seen_at=now,
        occurrence_count=2,
        is_vip=False,
        is_blocked=False,
        created_at=now,
        updated_at=now,
    )
    event = Event(
        id=str(uuid.uuid4()),
        camera_id=str(uuid.uuid4()),
        timestamp=now,
        description="Person at the door",
        confidence=80,
        objects_detected='["person"]',
        source_type="protect",
    )
    link = EntityEvent(
        entity_id=entity.id,
        event_id=event.id,
        similarity_score=0.91,
        created_at=now,
    )
    db = factory()
    try:
        db.add_all([user, entity, event, link])
        db.commit()
        user_id, username, entity_id = user.id, user.username, entity.id
    finally:
        db.close()

    day = thumbnail_dir / "2026-06-01"
    day.mkdir(parents=True)
    names = []
    for index in range(6):
        name = f"thumb-{index}.jpg"
        (day / name).write_bytes(b"jpeg")
        names.append(name)
    token = create_access_token(user_id, username)
    return token, entity_id, names


@pytest.fixture
def pool_app(monkeypatch, tmp_path):
    pool_engine, factory, path = _tiny_pool()
    monkeypatch.setattr("app.core.database.SessionLocal", factory)
    monkeypatch.setattr(main, "THUMBNAIL_DIR", tmp_path / "thumbnails")
    token, entity_id, names = _seed(factory, tmp_path / "thumbnails")

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield {
            "engine": pool_engine,
            "factory": factory,
            "token": token,
            "entity_id": entity_id,
            "names": names,
        }
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        pool_engine.dispose()
        if os.path.exists(path):
            os.remove(path)


def test_pool_wait_on_auth_does_not_stall_health(pool_app, monkeypatch):
    """A checked-out connection must not freeze /health on the event loop.

    The extra connection is held with ``engine.connect()`` for the whole
    attempt. A session ``execute()`` result can be collected and returned to
    the pool, which would hide the stall.
    """
    idents = []
    original = auth_middleware._load_session_user

    def _record_thread(user_id):
        idents.append(threading.get_ident())
        return original(user_id)

    monkeypatch.setattr(auth_middleware, "_load_session_user", _record_thread)
    held = pool_app["engine"].connect()
    held.execute(text("SELECT 1"))
    assert pool_app["engine"].pool.checkedout() == 1

    async def _run():
        cookies = {"access_token": pool_app["token"]}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.perf_counter()
            thumbs = [
                asyncio.create_task(
                    client.get(
                        f"/api/v1/thumbnails/2026-06-01/{name}",
                        cookies=cookies,
                    )
                )
                for name in pool_app["names"][:4]
            ]
            # Let the thumbnail auth reach the pool before measuring health.
            await asyncio.sleep(0.05)
            assert pool_app["engine"].pool.checkedout() == 1
            health = await asyncio.wait_for(client.get("/health"), timeout=0.75)
            elapsed = time.perf_counter() - started
            still_waiting = [task for task in thumbs if not task.done()]
            held.close()
            done, pending = await asyncio.wait(thumbs, timeout=5)
            statuses = []
            for task in done:
                exc = task.exception()
                statuses.append(exc if exc is not None else task.result().status_code)
            for task in pending:
                task.cancel()
            return health, elapsed, len(still_waiting), statuses

    try:
        health, elapsed, still_waiting, statuses = asyncio.run(_run())
    finally:
        if not held.closed:
            held.close()

    assert health.status_code == 200
    assert health.json()["status"] == "healthy"
    assert elapsed < 0.75
    assert still_waiting, "thumbnail requests were not blocked by the held connection"
    assert statuses
    assert statuses == [200] * len(statuses)
    assert idents, "thumbnail auth never reached the database"
    assert all(ident != threading.get_ident() for ident in idents)


def test_concurrent_thumbnails_release_connection_before_file_send(pool_app, monkeypatch):
    """File responses overlap, so a connection is not held for the whole send."""
    from starlette.responses import FileResponse

    peak = 0
    in_flight = 0
    original_call = FileResponse.__call__

    async def _slow_send(self, scope, receive, send):
        nonlocal peak, in_flight
        in_flight += 1
        peak = max(peak, in_flight)
        try:
            await asyncio.sleep(0.35)
            return await original_call(self, scope, receive, send)
        finally:
            in_flight -= 1

    monkeypatch.setattr(FileResponse, "__call__", _slow_send)

    async def _run():
        cookies = {"access_token": pool_app["token"]}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.perf_counter()
            thumb_tasks = [
                asyncio.create_task(
                    client.get(
                        f"/api/v1/thumbnails/2026-06-01/{name}",
                        cookies=cookies,
                    )
                )
                for name in pool_app["names"]
            ]
            detail_task = asyncio.create_task(
                client.get(
                    f"/api/v1/context/entities/{pool_app['entity_id']}",
                    cookies=cookies,
                )
            )
            health_started = time.perf_counter()
            health = await asyncio.wait_for(client.get("/health"), timeout=0.75)
            health_elapsed = time.perf_counter() - health_started
            thumbs = await asyncio.wait_for(
                asyncio.gather(*thumb_tasks),
                timeout=2,
            )
            detail = await asyncio.wait_for(detail_task, timeout=2)
            elapsed = time.perf_counter() - started
            return health, health_elapsed, thumbs, detail, elapsed

    health, health_elapsed, thumbs, detail, elapsed = asyncio.run(_run())

    assert health.status_code == 200
    assert health_elapsed < 0.75
    assert all(response.status_code == 200 for response in thumbs)
    assert all(response.content == b"jpeg" for response in thumbs)
    assert elapsed < 1.2
    assert peak >= 2
    assert pool_app["engine"].pool.checkedout() == 0

    body = detail.json()
    assert detail.status_code == 200
    assert body["entity_type"] == "unknown"
    assert body["name"] is None
    assert len(body["recent_events"]) == 1
    assert body["recent_events"][0]["description"] == "Person at the door"
