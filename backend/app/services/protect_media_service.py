"""
ProtectMediaService

Responsible for retrieving the appropriate media (snapshot + optional motion clip)
for a qualifying Protect event.

Handles:
- Deciding whether a clip should be downloaded for an event
- Coordinating with SnapshotService and ClipService
- Returning a clean MediaBundle for the AI pipeline
- Cleanup of temporary media

Extracted from ProtectEventHandler during Phase 4 decomposition.

# Migrated to @singleton decorator as part of #450 (Lightweight DI Container).
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from app.services.snapshot_service import get_snapshot_service, SnapshotResult
from app.services.clip_service import get_clip_service
from app.core.decorators import singleton

logger = logging.getLogger(__name__)


class MediaBundle:
    """Container for media needed by the AI pipeline for a Protect event."""
    def __init__(
        self,
        snapshot_result: Optional[SnapshotResult] = None,
        clip_path: Optional[Path] = None,
        fallback_reason: Optional[str] = None,
    ):
        self.snapshot_result = snapshot_result
        self.clip_path = clip_path
        self.fallback_reason = fallback_reason

    @property
    def has_clip(self) -> bool:
        return self.clip_path is not None

    @property
    def has_snapshot(self) -> bool:
        return self.snapshot_result is not None


@singleton
class ProtectMediaService:
    """
    Service that owns snapshot + clip retrieval decisions and coordination for Protect events.
    """

    def __init__(self):
        pass

    async def get_media_for_event(
        self,
        controller_id: str,
        protect_camera_id: str,
        camera_id: str,
        camera_name: str,
        event_id: str,
        event_timestamp: datetime,
        is_doorbell_ring: bool = False,
    ) -> MediaBundle:
        """
        Retrieve the best available media for AI analysis of this event.

        Strategy:
        - Always retrieve a snapshot (needed for thumbnail + fallback)
        - Attempt clip download for non-ring events when useful
        - Return a MediaBundle the AI pipeline can use
        """
        bundle = MediaBundle()

        # Always get a snapshot (required for thumbnail and single-frame fallback)
        bundle.snapshot_result = await self._retrieve_snapshot(
            controller_id, protect_camera_id, camera_id, camera_name, "motion"
        )

        if not bundle.snapshot_result:
            bundle.fallback_reason = "snapshot_retrieval_failed"
            return bundle

        # Decide whether to attempt clip download
        # For now: attempt for most events, skip for simple doorbell rings if desired
        should_attempt_clip = not is_doorbell_ring

        if should_attempt_clip:
            clip_path, clip_fallback = await self._download_clip(
                controller_id,
                protect_camera_id,
                camera_id,
                camera_name,
                event_id,
                event_timestamp,
            )
            bundle.clip_path = clip_path
            if clip_fallback:
                bundle.fallback_reason = clip_fallback

        return bundle

    async def _retrieve_snapshot(
        self,
        controller_id: str,
        protect_camera_id: str,
        camera_id: str,
        camera_name: str,
        event_type: str,
    ) -> Optional[SnapshotResult]:
        try:
            snapshot_service = get_snapshot_service()
            result = await snapshot_service.get_snapshot(
                controller_id=controller_id,
                protect_camera_id=protect_camera_id,
                camera_id=camera_id,
                camera_name=camera_name,
                timestamp=datetime.now(),
            )
            return result
        except Exception as e:
            logger.warning(f"Snapshot retrieval failed for camera '{camera_name}': {e}")
            return None

    async def _download_clip(
        self,
        controller_id: str,
        protect_camera_id: str,
        camera_id: str,
        camera_name: str,
        event_id: str,
        event_timestamp: datetime,
    ) -> Tuple[Optional[Path], Optional[str]]:
        try:
            clip_service = get_clip_service()

            clip_start = event_timestamp - timedelta(seconds=15)
            clip_end = event_timestamp + timedelta(seconds=15)

            clip_path = await clip_service.download_clip(
                controller_id=controller_id,
                protect_camera_id=protect_camera_id,
                start_time=clip_start,
                end_time=clip_end,
                event_id=event_id,
            )

            if clip_path:
                return clip_path, None
            else:
                return None, "clip_download_failed"

        except Exception as e:
            logger.warning(f"Clip download failed for camera '{camera_name}': {e}")
            return None, "clip_download_exception"

    def cleanup_clip(self, event_id: str) -> bool:
        """Best-effort cleanup of a downloaded clip."""
        try:
            clip_service = get_clip_service()
            return clip_service.cleanup_clip(event_id)
        except Exception as e:
            logger.warning(f"Clip cleanup failed for event {event_id}: {e}")
            return False


# Backward compatible getter (delegates to @singleton decorator)
def get_protect_media_service() -> "ProtectMediaService":
    return ProtectMediaService()


def reset_protect_media_service() -> None:
    ProtectMediaService._reset_instance()