"""
Integration tests for Story P3-6.2: Vagueness Detection in Event Pipeline

Tests the end-to-end integration of vagueness detection:
- AC6: Detection runs in event pipeline after AI response
- AC6: Detection errors don't block event processing
- AC3: Vague events stored with correct low_confidence flag
- AC4: Vague events stored with vague_reason field
"""
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile
import os

from app.core.database import Base
from app.models.protect_controller import ProtectController
from app.models.camera import Camera
from app.models.event import Event
from app.services.protect_event_handler import ProtectEventHandler


# Create test database
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
os.close(test_db_fd)

TEST_DATABASE_URL = f"sqlite:///{test_db_path}"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create tables once
Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function", autouse=True)
def cleanup_database():
    """Clean up database between tests"""
    yield
    db = TestingSessionLocal()
    try:
        db.query(Event).delete()
        db.query(Camera).delete()
        db.query(ProtectController).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture
def db_session():
    """Create a test database session"""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def protect_controller(db_session):
    """Create a test Protect controller"""
    controller = ProtectController(
        id="test-ctrl-vague-001",
        name="Test Controller",
        host="192.168.1.1",
        port=443,
        username="admin",
        password="testpassword",
        is_connected=True
    )
    db_session.add(controller)
    db_session.commit()
    db_session.refresh(controller)
    return controller


@pytest.fixture
def protect_camera(db_session, protect_controller):
    """Create a test Protect camera"""
    import json
    camera = Camera(
        id="test-cam-vague-001",
        name="Test Camera",
        type="rtsp",
        source_type="protect",
        protect_controller_id=protect_controller.id,
        protect_camera_id="protect-native-001",
        smart_detection_types=json.dumps(["person", "vehicle"]),
        is_enabled=True
    )
    db_session.add(camera)
    db_session.commit()
    db_session.refresh(camera)
    return camera


@pytest.fixture
def mock_ai_service():
    """Create a mock AI service"""
    mock = MagicMock()
    mock.describe_image = AsyncMock()
    return mock


@pytest.fixture
def mock_snapshot_service():
    """Create a mock snapshot service"""
    mock = MagicMock()
    return mock


class TestVaguenessDetectionInPipeline:
    """AC6: Test vagueness detection runs in event pipeline"""

    @pytest.mark.asyncio
    async def test_vague_description_sets_low_confidence(
        self, db_session, protect_camera, mock_ai_service, mock_snapshot_service
    ):
        """AC3: Vague description should set low_confidence = True"""
        # Setup AI result with vague description (but high AI confidence)
        mock_ai_result = MagicMock()
        mock_ai_result.description = "It appears to be something moving near the front door area"
        mock_ai_result.confidence = 80
        mock_ai_result.objects_detected = ["unknown"]
        mock_ai_result.provider = "openai"
        mock_ai_result.ai_confidence = 85  # High AI confidence
        mock_ai_result.bounding_boxes = None  # Story P15-5.1

        mock_snapshot = MagicMock()
        mock_snapshot.timestamp = datetime.now(timezone.utc)
        mock_snapshot.thumbnail_path = "thumbnails/test.jpg"

        # Create handler instance (takes no constructor args)
        handler = ProtectEventHandler()

        event = await handler._store_protect_event(
            db=db_session,
            ai_result=mock_ai_result,
            snapshot_result=mock_snapshot,
            camera=protect_camera,
            event_type="motion",
            protect_event_id="test-event-1",
            is_doorbell_ring=False
        )

        # Verify event stored with low_confidence due to vague phrase
        assert event is not None
        assert event.low_confidence is True
        assert event.vague_reason is not None
        assert "appears to be" in event.vague_reason.lower()
        # AI confidence should still be stored
        assert event.ai_confidence == 85

    @pytest.mark.asyncio
    async def test_specific_description_not_flagged(
        self, db_session, protect_camera, mock_ai_service, mock_snapshot_service
    ):
        """AC5: Specific description should NOT be flagged as vague"""
        # Setup AI result with specific description
        mock_ai_result = MagicMock()
        mock_ai_result.description = "Person in blue jacket delivered package to front door and rang doorbell"
        mock_ai_result.confidence = 90
        mock_ai_result.objects_detected = ["person", "package"]
        mock_ai_result.provider = "openai"
        mock_ai_result.ai_confidence = 92
        mock_ai_result.bounding_boxes = None  # Story P15-5.1

        mock_snapshot = MagicMock()
        mock_snapshot.timestamp = datetime.now(timezone.utc)
        mock_snapshot.thumbnail_path = "thumbnails/test.jpg"

        handler = ProtectEventHandler()

        event = await handler._store_protect_event(
            db=db_session,
            ai_result=mock_ai_result,
            snapshot_result=mock_snapshot,
            camera=protect_camera,
            event_type="person",
            protect_event_id="test-event-2",
            is_doorbell_ring=False
        )

        # Verify event stored without vague flag
        assert event is not None
        assert event.low_confidence is False
        assert event.vague_reason is None
        assert event.ai_confidence == 92

    @pytest.mark.asyncio
    async def test_low_ai_confidence_still_sets_low_confidence(
        self, db_session, protect_camera, mock_ai_service, mock_snapshot_service
    ):
        """AC3: Low AI confidence should set low_confidence even if not vague"""
        # Setup AI result with specific description but low AI confidence
        mock_ai_result = MagicMock()
        mock_ai_result.description = "Person walking toward front door carrying large brown cardboard box today"
        mock_ai_result.confidence = 45
        mock_ai_result.objects_detected = ["person"]
        mock_ai_result.provider = "openai"
        mock_ai_result.ai_confidence = 35  # Below 50 threshold
        mock_ai_result.bounding_boxes = None  # Story P15-5.1

        mock_snapshot = MagicMock()
        mock_snapshot.timestamp = datetime.now(timezone.utc)
        mock_snapshot.thumbnail_path = "thumbnails/test.jpg"

        handler = ProtectEventHandler()

        event = await handler._store_protect_event(
            db=db_session,
            ai_result=mock_ai_result,
            snapshot_result=mock_snapshot,
            camera=protect_camera,
            event_type="person",
            protect_event_id="test-event-3",
            is_doorbell_ring=False
        )

        # Verify low_confidence is True due to low AI confidence (not vagueness)
        assert event is not None
        assert event.low_confidence is True
        assert event.vague_reason is None  # Not vague, just low AI confidence
        assert event.ai_confidence == 35


class TestVaguenessDetectionErrorHandling:
    """AC6: Test that detection errors don't block event processing"""

    @pytest.mark.asyncio
    async def test_detection_error_does_not_block_event(
        self, db_session, protect_camera, mock_ai_service, mock_snapshot_service
    ):
        """AC6: Detection error should not block event storage"""
        mock_ai_result = MagicMock()
        mock_ai_result.description = "Person walking to door with package in hand today"
        mock_ai_result.confidence = 80
        mock_ai_result.objects_detected = ["person"]
        mock_ai_result.provider = "openai"
        mock_ai_result.ai_confidence = 75
        mock_ai_result.bounding_boxes = None  # Story P15-5.1

        mock_snapshot = MagicMock()
        mock_snapshot.timestamp = datetime.now(timezone.utc)
        mock_snapshot.thumbnail_path = "thumbnails/test.jpg"

        handler = ProtectEventHandler()

        # Mock the detect_vague_description module to raise an exception
        with patch('app.services.description_quality.detect_vague_description') as mock_detect:
            mock_detect.side_effect = Exception("Detection service unavailable")

            event = await handler._store_protect_event(
                db=db_session,
                ai_result=mock_ai_result,
                snapshot_result=mock_snapshot,
                camera=protect_camera,
                event_type="person",
                protect_event_id="test-event-4",
                is_doorbell_ring=False
            )

        # Event should still be stored despite detection error
        assert event is not None
        assert "Person walking to door" in event.description
        # Default to not-vague when detection fails
        assert event.vague_reason is None
        # low_confidence should still reflect AI confidence
        assert event.low_confidence is False  # ai_confidence 75 >= 50


class TestVagueReasonTracking:
    """AC4: Test vague_reason field is tracked correctly"""

    @pytest.mark.asyncio
    async def test_vague_phrase_reason_stored(
        self, db_session, protect_camera, mock_ai_service, mock_snapshot_service
    ):
        """AC4: Vague phrase should be tracked in vague_reason"""
        mock_ai_result = MagicMock()
        mock_ai_result.description = "It might be a delivery driver coming to drop off a package"
        mock_ai_result.confidence = 70
        mock_ai_result.objects_detected = ["person"]
        mock_ai_result.provider = "openai"
        mock_ai_result.ai_confidence = 80
        mock_ai_result.bounding_boxes = None  # Story P15-5.1

        mock_snapshot = MagicMock()
        mock_snapshot.timestamp = datetime.now(timezone.utc)
        mock_snapshot.thumbnail_path = "thumbnails/test.jpg"

        handler = ProtectEventHandler()

        event = await handler._store_protect_event(
            db=db_session,
            ai_result=mock_ai_result,
            snapshot_result=mock_snapshot,
            camera=protect_camera,
            event_type="person",
            protect_event_id="test-event-5",
            is_doorbell_ring=False
        )

        assert event is not None
        assert event.vague_reason is not None
        assert "vague phrase" in event.vague_reason.lower()
        assert "might be" in event.vague_reason.lower()

    @pytest.mark.asyncio
    async def test_short_description_reason_stored(
        self, db_session, protect_camera, mock_ai_service, mock_snapshot_service
    ):
        """AC4: Short description should be tracked in vague_reason"""
        mock_ai_result = MagicMock()
        mock_ai_result.description = "Person at door."  # Only 3 words
        mock_ai_result.confidence = 70
        mock_ai_result.objects_detected = ["person"]
        mock_ai_result.provider = "openai"
        mock_ai_result.ai_confidence = 80
        mock_ai_result.bounding_boxes = None  # Story P15-5.1

        mock_snapshot = MagicMock()
        mock_snapshot.timestamp = datetime.now(timezone.utc)
        mock_snapshot.thumbnail_path = "thumbnails/test.jpg"

        handler = ProtectEventHandler()

        event = await handler._store_protect_event(
            db=db_session,
            ai_result=mock_ai_result,
            snapshot_result=mock_snapshot,
            camera=protect_camera,
            event_type="person",
            protect_event_id="test-event-6",
            is_doorbell_ring=False
        )

        assert event is not None
        assert event.vague_reason is not None
        assert "short" in event.vague_reason.lower() or "words" in event.vague_reason.lower()

    @pytest.mark.asyncio
    async def test_generic_phrase_reason_stored(
        self, db_session, protect_camera, mock_ai_service, mock_snapshot_service
    ):
        """AC4: Generic phrase should be tracked in vague_reason"""
        mock_ai_result = MagicMock()
        mock_ai_result.description = "Motion detected."  # Generic phrase
        mock_ai_result.confidence = 70
        mock_ai_result.objects_detected = ["unknown"]
        mock_ai_result.provider = "openai"
        mock_ai_result.ai_confidence = 80
        mock_ai_result.bounding_boxes = None  # Story P15-5.1

        mock_snapshot = MagicMock()
        mock_snapshot.timestamp = datetime.now(timezone.utc)
        mock_snapshot.thumbnail_path = "thumbnails/test.jpg"

        handler = ProtectEventHandler()

        event = await handler._store_protect_event(
            db=db_session,
            ai_result=mock_ai_result,
            snapshot_result=mock_snapshot,
            camera=protect_camera,
            event_type="motion",
            protect_event_id="test-event-7",
            is_doorbell_ring=False
        )

        assert event is not None
        assert event.vague_reason is not None
        assert "generic" in event.vague_reason.lower() or "motion detected" in event.vague_reason.lower()
