"""Pytest fixtures and configuration for test suite

This module provides:
1. Database session fixtures for test isolation
2. Factory functions for creating test objects with sensible defaults
3. Pytest fixtures that use the factory functions

Factory Functions:
    - make_event(**overrides) -> Event
    - make_camera(**overrides) -> Camera
    - make_alert_rule(**overrides) -> AlertRule
    - make_entity(**overrides) -> RecognizedEntity

Each factory accepts an optional db_session parameter to persist objects.
"""
import json
import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, get_db
from app.models.event import Event
from app.models.camera import Camera
from app.models.alert_rule import AlertRule
from app.models.recognized_entity import RecognizedEntity
import os
import tempfile


# =============================================================================
# Factory Functions for Test Objects
# =============================================================================

def make_event(
    db_session=None,
    id: str = None,
    camera_id: str = "camera-001",
    timestamp: datetime = None,
    description: str = "Test event - person walking in frame",
    confidence: int = 85,
    objects_detected: str = '["person"]',
    source_type: str = "protect",
    alert_triggered: bool = False,
    **overrides
) -> Event:
    """
    Factory function to create Event instances for testing.

    Args:
        db_session: Optional SQLAlchemy session. If provided, adds and commits the event.
        id: UUID string. If None, generates a new UUID.
        camera_id: Camera ID the event belongs to.
        timestamp: Event timestamp. If None, uses current UTC time.
        description: AI-generated description.
        confidence: Confidence score (0-100).
        objects_detected: JSON array of detected objects.
        source_type: Event source ('rtsp', 'usb', 'protect').
        alert_triggered: Whether an alert was triggered.
        **overrides: Any additional Event model fields.

    Returns:
        Event instance (persisted if db_session provided).

    Example:
        event = make_event(description="A person at the door")
        event = make_event(db_session=session, camera_id=camera.id)
    """
    if id is None:
        id = str(uuid.uuid4())
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    event = Event(
        id=id,
        camera_id=camera_id,
        timestamp=timestamp,
        description=description,
        confidence=confidence,
        objects_detected=objects_detected,
        source_type=source_type,
        alert_triggered=alert_triggered,
        **overrides
    )

    if db_session:
        db_session.add(event)
        db_session.commit()

    return event


def make_camera(
    db_session=None,
    id: str = None,
    name: str = "Test Camera",
    type: str = "rtsp",
    rtsp_url: str = "rtsp://test.local:554/stream1",
    source_type: str = "rtsp",
    is_enabled: bool = True,
    frame_rate: int = 5,
    motion_enabled: bool = True,
    motion_sensitivity: str = "medium",
    motion_cooldown: int = 60,
    motion_algorithm: str = "mog2",
    analysis_mode: str = "single_frame",
    homekit_stream_quality: str = "medium",
    **overrides
) -> Camera:
    """
    Factory function to create Camera instances for testing.

    Args:
        db_session: Optional SQLAlchemy session. If provided, adds and commits the camera.
        id: UUID string. If None, generates a new UUID.
        name: User-friendly camera name.
        type: Camera type ('rtsp' or 'usb').
        rtsp_url: RTSP URL for the camera.
        source_type: Camera source ('rtsp', 'usb', 'protect').
        is_enabled: Whether camera capture is active.
        frame_rate: Target frames per second.
        motion_enabled: Whether motion detection is active.
        motion_sensitivity: Sensitivity level ('low', 'medium', 'high').
        motion_cooldown: Seconds between motion triggers.
        motion_algorithm: Detection algorithm ('mog2', 'knn', 'frame_diff').
        analysis_mode: AI analysis mode.
        homekit_stream_quality: HomeKit streaming quality.
        **overrides: Any additional Camera model fields.

    Returns:
        Camera instance (persisted if db_session provided).

    Example:
        camera = make_camera(name="Front Door")
        camera = make_camera(db_session=session, source_type="protect")
    """
    if id is None:
        id = str(uuid.uuid4())

    camera = Camera(
        id=id,
        name=name,
        type=type,
        rtsp_url=rtsp_url,
        source_type=source_type,
        is_enabled=is_enabled,
        frame_rate=frame_rate,
        motion_enabled=motion_enabled,
        motion_sensitivity=motion_sensitivity,
        motion_cooldown=motion_cooldown,
        motion_algorithm=motion_algorithm,
        analysis_mode=analysis_mode,
        homekit_stream_quality=homekit_stream_quality,
        **overrides
    )

    if db_session:
        db_session.add(camera)
        db_session.commit()

    return camera


def make_alert_rule(
    db_session=None,
    id: str = None,
    name: str = "Test Alert Rule",
    is_enabled: bool = True,
    conditions: dict = None,
    actions: dict = None,
    cooldown_minutes: int = 5,
    entity_match_mode: str = "any",
    **overrides
) -> AlertRule:
    """
    Factory function to create AlertRule instances for testing.

    Args:
        db_session: Optional SQLAlchemy session. If provided, adds and commits the rule.
        id: UUID string. If None, generates a new UUID.
        name: Human-readable rule name.
        is_enabled: Whether rule is active.
        conditions: Dict of match criteria. Defaults to match any person.
        actions: Dict of triggered actions. Defaults to dashboard notification.
        cooldown_minutes: Minimum time between triggers.
        entity_match_mode: Entity matching mode ('any', 'specific', 'unknown').
        **overrides: Any additional AlertRule model fields.

    Returns:
        AlertRule instance (persisted if db_session provided).

    Example:
        rule = make_alert_rule(name="Package Alert")
        rule = make_alert_rule(db_session=session, conditions={"object_types": ["vehicle"]})
    """
    if id is None:
        id = str(uuid.uuid4())

    if conditions is None:
        conditions = {
            "object_types": ["person"],
            "cameras": [],
            "min_confidence": 70
        }

    if actions is None:
        actions = {
            "dashboard_notification": True
        }

    rule = AlertRule(
        id=id,
        name=name,
        is_enabled=is_enabled,
        conditions=json.dumps(conditions),
        actions=json.dumps(actions),
        cooldown_minutes=cooldown_minutes,
        entity_match_mode=entity_match_mode,
        **overrides
    )

    if db_session:
        db_session.add(rule)
        db_session.commit()

    return rule


def make_entity(
    db_session=None,
    id: str = None,
    entity_type: str = "person",
    name: str = None,
    reference_embedding: str = None,
    first_seen_at: datetime = None,
    last_seen_at: datetime = None,
    occurrence_count: int = 1,
    is_vip: bool = False,
    is_blocked: bool = False,
    **overrides
) -> RecognizedEntity:
    """
    Factory function to create RecognizedEntity instances for testing.

    Args:
        db_session: Optional SQLAlchemy session. If provided, adds and commits the entity.
        id: UUID string. If None, generates a new UUID.
        entity_type: Type of entity ('person', 'vehicle', 'unknown').
        name: User-assigned name (optional).
        reference_embedding: JSON array of 512 floats. If None, generates dummy embedding.
        first_seen_at: Timestamp of first occurrence. If None, uses current UTC time.
        last_seen_at: Timestamp of most recent occurrence. If None, uses current UTC time.
        occurrence_count: Number of times entity has been seen.
        is_vip: VIP entities trigger high-priority notifications.
        is_blocked: Blocked entities suppress notifications.
        **overrides: Any additional RecognizedEntity model fields.

    Returns:
        RecognizedEntity instance (persisted if db_session provided).

    Example:
        entity = make_entity(name="John")
        entity = make_entity(db_session=session, entity_type="vehicle", name="White SUV")
    """
    if id is None:
        id = str(uuid.uuid4())

    if first_seen_at is None:
        first_seen_at = datetime.now(timezone.utc)

    if last_seen_at is None:
        last_seen_at = datetime.now(timezone.utc)

    if reference_embedding is None:
        # Generate a dummy 512-dimensional embedding
        reference_embedding = json.dumps([0.1] * 512)

    entity = RecognizedEntity(
        id=id,
        entity_type=entity_type,
        name=name,
        reference_embedding=reference_embedding,
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        occurrence_count=occurrence_count,
        is_vip=is_vip,
        is_blocked=is_blocked,
        **overrides
    )

    if db_session:
        db_session.add(entity)
        db_session.commit()

    return entity


# =============================================================================
# Pytest Fixtures Using Factory Functions
# =============================================================================

@pytest.fixture
def sample_camera(db_session):
    """Create a sample camera for testing using factory function."""
    return make_camera(db_session=db_session)


@pytest.fixture
def sample_event(db_session, sample_camera):
    """Create a sample event for testing using factory function."""
    return make_event(db_session=db_session, camera_id=sample_camera.id)


@pytest.fixture
def sample_alert_rule(db_session):
    """Create a sample alert rule for testing using factory function."""
    return make_alert_rule(db_session=db_session)


@pytest.fixture
def sample_entity(db_session):
    """Create a sample recognized entity for testing using factory function."""
    return make_entity(db_session=db_session)


# =============================================================================
# Database Session Fixtures
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def clear_app_overrides():
    """
    Session-scoped fixture to ensure app.dependency_overrides is cleared
    at the start and end of the test session.

    This prevents state pollution between test modules.
    """
    from main import app

    # Clear any existing overrides at session start
    app.dependency_overrides.clear()

    yield

    # Clear overrides at session end
    app.dependency_overrides.clear()




@pytest.fixture(scope="function")
def db_session():
    """
    Create an in-memory SQLite database for testing

    Yields:
        SQLAlchemy Session for test database

    Cleanup:
        Drops all tables after test completes
    """
    # Create in-memory database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )

    # Create all tables
    Base.metadata.create_all(engine)

    # Create session
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture(scope="function")
def temp_db_file():
    """
    Create a temporary SQLite database file for integration tests

    Yields:
        Path to temporary database file

    Cleanup:
        Removes temporary file after test completes
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)
