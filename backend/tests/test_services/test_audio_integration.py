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
    """Test AI prompts with audio transcription (AC1, AC2, AC3).

    Refactor note (commit 1af9f8a): prompt assembly moved out of the per-provider
    ``_build_user_prompt`` / ``_build_multi_image_prompt`` methods into the shared
    ``AIPromptService.select_and_build_prompt``. The audio context line is now
    rendered as ``Audio detected: "<text>"`` (previously ``Audio transcription:``).
    """

    def _build_prompt(self, audio_transcription, analysis_mode="single_image"):
        from app.services.ai_prompt_service import AIPromptService

        service = AIPromptService()
        prompt, _ = service.select_and_build_prompt(
            camera_id=None,
            custom_prompt=None,
            detected_objects=["person"],
            timestamp="2025-12-08T10:00:00Z",
            audio_transcription=audio_transcription,
            analysis_mode=analysis_mode,
        )
        return prompt

    def test_prompt_includes_transcription_when_provided(self):
        """AC1: Prompt includes transcription when available"""
        prompt = self._build_prompt("Amazon delivery")
        assert 'Audio detected: "Amazon delivery"' in prompt

    def test_prompt_includes_transcription_in_multi_image(self):
        """AC1: Multi-image prompt includes transcription"""
        prompt = self._build_prompt(
            "Hello, this is your UPS delivery", analysis_mode="multi_image"
        )
        assert 'Audio detected: "Hello, this is your UPS delivery"' in prompt

    def test_prompt_omits_audio_when_none(self):
        """AC3: No audio section when transcription is None"""
        prompt = self._build_prompt(None)
        assert "Audio detected" not in prompt

    def test_prompt_omits_audio_when_empty(self):
        """AC3: No audio section when transcription is empty string"""
        prompt = self._build_prompt("")
        assert "Audio detected" not in prompt

    def test_prompt_omits_audio_when_whitespace(self):
        """AC3: No audio section when transcription is only whitespace"""
        prompt = self._build_prompt("   ")
        assert "Audio detected" not in prompt

    def test_transcription_is_quoted_in_prompt(self):
        """AC2: Transcription is properly quoted in prompt"""
        prompt = self._build_prompt("FedEx delivery")
        # Should be quoted
        assert '"FedEx delivery"' in prompt


# NOTE: TestDoorbellAudioExtraction was removed (commit 1af9f8a refactor).
# The clip-based audio path it exercised --
# ``ProtectEventHandler._extract_and_transcribe_audio`` calling
# ``AudioExtractor.extract_audio`` + ``.transcribe`` -- was deleted during the
# ai_service / protect_event_handler decomposition. No production code calls that
# method or that AudioExtractor path any longer (audio is now handled via the
# real-time audio_stream_service / audio_event_handler), so there is no equivalent
# symbol to repoint these tests to. The ``audio_transcription`` value still flows
# through providers and prompts, which the remaining tests in this module cover.


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
        from app.services.ai_providers import OpenAIProvider
        import inspect

        sig = inspect.signature(OpenAIProvider.generate_description)
        assert "audio_transcription" in sig.parameters

        sig_multi = inspect.signature(OpenAIProvider.generate_multi_image_description)
        assert "audio_transcription" in sig_multi.parameters

    def test_claude_provider_accepts_audio_transcription(self):
        """Claude provider accepts audio_transcription"""
        from app.services.ai_providers import ClaudeProvider
        import inspect

        sig = inspect.signature(ClaudeProvider.generate_description)
        assert "audio_transcription" in sig.parameters

        sig_multi = inspect.signature(ClaudeProvider.generate_multi_image_description)
        assert "audio_transcription" in sig_multi.parameters

    def test_gemini_provider_accepts_audio_transcription(self):
        """Gemini provider accepts audio_transcription"""
        from app.services.ai_providers import GeminiProvider
        import inspect

        sig = inspect.signature(GeminiProvider.generate_description)
        assert "audio_transcription" in sig.parameters

        sig_multi = inspect.signature(GeminiProvider.generate_multi_image_description)
        assert "audio_transcription" in sig_multi.parameters

    def test_grok_provider_accepts_audio_transcription(self):
        """Grok provider accepts audio_transcription"""
        from app.services.ai_providers import GrokProvider
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
