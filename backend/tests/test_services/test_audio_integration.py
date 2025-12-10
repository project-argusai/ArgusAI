"""Unit tests for Story P3-5.3: Include Audio Context in AI Descriptions

Tests audio transcription integration with AI prompts, event pipeline,
and database storage for doorbell cameras.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime, timezone
from pathlib import Path
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.event import Event
from app.models.camera import Camera


@pytest.fixture
def test_db():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def doorbell_camera(test_db):
    """Create a doorbell camera for testing"""
    camera = Camera(
        id="test-doorbell-camera-id",
        name="Front Door Doorbell",
        type="rtsp",  # Required by ORM constraint
        source_type="protect",
        is_doorbell=True,
        is_enabled=True,
        protect_camera_id="protect-doorbell-id",
        frame_rate=5
    )
    test_db.add(camera)
    test_db.commit()
    return camera


@pytest.fixture
def regular_camera(test_db):
    """Create a non-doorbell camera for testing"""
    camera = Camera(
        id="test-regular-camera-id",
        name="Front Yard Camera",
        type="rtsp",  # Required by ORM constraint
        source_type="protect",
        is_doorbell=False,
        is_enabled=True,
        protect_camera_id="protect-camera-id",
        frame_rate=5
    )
    test_db.add(camera)
    test_db.commit()
    return camera


class TestAIPromptWithAudio:
    """Test AI prompts with audio transcription (AC1, AC2, AC3)"""

    def test_prompt_includes_transcription_when_provided(self):
        """AC1: Prompt includes transcription when available"""
        from app.services.ai_service import OpenAIProvider

        provider = OpenAIProvider("test-api-key")
        transcription = "Amazon delivery"

        prompt = provider._build_user_prompt(
            camera_name="Front Door",
            timestamp="2025-12-08T10:00:00Z",
            detected_objects=["person"],
            custom_prompt=None,
            audio_transcription=transcription
        )

        assert 'Audio transcription: "Amazon delivery"' in prompt

    def test_prompt_includes_transcription_in_multi_image(self):
        """AC1: Multi-image prompt includes transcription"""
        from app.services.ai_service import OpenAIProvider

        provider = OpenAIProvider("test-api-key")
        transcription = "Hello, this is your UPS delivery"

        prompt = provider._build_multi_image_prompt(
            camera_name="Front Door",
            timestamp="2025-12-08T10:00:00Z",
            detected_objects=["person"],
            num_images=5,
            custom_prompt=None,
            audio_transcription=transcription
        )

        assert 'Audio transcription: "Hello, this is your UPS delivery"' in prompt

    def test_prompt_omits_audio_when_none(self):
        """AC3: No audio section when transcription is None"""
        from app.services.ai_service import OpenAIProvider

        provider = OpenAIProvider("test-api-key")

        prompt = provider._build_user_prompt(
            camera_name="Front Door",
            timestamp="2025-12-08T10:00:00Z",
            detected_objects=["person"],
            custom_prompt=None,
            audio_transcription=None
        )

        assert "Audio transcription" not in prompt

    def test_prompt_omits_audio_when_empty(self):
        """AC3: No audio section when transcription is empty string"""
        from app.services.ai_service import OpenAIProvider

        provider = OpenAIProvider("test-api-key")

        prompt = provider._build_user_prompt(
            camera_name="Front Door",
            timestamp="2025-12-08T10:00:00Z",
            detected_objects=["person"],
            custom_prompt=None,
            audio_transcription=""
        )

        assert "Audio transcription" not in prompt

    def test_prompt_omits_audio_when_whitespace(self):
        """AC3: No audio section when transcription is only whitespace"""
        from app.services.ai_service import OpenAIProvider

        provider = OpenAIProvider("test-api-key")

        prompt = provider._build_user_prompt(
            camera_name="Front Door",
            timestamp="2025-12-08T10:00:00Z",
            detected_objects=["person"],
            custom_prompt=None,
            audio_transcription="   "
        )

        assert "Audio transcription" not in prompt

    def test_transcription_is_quoted_in_prompt(self):
        """AC2: Transcription is properly quoted in prompt"""
        from app.services.ai_service import OpenAIProvider

        provider = OpenAIProvider("test-api-key")

        prompt = provider._build_user_prompt(
            camera_name="Front Door",
            timestamp="2025-12-08T10:00:00Z",
            detected_objects=["person"],
            custom_prompt=None,
            audio_transcription="FedEx delivery"
        )

        # Should be quoted
        assert '"FedEx delivery"' in prompt


class TestDoorbellAudioExtraction:
    """Test audio extraction for doorbell vs non-doorbell cameras (AC4, AC5)"""

    @pytest.mark.asyncio
    async def test_doorbell_camera_triggers_audio_extraction(self, doorbell_camera):
        """AC4: Doorbell camera triggers audio extraction"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()
        clip_path = Path("/tmp/test_clip.mp4")

        # Patch at the source module where get_audio_extractor is imported from
        with patch("app.services.audio_extractor.get_audio_extractor") as mock_get_extractor:
            mock_extractor = MagicMock()
            mock_extractor.extract_audio = AsyncMock(return_value=b"fake_audio_bytes")
            mock_extractor.transcribe = AsyncMock(return_value="Hello")
            mock_get_extractor.return_value = mock_extractor

            result = await handler._extract_and_transcribe_audio(clip_path, doorbell_camera)

            # Audio extraction should be called
            mock_extractor.extract_audio.assert_called_once_with(clip_path)
            mock_extractor.transcribe.assert_called_once()
            assert result == "Hello"

    @pytest.mark.asyncio
    async def test_audio_extraction_returns_none_on_no_audio(self, doorbell_camera):
        """AC4: Returns None when no audio track in clip"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()
        clip_path = Path("/tmp/test_clip.mp4")

        with patch("app.services.audio_extractor.get_audio_extractor") as mock_get_extractor:
            mock_extractor = MagicMock()
            mock_extractor.extract_audio = AsyncMock(return_value=None)  # No audio
            mock_get_extractor.return_value = mock_extractor

            result = await handler._extract_and_transcribe_audio(clip_path, doorbell_camera)

            assert result is None
            mock_extractor.extract_audio.assert_called_once()
            # Transcribe should NOT be called if no audio
            mock_extractor.transcribe.assert_not_called()

    @pytest.mark.asyncio
    async def test_audio_extraction_returns_none_on_silent_audio(self, doorbell_camera):
        """AC4: Returns None for silent audio (empty transcription)"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()
        clip_path = Path("/tmp/test_clip.mp4")

        with patch("app.services.audio_extractor.get_audio_extractor") as mock_get_extractor:
            mock_extractor = MagicMock()
            mock_extractor.extract_audio = AsyncMock(return_value=b"fake_audio_bytes")
            mock_extractor.transcribe = AsyncMock(return_value="")  # Silent/empty
            mock_get_extractor.return_value = mock_extractor

            result = await handler._extract_and_transcribe_audio(clip_path, doorbell_camera)

            assert result is None  # Empty transcription returns None

    @pytest.mark.asyncio
    async def test_audio_extraction_continues_on_error(self, doorbell_camera):
        """Audio failures should NOT block event processing"""
        from app.services.protect_event_handler import ProtectEventHandler

        handler = ProtectEventHandler()
        clip_path = Path("/tmp/test_clip.mp4")

        with patch("app.services.audio_extractor.get_audio_extractor") as mock_get_extractor:
            mock_extractor = MagicMock()
            mock_extractor.extract_audio = AsyncMock(side_effect=Exception("Audio extraction failed"))
            mock_get_extractor.return_value = mock_extractor

            # Should NOT raise exception - returns None instead
            result = await handler._extract_and_transcribe_audio(clip_path, doorbell_camera)

            assert result is None


class TestEventStorageWithTranscription:
    """Test event storage with audio_transcription field (AC6)"""

    def test_event_model_has_audio_transcription_field(self):
        """AC6: Event model has audio_transcription field"""
        event = Event(
            camera_id="test-camera-id",
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=80,
            objects_detected='["person"]',
            audio_transcription="Hello there"
        )

        assert event.audio_transcription == "Hello there"

    def test_event_stores_audio_transcription_in_db(self, test_db, doorbell_camera):
        """AC6: Audio transcription is persisted in database"""
        event = Event(
            camera_id=doorbell_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person at door announcing delivery",
            confidence=85,
            objects_detected='["person"]',
            source_type="protect",
            is_doorbell_ring=True,
            audio_transcription="Amazon delivery"
        )

        test_db.add(event)
        test_db.commit()

        # Retrieve and verify
        stored_event = test_db.query(Event).filter(Event.id == event.id).first()
        assert stored_event is not None
        assert stored_event.audio_transcription == "Amazon delivery"

    def test_event_stores_null_when_no_transcription(self, test_db, doorbell_camera):
        """AC6: Event stores NULL when no transcription"""
        event = Event(
            camera_id=doorbell_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Person at door",
            confidence=85,
            objects_detected='["person"]',
            source_type="protect",
            audio_transcription=None
        )

        test_db.add(event)
        test_db.commit()

        stored_event = test_db.query(Event).filter(Event.id == event.id).first()
        assert stored_event.audio_transcription is None


class TestEventSchemaWithTranscription:
    """Test event schemas include audio_transcription"""

    def test_event_response_schema_has_audio_transcription(self):
        """EventResponse schema includes audio_transcription field"""
        from app.schemas.event import EventResponse

        # Check field is defined in schema
        assert "audio_transcription" in EventResponse.model_fields

    def test_event_create_schema_has_audio_transcription(self):
        """EventCreate schema includes audio_transcription field"""
        from app.schemas.event import EventCreate

        assert "audio_transcription" in EventCreate.model_fields

    def test_event_response_from_orm_includes_transcription(self, test_db, doorbell_camera):
        """EventResponse correctly reads audio_transcription from ORM"""
        from app.schemas.event import EventResponse

        event = Event(
            camera_id=doorbell_camera.id,
            timestamp=datetime.now(timezone.utc),
            description="Test event",
            confidence=80,
            objects_detected='["person"]',
            alert_triggered=False,
            created_at=datetime.now(timezone.utc),
            audio_transcription="Package delivery"
        )

        test_db.add(event)
        test_db.commit()
        test_db.refresh(event)

        # Convert to response schema
        response = EventResponse.model_validate(event)
        assert response.audio_transcription == "Package delivery"


class TestAllProvidersAcceptAudioTranscription:
    """Test all AI providers accept audio_transcription parameter"""

    def test_openai_provider_accepts_audio_transcription(self):
        """OpenAI provider accepts audio_transcription"""
        from app.services.ai_service import OpenAIProvider
        import inspect

        sig = inspect.signature(OpenAIProvider.generate_description)
        assert "audio_transcription" in sig.parameters

        sig_multi = inspect.signature(OpenAIProvider.generate_multi_image_description)
        assert "audio_transcription" in sig_multi.parameters

    def test_claude_provider_accepts_audio_transcription(self):
        """Claude provider accepts audio_transcription"""
        from app.services.ai_service import ClaudeProvider
        import inspect

        sig = inspect.signature(ClaudeProvider.generate_description)
        assert "audio_transcription" in sig.parameters

        sig_multi = inspect.signature(ClaudeProvider.generate_multi_image_description)
        assert "audio_transcription" in sig_multi.parameters

    def test_gemini_provider_accepts_audio_transcription(self):
        """Gemini provider accepts audio_transcription"""
        from app.services.ai_service import GeminiProvider
        import inspect

        sig = inspect.signature(GeminiProvider.generate_description)
        assert "audio_transcription" in sig.parameters

        sig_multi = inspect.signature(GeminiProvider.generate_multi_image_description)
        assert "audio_transcription" in sig_multi.parameters

    def test_grok_provider_accepts_audio_transcription(self):
        """Grok provider accepts audio_transcription"""
        from app.services.ai_service import GrokProvider
        import inspect

        sig = inspect.signature(GrokProvider.generate_description)
        assert "audio_transcription" in sig.parameters

        sig_multi = inspect.signature(GrokProvider.generate_multi_image_description)
        assert "audio_transcription" in sig_multi.parameters


class TestAIServiceAcceptsAudioTranscription:
    """Test AIService public methods accept audio_transcription"""

    def test_generate_description_accepts_audio_transcription(self):
        """AIService.generate_description accepts audio_transcription"""
        from app.services.ai_service import AIService
        import inspect

        sig = inspect.signature(AIService.generate_description)
        assert "audio_transcription" in sig.parameters

    def test_describe_images_accepts_audio_transcription(self):
        """AIService.describe_images accepts audio_transcription"""
        from app.services.ai_service import AIService
        import inspect

        sig = inspect.signature(AIService.describe_images)
        assert "audio_transcription" in sig.parameters
