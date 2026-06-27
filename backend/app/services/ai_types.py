"""
Shared AI Types and Constants

Extracted during Phase 3.4 of the ai_service.py decomposition.

This module centralizes:
- AIProvider enum
- AIResult dataclass
- PROVIDER_CAPABILITIES (for video/image support queries)

This improves maintainability and allows the provider implementations,
orchestrator, and main service to share clean types without circular imports.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class AIProvider(Enum):
    """Supported AI vision providers"""
    OPENAI = "openai"
    GROK = "grok"
    CLAUDE = "claude"
    GEMINI = "gemini"


@dataclass
class AIResult:
    """Result from AI description generation"""
    description: str
    confidence: int  # 0-100 (computed from heuristics)
    objects_detected: List[str]  # person, vehicle, animal, package, unknown
    provider: str  # Which provider was used
    tokens_used: int
    response_time_ms: int
    cost_estimate: float  # USD
    success: bool
    error: Optional[str] = None
    # Story P3-6.1: AI self-reported confidence score
    ai_confidence: Optional[int] = None  # 0-100 (from AI response, None if not provided)
    # Story P4-5.4: A/B test variant tracking
    prompt_variant: Optional[str] = None  # 'control', 'experiment', or None
    # Story P15-5.1: AI Visual Annotations - bounding boxes for detected objects
    bounding_boxes: Optional[List[Dict[str, Any]]] = None  # List of normalized bounding box dicts


# Provider capability matrix (used by capability query endpoints and video analysis decisions)
PROVIDER_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "openai": {
        "video": True,  # P3-4.2: OpenAI supports video via frame extraction
        "video_method": "frame_extraction",
        "max_video_duration": 60,
        "max_video_size_mb": 50,
        "max_frames": 10,
        "supported_formats": ["mp4", "mov", "webm", "avi"],
        "max_images": 10,
        "supports_audio_transcription": True,
    },
    "grok": {
        "video": True,
        "video_method": "frame_extraction",
        "max_video_duration": 60,
        "max_video_size_mb": 50,
        "max_frames": 10,
        "supported_formats": ["mp4", "mov", "webm", "avi"],
        "max_images": 10,
        "supports_audio_transcription": False,
    },
    "claude": {
        "video": False,
        "video_method": None,
        "max_video_duration": 0,
        "max_video_size_mb": 0,
        "max_frames": 0,
        "supported_formats": [],
        "max_images": 20,
        "supports_audio_transcription": False,
    },
    "gemini": {
        "video": True,
        "video_method": "native_upload",
        "max_video_duration": 300,
        "max_video_size_mb": 2048,
        "inline_max_size_mb": 20,
        "max_frames": 0,
        "supported_formats": ["mp4", "mov", "webm", "avi", "flv", "mpg", "mpeg", "wmv"],
        "max_images": 16,
        "supports_audio": True,
    },
}


# Recognition feature flags (SystemSetting keys) - Phase B standardization
FACE_RECOGNITION_ENABLED = "face_recognition_enabled"
VEHICLE_RECOGNITION_ENABLED = "vehicle_recognition_enabled"

# Person matching settings (SystemSetting keys) - Phase B Slice 3
PERSON_MATCH_THRESHOLD = "person_match_threshold"
AUTO_CREATE_PERSONS = "auto_create_persons"
UPDATE_APPEARANCE_ON_HIGH_MATCH = "update_appearance_on_high_match"

# Vehicle matching settings (SystemSetting keys) - Phase B Slice 3
VEHICLE_MATCH_THRESHOLD = "vehicle_match_threshold"
AUTO_CREATE_VEHICLES = "auto_create_vehicles"
