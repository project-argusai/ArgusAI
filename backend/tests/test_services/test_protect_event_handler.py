"""
Unit tests for ProtectEventHandler (Story P14-3.2)

Tests the UniFi Protect event handling: parsing, filtering, deduplication,
and event flow from WebSocket message to AI pipeline.
"""
import pytest
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock, patch, PropertyMock

from app.services.protect_event_handler import (
    ProtectEventHandler,
    get_protect_event_handler,
    EVENT_COOLDOWN_SECONDS,
    EVENT_TYPE_MAPPING,
    VALID_EVENT_TYPES,
    DOORBELL_RING_PROMPT,
    PROTECT_MOTION_EVENT,
    _format_timestamp_for_ai,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def event_handler():
    """Create a fresh ProtectEventHandler instance for testing."""
    return ProtectEventHandler()


@pytest.fixture
def mock_db_session():
    """Mock database session for camera lookups and event storage."""
    with patch('app.services.protect_event_handler.get_db_session') as mock_get:
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__ = Mock(return_value=mock_session)
        mock_context.__exit__ = Mock(return_value=False)
        mock_get.return_value = mock_context
        yield mock_session


@pytest.fixture
def mock_camera():
    """Create a mock Camera model with protect configuration."""
    camera = MagicMock()
    camera.id = "cam-123"
    camera.name = "Front Door"
    camera.is_enabled = True
    camera.source_type = "protect"
    camera.protect_camera_id = "protect-cam-456"
    camera.smart_detection_types = '["person", "vehicle", "package"]'
    camera.motion_cooldown = 60
    return camera


@pytest.fixture
def mock_doorbell():
    """Create a mock doorbell camera."""
    doorbell = MagicMock()
    doorbell.id = "doorbell-789"
    doorbell.name = "Front Doorbell"
    doorbell.is_enabled = True
    doorbell.source_type = "protect"
    doorbell.protect_camera_id = "protect-doorbell-012"
    doorbell.smart_detection_types = '["person", "ring"]'
    doorbell.motion_cooldown = 60
    return doorbell


@pytest.fixture
def mock_ws_message():
    """Factory for creating mock WebSocket messages from uiprotect."""
    def _create_message(
        model_type: str = "Camera",
        camera_id: str = "protect-cam-456",
        is_motion: bool = False,
        is_person: bool = False,
        is_vehicle: bool = False,
        is_package: bool = False,
        is_animal: bool = False,
        is_ring: bool = False,
        last_ring: datetime = None,
    ):
        mock_msg = MagicMock()
        mock_obj = MagicMock()

        # Set the model type via __name__
        type(mock_obj).__name__ = model_type

        # Set camera ID
        mock_obj.id = camera_id

        # Set detection flags
        mock_obj.is_motion_currently_detected = is_motion
        mock_obj.is_smart_currently_detected = is_person or is_vehicle or is_package or is_animal
        mock_obj.is_person_currently_detected = is_person
        mock_obj.is_vehicle_currently_detected = is_vehicle
        mock_obj.is_package_currently_detected = is_package
        mock_obj.is_animal_currently_detected = is_animal

        # Doorbell-specific
        mock_obj.last_ring = last_ring
        mock_obj.last_ring_event_id = "ring-event-123" if is_ring else None

        # Active smart types
        active_types = []
        if is_person:
            active_types.append("person")
        if is_vehicle:
            active_types.append("vehicle")
        if is_package:
            active_types.append("package")
        if is_animal:
            active_types.append("animal")
        mock_obj.active_smart_detect_types = active_types
        mock_obj.last_smart_detect_event_ids = {}

        mock_msg.new_obj = mock_obj
        return mock_msg

    return _create_message


@pytest.fixture
def mock_snapshot_service():
    """Mock the snapshot service."""
    with patch('app.services.protect_event_handler.get_snapshot_service') as mock_get:
        mock_service = AsyncMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.image_data = b"fake_image_data"
        mock_result.thumbnail_path = "/thumbnails/test.jpg"
        mock_result.timestamp = datetime.now(timezone.utc)
        mock_service.get_snapshot.return_value = mock_result
        mock_get.return_value = mock_service
        yield mock_service


@pytest.fixture
def mock_ai_service():
    """Mock the AI service."""
    with patch('app.services.protect_event_handler.get_ai_service') as mock_get:
        mock_service = AsyncMock()
        mock_result = MagicMock()
        mock_result.description = "A person walking to the front door"
        mock_result.provider = "openai"
        mock_result.tokens_used = 100
        mock_service.describe_image.return_value = mock_result
        mock_get.return_value = mock_service
        yield mock_service


@pytest.fixture
def mock_websocket_manager():
    """Mock the WebSocket manager."""
    with patch('app.services.protect_event_handler.get_websocket_manager') as mock_get:
        mock_manager = AsyncMock()
        mock_get.return_value = mock_manager
        yield mock_manager


# =============================================================================
# Test: Constants
# =============================================================================

class TestConstants:
    """Tests for module-level constants."""

    def test_event_cooldown_seconds(self):
        """Test default cooldown is 60 seconds."""
        assert EVENT_COOLDOWN_SECONDS == 60

    def test_event_type_mapping(self):
        """Test event type mapping covers all types."""
        expected = {
            "motion": "motion",
            "smart_detect_person": "person",
            "smart_detect_vehicle": "vehicle",
            "smart_detect_package": "package",
            "smart_detect_animal": "animal",
            "ring": "ring",
        }
        assert EVENT_TYPE_MAPPING == expected

    def test_valid_event_types(self):
        """Test valid event types set matches mapping keys."""
        assert VALID_EVENT_TYPES == set(EVENT_TYPE_MAPPING.keys())

    def test_protect_motion_event_constant(self):
        """Test WebSocket event type constant."""
        assert PROTECT_MOTION_EVENT == "PROTECT_MOTION_EVENT"

    def test_doorbell_ring_prompt(self):
        """Test doorbell prompt contains expected keywords."""
        assert "front door" in DOORBELL_RING_PROMPT.lower()
        assert "delivery" in DOORBELL_RING_PROMPT.lower()


# =============================================================================
# Test: Initialization
# =============================================================================

class TestProtectEventHandlerInit:
    """Tests for ProtectEventHandler initialization."""

    def test_init_empty_tracking(self, event_handler):
        """Test handler initializes with empty event tracking."""
        assert len(event_handler._last_event_times) == 0

    def test_init_no_audio_transcription(self, event_handler):
        """Test handler initializes without audio transcription."""
        assert event_handler._last_audio_transcription is None

    def test_get_protect_event_handler_singleton(self):
        """Test get_protect_event_handler returns singleton."""
        handler1 = get_protect_event_handler()
        handler2 = get_protect_event_handler()
        assert handler1 is handler2


# =============================================================================
# Test: Event Type Parsing
# =============================================================================

class TestEventTypeParsing:
    """Tests for _parse_event_types method."""

    def test_parse_motion_only(self, event_handler, mock_ws_message):
        """Test parsing motion-only detection."""
        msg = mock_ws_message(is_motion=True)
        event_types = event_handler._parse_event_types(msg.new_obj, "Camera")
        assert "motion" in event_types

    def test_parse_smart_detect_person(self, event_handler, mock_ws_message):
        """Test parsing person smart detection."""
        msg = mock_ws_message(is_person=True)
        event_types = event_handler._parse_event_types(msg.new_obj, "Camera")
        assert "smart_detect_person" in event_types

    def test_parse_smart_detect_vehicle(self, event_handler, mock_ws_message):
        """Test parsing vehicle smart detection."""
        msg = mock_ws_message(is_vehicle=True)
        event_types = event_handler._parse_event_types(msg.new_obj, "Camera")
        assert "smart_detect_vehicle" in event_types

    def test_parse_smart_detect_package(self, event_handler, mock_ws_message):
        """Test parsing package smart detection."""
        msg = mock_ws_message(is_package=True)
        event_types = event_handler._parse_event_types(msg.new_obj, "Camera")
        assert "smart_detect_package" in event_types

    def test_parse_smart_detect_animal(self, event_handler, mock_ws_message):
        """Test parsing animal smart detection."""
        msg = mock_ws_message(is_animal=True)
        event_types = event_handler._parse_event_types(msg.new_obj, "Camera")
        assert "smart_detect_animal" in event_types

    def test_parse_doorbell_ring(self, event_handler, mock_ws_message):
        """Test parsing doorbell ring event."""
        recent_ring = datetime.now(timezone.utc) - timedelta(seconds=1)
        msg = mock_ws_message(
            model_type="Doorbell",
            is_ring=True,
            last_ring=recent_ring
        )
        event_types = event_handler._parse_event_types(msg.new_obj, "Doorbell")
        assert "ring" in event_types

    def test_parse_multiple_detections(self, event_handler, mock_ws_message):
        """Test parsing multiple simultaneous detections."""
        msg = mock_ws_message(is_motion=True, is_person=True, is_vehicle=True)
        event_types = event_handler._parse_event_types(msg.new_obj, "Camera")
        assert "motion" in event_types
        assert "smart_detect_person" in event_types
        assert "smart_detect_vehicle" in event_types

    def test_parse_no_detection(self, event_handler, mock_ws_message):
        """Test parsing message with no detections returns empty list."""
        msg = mock_ws_message()  # All flags False
        event_types = event_handler._parse_event_types(msg.new_obj, "Camera")
        assert event_types == []

    @pytest.mark.parametrize("detection_flag,expected_type", [
        ("is_motion", "motion"),
        ("is_person", "smart_detect_person"),
        ("is_vehicle", "smart_detect_vehicle"),
        ("is_package", "smart_detect_package"),
        ("is_animal", "smart_detect_animal"),
    ])
    def test_parse_each_detection_type(self, event_handler, mock_ws_message, detection_flag, expected_type):
        """Parametrized test for each detection type."""
        # Create message with specific flag set
        kwargs = {detection_flag: True}
        msg = mock_ws_message(**kwargs)
        event_types = event_handler._parse_event_types(msg.new_obj, "Camera")
        assert expected_type in event_types


# =============================================================================
# Test: Event Filtering
# =============================================================================

class TestEventFiltering:
    """Tests for _should_process_event method."""

    def test_should_process_enabled_type(self, event_handler):
        """Test enabled event type passes filter."""
        smart_detection_types = ["person", "vehicle"]
        result = event_handler._should_process_event("person", smart_detection_types, "Test Camera")
        assert result is True

    def test_should_not_process_disabled_type(self, event_handler):
        """Test disabled event type is filtered out."""
        smart_detection_types = ["person", "vehicle"]
        result = event_handler._should_process_event("package", smart_detection_types, "Test Camera")
        assert result is False

    def test_should_process_motion_when_enabled(self, event_handler):
        """Test motion passes when in filter list."""
        smart_detection_types = ["motion", "person"]
        result = event_handler._should_process_event("motion", smart_detection_types, "Test Camera")
        assert result is True

    def test_should_not_process_motion_when_disabled(self, event_handler):
        """Test motion filtered when not in list."""
        smart_detection_types = ["person", "vehicle"]
        result = event_handler._should_process_event("motion", smart_detection_types, "Test Camera")
        assert result is False

    def test_empty_filter_list_is_all_motion_mode(self, event_handler):
        """Test empty filter list means 'all motion' mode - passes all events."""
        # Per AC8: Empty array means "all motion" mode - process everything
        smart_detection_types = []
        result = event_handler._should_process_event("person", smart_detection_types, "Test Camera")
        assert result is True

    def test_should_process_ring_event(self, event_handler):
        """Test ring event passes when enabled."""
        smart_detection_types = ["person", "ring"]
        result = event_handler._should_process_event("ring", smart_detection_types, "Test Camera")
        assert result is True

    @pytest.mark.parametrize("event_type,filter_types,expected", [
        ("person", ["person", "vehicle"], True),
        ("vehicle", ["person", "vehicle"], True),
        ("package", ["person", "vehicle"], False),
        ("animal", ["animal"], True),
        ("ring", ["ring"], True),
        ("motion", [], True),  # Empty = all motion mode (AC8)
        ("person", ["motion"], True),  # ["motion"] = all motion mode (AC8)
        ("package", ["person", "ring"], False),  # Package not in list
    ])
    def test_filter_scenarios(self, event_handler, event_type, filter_types, expected):
        """Parametrized test for various filter scenarios."""
        result = event_handler._should_process_event(event_type, filter_types, "Test Camera")
        assert result == expected


# =============================================================================
# Test: Event Deduplication
# =============================================================================

class TestEventDeduplication:
    """Tests for _is_duplicate_event method."""

    def test_first_event_not_duplicate(self, event_handler):
        """Test first event from camera is not duplicate."""
        result = event_handler._is_duplicate_event("cam-123", "Front Door")
        assert result is False

    def test_event_within_cooldown_is_duplicate(self, event_handler):
        """Test event within cooldown window is duplicate."""
        # Record first event
        event_handler._last_event_times["cam-123"] = datetime.now(timezone.utc)

        # Check immediately - should be duplicate
        result = event_handler._is_duplicate_event("cam-123", "Front Door")
        assert result is True

    def test_event_after_cooldown_not_duplicate(self, event_handler):
        """Test event after cooldown window is not duplicate."""
        # Record event in the past (beyond cooldown)
        old_time = datetime.now(timezone.utc) - timedelta(seconds=EVENT_COOLDOWN_SECONDS + 10)
        event_handler._last_event_times["cam-123"] = old_time

        result = event_handler._is_duplicate_event("cam-123", "Front Door")
        assert result is False

    def test_different_camera_not_affected(self, event_handler):
        """Test different camera is not affected by another's cooldown."""
        # Record event for camera 1
        event_handler._last_event_times["cam-123"] = datetime.now(timezone.utc)

        # Camera 2 should not be blocked
        result = event_handler._is_duplicate_event("cam-456", "Back Door")
        assert result is False

    def test_clear_event_tracking_specific_camera(self, event_handler):
        """Test clearing tracking for specific camera."""
        event_handler._last_event_times["cam-123"] = datetime.now(timezone.utc)
        event_handler._last_event_times["cam-456"] = datetime.now(timezone.utc)

        event_handler.clear_event_tracking("cam-123")

        assert "cam-123" not in event_handler._last_event_times
        assert "cam-456" in event_handler._last_event_times

    def test_clear_event_tracking_all(self, event_handler):
        """Test clearing all tracking."""
        event_handler._last_event_times["cam-123"] = datetime.now(timezone.utc)
        event_handler._last_event_times["cam-456"] = datetime.now(timezone.utc)

        event_handler.clear_event_tracking()

        assert len(event_handler._last_event_times) == 0


# =============================================================================
# Test: Camera Lookup
# =============================================================================

class TestCameraLookup:
    """Tests for _get_camera_by_protect_id method."""

    def test_get_camera_found(self, event_handler, mock_db_session, mock_camera):
        """Test camera lookup returns camera when found."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_camera

        result = event_handler._get_camera_by_protect_id(mock_db_session, "protect-cam-456")

        assert result == mock_camera

    def test_get_camera_not_found(self, event_handler, mock_db_session):
        """Test camera lookup returns None when not found."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        result = event_handler._get_camera_by_protect_id(mock_db_session, "unknown-camera")

        assert result is None

    def test_get_camera_filters_by_protect_id(self, event_handler, mock_db_session, mock_camera):
        """Test lookup filters by protect_camera_id."""
        mock_query = mock_db_session.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_filter.first.return_value = mock_camera

        event_handler._get_camera_by_protect_id(mock_db_session, "protect-cam-456")

        # Verify filter was called
        mock_query.filter.assert_called_once()


# =============================================================================
# Test: Smart Detection Types Loading
# =============================================================================

class TestSmartDetectionTypesLoading:
    """Tests for _load_smart_detection_types method."""

    def test_load_from_json_string(self, event_handler, mock_camera):
        """Test loading types from JSON string field."""
        mock_camera.smart_detection_types = '["person", "vehicle", "package"]'

        result = event_handler._load_smart_detection_types(mock_camera)

        assert result == ["person", "vehicle", "package"]

    def test_load_array_format(self, event_handler, mock_camera):
        """Test loading array-style JSON string."""
        mock_camera.smart_detection_types = '["person","vehicle","package","animal"]'

        result = event_handler._load_smart_detection_types(mock_camera)

        assert result == ["person", "vehicle", "package", "animal"]

    def test_load_null_returns_empty(self, event_handler, mock_camera):
        """Test null field returns empty list."""
        mock_camera.smart_detection_types = None

        result = event_handler._load_smart_detection_types(mock_camera)

        assert result == []

    def test_load_empty_string_returns_empty(self, event_handler, mock_camera):
        """Test empty string returns empty list."""
        mock_camera.smart_detection_types = ""

        result = event_handler._load_smart_detection_types(mock_camera)

        assert result == []

    def test_load_invalid_json_returns_empty(self, event_handler, mock_camera):
        """Test invalid JSON returns empty list."""
        mock_camera.smart_detection_types = "not valid json"

        result = event_handler._load_smart_detection_types(mock_camera)

        assert result == []


# =============================================================================
# Test: Handle Event Main Flow
# =============================================================================

class TestHandleEventFlow:
    """Tests for handle_event main method."""

    @pytest.mark.asyncio
    async def test_handle_event_no_new_obj(self, event_handler):
        """Test handle_event returns False when message has no new_obj."""
        mock_msg = MagicMock()
        mock_msg.new_obj = None

        result = await event_handler.handle_event("controller-123", mock_msg)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_event_non_camera_object(self, event_handler, mock_ws_message):
        """Test handle_event returns False for non-camera objects."""
        msg = mock_ws_message()
        type(msg.new_obj).__name__ = "Light"  # Not Camera or Doorbell

        result = await event_handler.handle_event("controller-123", msg)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_event_disabled_camera(
        self, event_handler, mock_db_session, mock_camera, mock_ws_message
    ):
        """Test handle_event returns False for disabled camera."""
        mock_camera.is_enabled = False
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_camera

        msg = mock_ws_message(is_motion=True)
        result = await event_handler.handle_event("controller-123", msg)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_event_unregistered_camera(
        self, event_handler, mock_db_session, mock_ws_message
    ):
        """Test handle_event returns False for unregistered camera."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        msg = mock_ws_message(is_motion=True)
        result = await event_handler.handle_event("controller-123", msg)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_event_non_protect_source(
        self, event_handler, mock_db_session, mock_camera, mock_ws_message
    ):
        """Test handle_event returns False for non-protect source type."""
        mock_camera.source_type = "rtsp"  # Not protect
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_camera

        msg = mock_ws_message(is_motion=True)
        result = await event_handler.handle_event("controller-123", msg)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_event_filtered_event_type(
        self, event_handler, mock_db_session, mock_camera, mock_ws_message
    ):
        """Test handle_event returns False when event type is filtered."""
        mock_camera.smart_detection_types = '["person"]'  # Only person enabled
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_camera

        msg = mock_ws_message(is_vehicle=True)  # Vehicle not in filter
        result = await event_handler.handle_event("controller-123", msg)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_event_duplicate_filtered(
        self, event_handler, mock_db_session, mock_camera, mock_ws_message
    ):
        """Test handle_event returns False for duplicate event."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_camera

        # First event should process (but we're not mocking full pipeline)
        # Record recent event to trigger duplicate detection
        event_handler._last_event_times[mock_camera.id] = datetime.now(timezone.utc)

        msg = mock_ws_message(is_person=True)
        result = await event_handler.handle_event("controller-123", msg)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_event_no_detection(
        self, event_handler, mock_db_session, mock_camera, mock_ws_message
    ):
        """Test handle_event returns False when no detection in message."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_camera

        msg = mock_ws_message()  # No detection flags set
        result = await event_handler.handle_event("controller-123", msg)

        assert result is False


# =============================================================================
# Test: Protect Event ID Extraction
# =============================================================================

class TestProtectEventIdExtraction:
    """Tests for _extract_protect_event_id method."""

    def test_extract_from_last_motion(self, event_handler):
        """Test extraction from last_motion object."""
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()

        # Create mock last_motion with id attribute
        mock_last_motion = MagicMock()
        mock_last_motion.id = "motion-event-123"
        mock_msg.new_obj.last_motion = mock_last_motion
        mock_msg.new_obj.last_smart_detect = None

        result = event_handler._extract_protect_event_id(mock_msg)

        assert result == "motion-event-123"

    def test_extract_from_last_smart_detect(self, event_handler):
        """Test extraction from last_smart_detect object."""
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()

        # No last_motion, but has last_smart_detect
        mock_msg.new_obj.last_motion = None
        mock_last_smart = MagicMock()
        mock_last_smart.id = "smart-event-456"
        mock_msg.new_obj.last_smart_detect = mock_last_smart

        result = event_handler._extract_protect_event_id(mock_msg)

        assert result == "smart-event-456"

    def test_extract_prefers_motion_over_smart(self, event_handler):
        """Test extraction prefers last_motion over last_smart_detect."""
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()

        mock_last_motion = MagicMock()
        mock_last_motion.id = "motion-event-123"
        mock_msg.new_obj.last_motion = mock_last_motion

        mock_last_smart = MagicMock()
        mock_last_smart.id = "smart-event-456"
        mock_msg.new_obj.last_smart_detect = mock_last_smart

        result = event_handler._extract_protect_event_id(mock_msg)

        # Should prefer motion
        assert result == "motion-event-123"

    def test_extract_returns_none_when_no_events(self, event_handler):
        """Test extraction returns None when no event objects present."""
        mock_msg = MagicMock()
        mock_msg.new_obj = MagicMock()
        mock_msg.new_obj.last_motion = None
        mock_msg.new_obj.last_smart_detect = None

        result = event_handler._extract_protect_event_id(mock_msg)

        assert result is None

    def test_extract_returns_none_when_no_new_obj(self, event_handler):
        """Test extraction returns None when message has no new_obj."""
        mock_msg = MagicMock()
        mock_msg.new_obj = None

        result = event_handler._extract_protect_event_id(mock_msg)

        assert result is None


# =============================================================================
# Test: Timestamp Formatting
# =============================================================================

class TestTimestampFormatting:
    """Tests for _format_timestamp_for_ai helper function."""

    def test_format_utc_timestamp(self, mock_db_session):
        """Test formatting UTC timestamp without timezone setting."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        result = _format_timestamp_for_ai(timestamp, mock_db_session)

        assert "2025-01-15" in result
        assert "14:30" in result

    def test_format_with_timezone_setting(self, mock_db_session):
        """Test formatting with configured timezone."""
        mock_setting = MagicMock()
        mock_setting.value = "America/New_York"
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_setting

        timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        result = _format_timestamp_for_ai(timestamp, mock_db_session)

        assert "2025-01-15" in result

    def test_format_naive_timestamp(self, mock_db_session):
        """Test formatting naive timestamp assumes UTC."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        timestamp = datetime(2025, 1, 15, 14, 30, 0)  # No timezone
        result = _format_timestamp_for_ai(timestamp, mock_db_session)

        assert "2025-01-15" in result


# =============================================================================
# Test: OCR Extraction
# =============================================================================

class TestOCRExtraction:
    """Tests for _try_ocr_extraction method."""

    def test_ocr_disabled_returns_none(self, event_handler, mock_db_session):
        """Test OCR returns None when disabled in settings."""
        mock_setting = MagicMock()
        mock_setting.value = "false"
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_setting

        import numpy as np
        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)

        result = event_handler._try_ocr_extraction(fake_frame, mock_db_session)

        assert result is None

    def test_ocr_enabled_but_unavailable(self, event_handler, mock_db_session):
        """Test OCR returns None when tesseract not available."""
        mock_setting = MagicMock()
        mock_setting.value = "true"
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_setting

        with patch('app.services.ocr_service.is_ocr_available', return_value=False):
            import numpy as np
            fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)

            result = event_handler._try_ocr_extraction(fake_frame, mock_db_session)

        assert result is None


# =============================================================================
# Test: HomeKit Doorbell Trigger
# =============================================================================

class TestHomekitDoorbellTrigger:
    """Tests for _trigger_homekit_doorbell method."""

    def test_trigger_homekit_doorbell_success(self, event_handler):
        """Test HomeKit doorbell trigger succeeds when running."""
        with patch('app.services.homekit_service.get_homekit_service') as mock_get:
            mock_service = MagicMock()
            mock_service.is_running = True
            mock_service.trigger_doorbell.return_value = True
            mock_get.return_value = mock_service

            result = event_handler._trigger_homekit_doorbell("cam-123", "event-456")

            assert result is True
            mock_service.trigger_doorbell.assert_called_once_with("cam-123", "event-456")

    def test_trigger_homekit_doorbell_not_running(self, event_handler):
        """Test HomeKit trigger returns False when not running."""
        with patch('app.services.homekit_service.get_homekit_service') as mock_get:
            mock_service = MagicMock()
            mock_service.is_running = False
            mock_get.return_value = mock_service

            result = event_handler._trigger_homekit_doorbell("cam-123", "event-456")

            assert result is False

    def test_trigger_homekit_doorbell_error_handled(self, event_handler):
        """Test HomeKit errors are caught and return False."""
        with patch('app.services.homekit_service.get_homekit_service') as mock_get:
            mock_get.side_effect = Exception("HomeKit error")

            result = event_handler._trigger_homekit_doorbell("cam-123", "event-456")

            assert result is False
