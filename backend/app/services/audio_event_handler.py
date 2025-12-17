"""Audio Event Handler Service (Story P6-3.2)

This service handles audio event detection for camera streams:
1. Monitors audio buffers from AudioStreamService
2. Runs audio classification when buffers are ready
3. Creates events with audio_event_type when detection passes threshold

Architecture:
- Called from event pipeline when processing camera events (integration point)
- Can also be triggered independently for periodic audio checks
- Thread-safe for concurrent camera processing
- Graceful degradation if audio service unavailable
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional
import json
import uuid

from sqlalchemy.orm import Session

from app.models.event import Event
from app.models.camera import Camera
from app.services.audio_event_detector import (
    AudioEventDetector,
    AudioDetectionResult,
    get_audio_event_detector,
)
from app.services.audio_stream_service import (
    AudioStreamExtractor,
    AudioChunk,
    get_audio_stream_extractor,
)
from app.services.audio_classifiers import AudioEventType

logger = logging.getLogger(__name__)


@dataclass
class AudioEventCreationResult:
    """
    Result from audio event creation attempt.

    Attributes:
        event_id: Created event UUID (None if no event created)
        audio_event_type: Type of detected audio event
        confidence: Detection confidence score
        created: Whether an event was actually created
        reason: Explanation for result (e.g., "below_threshold", "created", "no_audio")
    """
    event_id: Optional[str]
    audio_event_type: Optional[AudioEventType]
    confidence: Optional[float]
    created: bool
    reason: str


class AudioEventHandler:
    """
    Handles audio event detection and event creation (Story P6-3.2 AC#1, AC#4)

    Integrates AudioStreamService (audio buffers) with AudioEventDetector
    (classification) to create events when audio events are detected.

    Usage:
        handler = get_audio_event_handler()

        # Option 1: Process audio for specific camera
        result = await handler.process_camera_audio(db, camera_id)

        # Option 2: Attach audio info to existing event during event processing
        await handler.enrich_event_with_audio(db, event, camera_id)
    """

    def __init__(
        self,
        audio_extractor: Optional[AudioStreamExtractor] = None,
        audio_detector: Optional[AudioEventDetector] = None,
    ):
        """
        Initialize AudioEventHandler.

        Args:
            audio_extractor: Audio stream extractor (default: singleton)
            audio_detector: Audio event detector (default: singleton)
        """
        self._audio_extractor = audio_extractor
        self._audio_detector = audio_detector

        logger.info(
            "AudioEventHandler initialized",
            extra={"event_type": "audio_event_handler_init"}
        )

    @property
    def audio_extractor(self) -> AudioStreamExtractor:
        """Lazy-load audio extractor singleton."""
        if self._audio_extractor is None:
            self._audio_extractor = get_audio_stream_extractor()
        return self._audio_extractor

    @property
    def audio_detector(self) -> AudioEventDetector:
        """Lazy-load audio detector singleton."""
        if self._audio_detector is None:
            self._audio_detector = get_audio_event_detector()
        return self._audio_detector

    def _is_audio_enabled(self, db: Session, camera_id: str) -> bool:
        """
        Check if audio is enabled for a camera.

        Args:
            db: Database session
            camera_id: Camera UUID

        Returns:
            True if camera has audio_enabled=True
        """
        camera = db.query(Camera).filter(Camera.id == camera_id).first()
        if camera is None:
            return False
        return getattr(camera, 'audio_enabled', False)

    async def process_camera_audio(
        self,
        db: Session,
        camera_id: str,
        audio_duration_seconds: float = 2.0,
        create_event: bool = True,
    ) -> AudioEventCreationResult:
        """
        Process audio from a camera and optionally create an event.

        This is the main entry point for standalone audio processing.
        Can be called periodically or on-demand for cameras with audio enabled.

        Args:
            db: Database session
            camera_id: Camera UUID
            audio_duration_seconds: Duration of audio to analyze (default 2s)
            create_event: Whether to create Event record for detections

        Returns:
            AudioEventCreationResult with details of what happened
        """
        # Check if audio is enabled for this camera
        if not self._is_audio_enabled(db, camera_id):
            return AudioEventCreationResult(
                event_id=None,
                audio_event_type=None,
                confidence=None,
                created=False,
                reason="audio_disabled"
            )

        # Get audio from buffer
        audio_chunk = self.audio_extractor.get_latest_audio(
            camera_id,
            duration_seconds=audio_duration_seconds
        )

        if audio_chunk is None:
            return AudioEventCreationResult(
                event_id=None,
                audio_event_type=None,
                confidence=None,
                created=False,
                reason="no_audio_buffer"
            )

        # Run audio detection
        detection_results = self.audio_detector.detect_audio_events(
            audio_chunk.samples,
            audio_chunk.sample_rate,
            db=db,
            channels=audio_chunk.channels,
        )

        if not detection_results:
            return AudioEventCreationResult(
                event_id=None,
                audio_event_type=None,
                confidence=None,
                created=False,
                reason="no_detection"
            )

        # Find first detection that passed threshold
        passed_detection = next(
            (d for d in detection_results if d.passed_threshold),
            None
        )

        if passed_detection is None:
            # Have detections but none passed threshold
            best_detection = max(detection_results, key=lambda d: d.confidence)
            return AudioEventCreationResult(
                event_id=None,
                audio_event_type=best_detection.event_type,
                confidence=best_detection.confidence,
                created=False,
                reason=f"below_threshold (threshold={best_detection.threshold_used:.2%})"
            )

        # Create event if requested
        if create_event:
            event_id = await self._create_audio_event(
                db,
                camera_id,
                passed_detection,
                audio_chunk,
            )

            return AudioEventCreationResult(
                event_id=event_id,
                audio_event_type=passed_detection.event_type,
                confidence=passed_detection.confidence,
                created=True,
                reason="created"
            )

        return AudioEventCreationResult(
            event_id=None,
            audio_event_type=passed_detection.event_type,
            confidence=passed_detection.confidence,
            created=False,
            reason="create_event_disabled"
        )

    async def _create_audio_event(
        self,
        db: Session,
        camera_id: str,
        detection: AudioDetectionResult,
        audio_chunk: AudioChunk,
    ) -> str:
        """
        Create an Event record for an audio detection.

        Args:
            db: Database session
            camera_id: Camera UUID
            detection: Audio detection result
            audio_chunk: Source audio chunk

        Returns:
            Created event UUID
        """
        event_id = str(uuid.uuid4())

        # Create event with audio fields populated (Story P6-3.2 AC#4)
        event = Event(
            id=event_id,
            camera_id=camera_id,
            timestamp=datetime.now(timezone.utc),
            description=f"Audio event detected: {detection.event_type.value.replace('_', ' ')}",
            confidence=int(detection.confidence * 100),
            objects_detected=json.dumps(["audio_event"]),
            source_type="rtsp",  # Audio events come from RTSP streams
            audio_event_type=detection.event_type.value,
            audio_confidence=detection.confidence,
            audio_duration_ms=detection.duration_ms,
        )

        db.add(event)
        db.commit()

        logger.info(
            f"Created audio event for camera {camera_id}: {detection.event_type.value}",
            extra={
                "event_type": "audio_event_created",
                "event_id": event_id,
                "camera_id": camera_id,
                "audio_event_type": detection.event_type.value,
                "confidence": detection.confidence,
                "duration_ms": detection.duration_ms,
            }
        )

        return event_id

    async def enrich_event_with_audio(
        self,
        db: Session,
        event: Event,
        camera_id: str,
        audio_duration_seconds: float = 2.0,
    ) -> bool:
        """
        Enrich an existing event with audio detection information.

        This is called from the event pipeline to add audio context
        to motion-triggered events.

        Args:
            db: Database session
            event: Event to enrich
            camera_id: Camera UUID
            audio_duration_seconds: Duration of audio to analyze

        Returns:
            True if audio info was added to event
        """
        # Check if audio is enabled
        if not self._is_audio_enabled(db, camera_id):
            return False

        # Get audio from buffer
        audio_chunk = self.audio_extractor.get_latest_audio(
            camera_id,
            duration_seconds=audio_duration_seconds
        )

        if audio_chunk is None:
            logger.debug(
                f"No audio buffer available for event enrichment (camera {camera_id})"
            )
            return False

        # Run audio detection
        detection_results = self.audio_detector.detect_audio_events(
            audio_chunk.samples,
            audio_chunk.sample_rate,
            db=db,
            channels=audio_chunk.channels,
        )

        if not detection_results:
            return False

        # Find first detection that passed threshold
        passed_detection = next(
            (d for d in detection_results if d.passed_threshold),
            None
        )

        if passed_detection is None:
            return False

        # Update event with audio fields (Story P6-3.2 AC#4)
        event.audio_event_type = passed_detection.event_type.value
        event.audio_confidence = passed_detection.confidence
        event.audio_duration_ms = passed_detection.duration_ms

        # Optionally enhance description
        if passed_detection.event_type != AudioEventType.OTHER:
            audio_desc = passed_detection.event_type.value.replace("_", " ")
            if event.description and not audio_desc in event.description.lower():
                event.description = f"{event.description} [Audio: {audio_desc} detected]"

        db.commit()

        logger.info(
            f"Enriched event {event.id} with audio: {passed_detection.event_type.value}",
            extra={
                "event_type": "event_audio_enriched",
                "event_id": event.id,
                "camera_id": camera_id,
                "audio_event_type": passed_detection.event_type.value,
                "confidence": passed_detection.confidence,
            }
        )

        return True

    async def check_cameras_for_audio_events(
        self,
        db: Session,
        camera_ids: Optional[List[str]] = None,
    ) -> Dict[str, AudioEventCreationResult]:
        """
        Check multiple cameras for audio events.

        Useful for batch processing or periodic checks.

        Args:
            db: Database session
            camera_ids: Optional list of camera IDs (default: all audio-enabled cameras)

        Returns:
            Dict mapping camera_id to AudioEventCreationResult
        """
        results: Dict[str, AudioEventCreationResult] = {}

        if camera_ids is None:
            # Get all audio-enabled cameras
            cameras = db.query(Camera).filter(
                Camera.audio_enabled == True,
                Camera.is_enabled == True,
            ).all()
            camera_ids = [c.id for c in cameras]

        for camera_id in camera_ids:
            try:
                result = await self.process_camera_audio(
                    db,
                    camera_id,
                    audio_duration_seconds=2.0,
                    create_event=True,
                )
                results[camera_id] = result
            except Exception as e:
                logger.error(
                    f"Error processing audio for camera {camera_id}: {e}",
                    exc_info=True,
                    extra={
                        "event_type": "audio_check_error",
                        "camera_id": camera_id,
                        "error": str(e),
                    }
                )
                results[camera_id] = AudioEventCreationResult(
                    event_id=None,
                    audio_event_type=None,
                    confidence=None,
                    created=False,
                    reason=f"error: {str(e)}"
                )

        return results


# Singleton instance
_audio_event_handler: Optional[AudioEventHandler] = None


def get_audio_event_handler() -> AudioEventHandler:
    """
    Get the global AudioEventHandler singleton.

    Returns:
        AudioEventHandler instance (creates one if not exists)
    """
    global _audio_event_handler

    if _audio_event_handler is None:
        _audio_event_handler = AudioEventHandler()

    return _audio_event_handler


def initialize_audio_event_handler(
    audio_extractor: Optional[AudioStreamExtractor] = None,
    audio_detector: Optional[AudioEventDetector] = None,
) -> AudioEventHandler:
    """
    Initialize (or reinitialize) the global AudioEventHandler.

    Args:
        audio_extractor: Optional custom audio extractor
        audio_detector: Optional custom audio detector

    Returns:
        Newly initialized AudioEventHandler instance
    """
    global _audio_event_handler

    _audio_event_handler = AudioEventHandler(
        audio_extractor=audio_extractor,
        audio_detector=audio_detector,
    )
    logger.info("Global AudioEventHandler initialized")

    return _audio_event_handler
