"""
ProtectAIPipeline

Handles the AI analysis submission for qualifying Protect events.

Responsibilities:
- Snapshot → AI description (with full fallback chain: video_native → multi_frame → single_frame)
- Tracking analysis mode, frame count, fallback reasons
- Integration with VisionAnalysisOrchestrator
- Context-enhanced prompts (MCP)

Extracted from ProtectEventHandler during Phase 4 decomposition.

Migrated to @singleton decorator as part of #450 (Lightweight DI Container).
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Any, TYPE_CHECKING

from app.services.snapshot_service import SnapshotResult
from app.models.camera import Camera
from app.core.decorators import singleton

if TYPE_CHECKING:
    from app.services.ai_service import AIResult

logger = logging.getLogger(__name__)


@singleton
class ProtectAIPipeline:
    """
    Service responsible for running AI analysis on Protect event snapshots/clips.

    This class owns the complex fallback logic so ProtectEventHandler can stay focused
    on event flow coordination.
    """

    def __init__(self):
        self._last_analysis_mode: Optional[str] = None
        self._last_frame_count: Optional[int] = None
        self._last_fallback_reason: Optional[str] = None
        self._last_audio_transcription: Optional[str] = None
        self._last_extracted_frames: List[bytes] = []
        self._last_frame_timestamps: List[float] = []

    async def submit_snapshot_for_analysis(
        self,
        snapshot_result: SnapshotResult,
        camera: Camera,
        event_type: str,
        is_doorbell_ring: bool = False,
        clip_path: Optional[Path] = None,
    ) -> Optional["AIResult"]:
        """
        Submit a Protect snapshot (and optional clip) to the AI pipeline.

        Implements the full fallback chain and tracking.
        """
        # Reset tracking state for this event
        self._last_analysis_mode = None
        self._last_frame_count = None
        self._last_fallback_reason = None
        self._last_audio_transcription = None
        self._last_extracted_frames = []
        self._last_frame_timestamps = []

        # Lazy import to avoid circular dependency
        from app.services.vision_analysis_orchestrator import get_vision_analysis_orchestrator
        from app.services.ai_service import ai_service
        from app.core.database import get_db_session

        try:
            # Ensure AI keys are loaded
            with get_db_session() as db:
                await ai_service.load_api_keys_from_db(db)

            # For now, delegate to the existing orchestrator (single frame path)
            # Full multi-frame + video_native logic can be wired here later
            # (the original complex logic lived in _submit_to_ai_pipeline)

            # Convert snapshot to the format expected by the orchestrator
            # (This is a simplified version — the full original logic was very long)

            # Placeholder: In a full extraction we would replicate the fallback chain here
            # For this micro-step, we delegate the core call

            # TODO: Full extraction of the fallback chain from the old _submit_to_ai_pipeline

            logger.info(
                f"Submitting snapshot for AI analysis (camera={camera.name}, type={event_type})",
                extra={"event_type": "protect_ai_submission"}
            )

            # === Video Native path (Gemini native video upload) ===
            if clip_path:
                try:
                    video_result = await self._try_video_native_analysis(
                        clip_path, camera, event_type, is_doorbell_ring
                    )
                    if video_result:
                        self._last_analysis_mode = "video_native"
                        self._last_frame_count = None  # Video native uses the full clip
                        logger.info(
                            f"Video native analysis successful for camera '{camera.name}'",
                            extra={"event_type": "protect_ai_video_native_success"}
                        )
                        return video_result
                except Exception as e:
                    self._last_fallback_reason = f"video_native_failed:{str(e)}"
                    logger.warning(f"Video native analysis failed for camera '{camera.name}', falling back: {e}")

            # === Multi-frame path (preferred when clip is available) ===
            if clip_path:
                try:
                    frames, timestamps = await self._extract_frames_from_clip(clip_path, camera)
                    if frames:
                        ai_result = await get_vision_analysis_orchestrator().analyze_images(
                            images=frames,  # List[bytes] or List[np.ndarray] depending on orchestrator signature
                            camera_name=camera.name,
                            timestamp=datetime.now(timezone.utc).isoformat(),
                            detected_objects=[event_type] if event_type else None,
                            custom_prompt=None,
                        )
                        self._last_analysis_mode = "multi_frame"
                        self._last_frame_count = len(frames)
                        self._last_extracted_frames = frames
                        self._last_frame_timestamps = timestamps or []

                        logger.info(
                            f"Multi-frame analysis successful for camera '{camera.name}' ({len(frames)} frames)",
                            extra={"event_type": "protect_ai_multi_frame_success"}
                        )
                        return ai_result
                except Exception as e:
                    self._last_fallback_reason = f"multi_frame_failed:{str(e)}"
                    logger.warning(f"Multi-frame analysis failed for camera '{camera.name}', falling back to single frame: {e}")

            # === Single-frame fallback path ===
            import base64
            import numpy as np
            from PIL import Image
            import io

            image_data = base64.b64decode(snapshot_result.image_base64)
            pil_image = Image.open(io.BytesIO(image_data)).convert('RGB')
            frame = np.array(pil_image)[:, :, ::-1]  # RGB to BGR

            ai_result = await get_vision_analysis_orchestrator().analyze_image(
                frame=frame,
                camera_name=camera.name,
                timestamp=datetime.now(timezone.utc).isoformat(),
                detected_objects=[event_type] if event_type else None,
                custom_prompt=None,
            )

            self._last_analysis_mode = "single_frame"
            self._last_frame_count = 1
            self._last_fallback_reason = self._last_fallback_reason or None

            return ai_result

        except Exception as e:
            logger.error(f"AI pipeline submission failed: {e}")
            self._last_fallback_reason = f"exception:{str(e)}"
            return None
            return None

    async def _extract_frames_from_clip(self, clip_path: Path, camera: Camera) -> tuple[List[bytes], List[float]]:
        """
        Extract key frames from a Protect motion clip using the FrameExtractor service.

        Returns (frames_as_bytes, timestamps)
        """
        try:
            from app.services.frame_extractor import get_frame_extractor

            extractor = get_frame_extractor()
            # Use adaptive or uniform sampling based on camera settings if available
            frames, timestamps = await extractor.extract_frames(
                video_path=clip_path,
                max_frames=5,           # Reasonable default for cost control
                strategy="adaptive"     # Can be made configurable later
            )

            # Convert to bytes if they come back as numpy arrays
            frame_bytes = []
            for frame in frames:
                if isinstance(frame, np.ndarray):
                    import cv2
                    _, buffer = cv2.imencode('.jpg', frame)
                    frame_bytes.append(buffer.tobytes())
                else:
                    frame_bytes.append(frame)

            return frame_bytes, timestamps or []

        except Exception as e:
            logger.warning(f"Frame extraction failed for clip {clip_path}: {e}")
            return [], []

    async def _try_video_native_analysis(
        self,
        clip_path: Path,
        camera: Camera,
        event_type: str,
        is_doorbell_ring: bool = False,
    ) -> Optional["AIResult"]:
        """
        Attempt native video analysis (currently only Gemini supports this well).

        Returns AIResult on success, None if the provider doesn't support it or it fails
        (so the caller can fall back to multi-frame/single-frame).
        """
        # Find a video-capable provider (Gemini preferred)
        gemini_provider = None
        for provider_enum, provider in self._get_providers().items():
            if provider_enum.value == "gemini" and hasattr(provider, "describe_video"):
                gemini_provider = provider
                break

        if not gemini_provider:
            # No native video provider available → let caller fall back
            return None

        try:
            result = await gemini_provider.describe_video(
                video_path=clip_path,
                camera_name=camera.name,
                timestamp=datetime.now(timezone.utc).isoformat(),
                detected_objects=[event_type] if event_type else None,
                custom_prompt=None,  # Can be enhanced later with doorbell prompt
            )

            if result and result.success:
                return result

            return None

        except Exception as e:
            logger.warning(f"Gemini native video analysis failed: {e}")
            return None

    def _get_providers(self):
        """Helper to access configured providers (will be improved when we inject them properly)."""
        # Temporary: get from the global AI service until we improve dependency injection
        from app.services.ai_service import ai_service
        return ai_service.providers if hasattr(ai_service, "providers") else {}

    # Accessors for the tracking state (used by event storage)
    @property
    def last_analysis_mode(self) -> Optional[str]:
        return self._last_analysis_mode

    @property
    def last_frame_count(self) -> Optional[int]:
        return self._last_frame_count

    @property
    def last_fallback_reason(self) -> Optional[str]:
        return self._last_fallback_reason

    @property
    def last_audio_transcription(self) -> Optional[str]:
        return self._last_audio_transcription


# Backward compatible getter (delegates to @singleton decorator)
def get_protect_ai_pipeline() -> "ProtectAIPipeline":
    return ProtectAIPipeline()


def reset_protect_ai_pipeline() -> None:
    ProtectAIPipeline._reset_instance()