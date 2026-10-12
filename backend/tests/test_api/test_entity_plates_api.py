"""Plate endpoints: status, add (hashed at once), list without plate data, remove, clear, roles."""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.models.entity_plate import EntityPlate
from app.models.user import UserRole
from app.services import entity_plate_service as eps
from app.services import plate_reader as pr
from main import app
from tests.conftest import make_entity

SALT = "api-test-salt-not-a-secret-0002"
PLATE = "TEST 123"  # made-up
BASE = "/api/v1/context"


@pytest.fixture
def db_session(monkeypatch):
    monkeypatch.setattr(settings, "PLATE_HASH_SALT", SecretStr(SALT), raising=False)
    monkeypatch.setattr(settings, "PLATE_RECOGNITION_ENABLED", False, raising=False)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    make_entity(session, id="car", entity_type="vehicle", name="Test car")
    make_entity(session, id="pat", entity_type="person", name="Test person")
    eps.invalidate_plate_index()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def client(db_session):
    previous = app.dependency_overrides.get(get_db)

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def test_add_list_remove(client, db_session):
    r = client.post(f"{BASE}/entities/car/plates", json={"plate": PLATE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "enrolled" and body["plate"]["source"] == "manual" and body["plate"]["usable"]
    digest = pr.hash_plate(PLATE)
    assert "TEST123" not in r.text and "TEST 123" not in r.text and digest not in r.text
    assert db_session.query(EntityPlate).one().plate_hash == digest

    again = client.post(f"{BASE}/entities/car/plates", json={"plate": "test-123"})
    assert again.json()["status"] == "already_enrolled"

    listed = client.get(f"{BASE}/entities/car/plates")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()["plates"]] == [body["plate"]["id"]]
    assert digest not in listed.text

    pid = body["plate"]["id"]
    assert client.delete(f"{BASE}/entities/car/plates/{pid}").json() == {"deleted_count": 1}
    assert client.delete(f"{BASE}/entities/car/plates/{pid}").status_code == 404


def test_validation_and_errors_do_not_echo_the_plate(client):
    r = client.post(f"{BASE}/entities/car/plates", json={"plate": "!!!!"})
    assert r.status_code == 422 and "!!!!" not in r.text
    r = client.post(f"{BASE}/entities/car/plates", json={"plate": "X" * 30})
    assert r.status_code == 422 and "X" * 30 not in r.text
    assert client.post(f"{BASE}/entities/pat/plates", json={"plate": PLATE}).status_code == 400
    assert client.post(f"{BASE}/entities/nope/plates", json={"plate": PLATE}).status_code == 404
    assert client.get(f"{BASE}/entities/pat/plates").status_code == 400


def test_no_salt_refuses_to_store(client, monkeypatch):
    monkeypatch.setattr(settings, "PLATE_HASH_SALT", None, raising=False)
    r = client.post(f"{BASE}/entities/car/plates", json={"plate": PLATE})
    assert r.status_code == 409


def test_status_and_clear(client):
    client.post(f"{BASE}/entities/car/plates", json={"plate": PLATE})
    status = client.get(f"{BASE}/plates/status").json()
    assert status["enabled"] is False and status["active"] is False and status["salt_configured"] is True
    assert status["vehicles_with_plates"] == 1 and status["saved_plates"] == 1
    assert client.delete(f"{BASE}/entities/car/plates").json() == {"deleted_count": 1}
    client.post(f"{BASE}/entities/car/plates", json={"plate": PLATE})
    assert client.delete(f"{BASE}/plates").json() == {"deleted_count": 1}


@pytest.mark.real_user_roles
@pytest.mark.parametrize("role,add,clear", [
    (UserRole.VIEWER, 403, 403),
    (UserRole.OPERATOR, 200, 403),
    (UserRole.ADMIN, 200, 200),
])
def test_roles(client, role, add, clear):
    from app.api.v1.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u", username="u", role=role)
    try:
        assert client.get(f"{BASE}/entities/car/plates").status_code == 200
        assert client.post(f"{BASE}/entities/car/plates", json={"plate": PLATE}).status_code == add
        assert client.delete(f"{BASE}/entities/car/plates").status_code == clear
        assert client.delete(f"{BASE}/plates").status_code == clear
    finally:
        app.dependency_overrides.pop(get_current_user, None)
