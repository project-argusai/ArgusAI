"""Audio Event Configuration API Router (Story P6-3.2)

Provides endpoints for managing audio event detection configuration:
- GET /api/v1/audio/thresholds - Retrieve current confidence thresholds
- PATCH /api/v1/audio/thresholds - Update thresholds per event type

Audio event types:
- glass_break: Sound of glass shattering
- gunshot: Sound of gunfire
- scream: Human screaming or distress call
- doorbell: Doorbell ringing sound
- other: Other significant audio event
"""

import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.audio_event_detector import (
    get_audio_event_detector,
    DEFAULT_THRESHOLDS,
)
from app.services.audio_classifiers import AudioEventType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["audio"])


class AudioThresholdsResponse(BaseModel):
    """Response schema for audio detection thresholds"""
    glass_break: float = Field(..., ge=0.0, le=1.0, description="Confidence threshold for glass break detection")
    gunshot: float = Field(..., ge=0.0, le=1.0, description="Confidence threshold for gunshot detection")
    scream: float = Field(..., ge=0.0, le=1.0, description="Confidence threshold for scream detection")
    doorbell: float = Field(..., ge=0.0, le=1.0, description="Confidence threshold for doorbell detection")
    other: float = Field(..., ge=0.0, le=1.0, description="Confidence threshold for other audio events")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "glass_break": 0.70,
                    "gunshot": 0.70,
                    "scream": 0.70,
                    "doorbell": 0.70,
                    "other": 0.70
                }
            ]
        }
    }


class ThresholdUpdateRequest(BaseModel):
    """Request schema for updating a single threshold"""
    event_type: str = Field(
        ...,
        description="Audio event type to update (glass_break, gunshot, scream, doorbell, other)"
    )
    threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="New confidence threshold value (0.0 to 1.0)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_type": "glass_break",
                    "threshold": 0.80
                }
            ]
        }
    }


class ThresholdUpdateResponse(BaseModel):
    """Response schema for threshold update"""
    event_type: str = Field(..., description="Updated audio event type")
    old_threshold: float = Field(..., description="Previous threshold value")
    new_threshold: float = Field(..., description="New threshold value")
    message: str = Field(..., description="Status message")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "event_type": "glass_break",
                    "old_threshold": 0.70,
                    "new_threshold": 0.80,
                    "message": "Threshold updated successfully"
                }
            ]
        }
    }


@router.get(
    "/thresholds",
    response_model=AudioThresholdsResponse,
    summary="Get audio detection thresholds",
    description="""
    Retrieve current confidence thresholds for all audio event types.

    Thresholds determine the minimum confidence score required for an
    audio detection to be recorded as an event. Lower thresholds mean
    more detections (but potentially more false positives).

    Default threshold: 70% (0.70) for all event types.
    """
)
async def get_audio_thresholds(
    db: Session = Depends(get_db),
) -> AudioThresholdsResponse:
    """
    Get current audio detection confidence thresholds.

    Returns thresholds for each audio event type:
    - glass_break
    - gunshot
    - scream
    - doorbell
    - other
    """
    detector = get_audio_event_detector()

    # Load thresholds from database if not already loaded
    detector.load_thresholds_from_db(db)

    thresholds = detector.get_thresholds()

    logger.debug(
        "Retrieved audio thresholds",
        extra={
            "event_type": "audio_thresholds_retrieved",
            "thresholds": thresholds
        }
    )

    return AudioThresholdsResponse(
        glass_break=thresholds.get("glass_break", 0.70),
        gunshot=thresholds.get("gunshot", 0.70),
        scream=thresholds.get("scream", 0.70),
        doorbell=thresholds.get("doorbell", 0.70),
        other=thresholds.get("other", 0.70),
    )


@router.patch(
    "/thresholds",
    response_model=ThresholdUpdateResponse,
    summary="Update audio detection threshold",
    description="""
    Update the confidence threshold for a specific audio event type.

    The threshold determines the minimum confidence score required for
    audio detections of that type to be recorded as events.

    Valid event types: glass_break, gunshot, scream, doorbell, other
    Valid threshold range: 0.0 to 1.0 (0% to 100%)
    """
)
async def update_audio_threshold(
    request: ThresholdUpdateRequest,
    db: Session = Depends(get_db),
) -> ThresholdUpdateResponse:
    """
    Update confidence threshold for an audio event type.

    Args:
        request: Contains event_type and new threshold value

    Returns:
        Updated threshold information

    Raises:
        HTTPException 400: Invalid event type
        HTTPException 422: Invalid threshold value (handled by Pydantic)
    """
    # Validate event type
    event_type = AudioEventType.from_string(request.event_type)
    if event_type is None:
        valid_types = [t.value for t in AudioEventType]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid event type '{request.event_type}'. Valid types: {valid_types}"
        )

    detector = get_audio_event_detector()

    # Get current threshold
    old_threshold = detector.get_threshold(event_type)

    # Save new threshold to database and memory
    detector.save_threshold_to_db(db, event_type, request.threshold)

    logger.info(
        f"Audio threshold updated: {event_type.value} {old_threshold:.2%} -> {request.threshold:.2%}",
        extra={
            "event_type": "audio_threshold_updated",
            "audio_event_type": event_type.value,
            "old_threshold": old_threshold,
            "new_threshold": request.threshold,
        }
    )

    return ThresholdUpdateResponse(
        event_type=event_type.value,
        old_threshold=old_threshold,
        new_threshold=request.threshold,
        message="Threshold updated successfully"
    )


@router.get(
    "/supported-types",
    response_model=Dict[str, str],
    summary="Get supported audio event types",
    description="List all supported audio event types and their descriptions."
)
async def get_supported_audio_types() -> Dict[str, str]:
    """
    Get list of all supported audio event types.

    Returns:
        Dict mapping event type name to description
    """
    return {
        "glass_break": "Sound of glass shattering or breaking",
        "gunshot": "Sound of gunfire or explosions",
        "scream": "Human screaming, shouting, or distress calls",
        "doorbell": "Doorbell ring or chime sounds",
        "other": "Other significant audio events not classified above"
    }
