"""
VideoStorageService for downloading and storing full motion videos from UniFi Protect
(Story P8-3.2)

Provides functionality to:
- Download motion video clips from Protect cameras for permanent storage
- Store videos as original MP4 (no re-encoding) at data/videos/{event_id}.mp4
- Handle download failures gracefully (log but don't block event processing)
- Clean up old videos based on video_retention_days setting

Architecture Reference: docs/architecture-phase8.md#Video-Storage

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import asyncio
import logging
from app.core.decorators import singleton
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.protect_service import ProtectService

logger = logging.getLogger(__name__)

# Video storage configuration
VIDEO_DIR = "data/videos"
DOWNLOAD_TIMEOUT = 60.0  # 60 second timeout for video download (videos can be large)


@singleton
class VideoStorageService:
    """
    Service for downloading and storing full motion videos from UniFi Protect.

    This service handles:
    - Downloading motion clips via the uiprotect library
    - Storing videos permanently in data/videos/{event_id}.mp4
    - Ensuring the video directory exists
    - Graceful error handling (returns None, never raises)
    - Video cleanup for retention management

    Uses ProtectService singleton to access authenticated ProtectApiClient
    connections - does NOT create new connections.

    Attributes:
        _protect_service: Reference to ProtectService for client access
    """

    def __init__(self, protect_service: "ProtectService"):
        """
        Initialize VideoStorageService with ProtectService dependency.

        Args:
            protect_service: ProtectService instance for accessing
                           authenticated Protect controller connections
        """
        self._protect_service = protect_service

        # Ensure video directory exists on init
        self._ensure_video_dir()

    def _ensure_video_dir(self) -> None:
        """
        Create the video storage directory if it doesn't exist.

        Creates data/videos/ directory for permanent video storage.
        This directory should be gitignored.
        """
        video_dir = Path(VIDEO_DIR)
        if not video_dir.exists():
            video_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Created video storage directory",
                extra={
                    "event_type": "video_dir_created",
                    "path": str(video_dir)
                }
            )

    def _get_video_path(self, event_id: str) -> Path:
        """
        Get the file path for storing a video.

        Args:
            event_id: Unique identifier for the event

        Returns:
            Path object for data/videos/{event_id}.mp4
        """
        return Path(VIDEO_DIR) / f"{event_id}.mp4"

    def get_video_path_if_exists(self, event_id: str) -> Optional[Path]:
        """
        Get the video path if the video file exists.

        Args:
            event_id: Unique identifier for the event

        Returns:
            Path to the video file if it exists, None otherwise
        """
        video_path = self._get_video_path(event_id)
        if video_path.exists() and video_path.stat().st_size > 0:
            return video_path
        return None

    async def download_video(
        self,
        event_id: str,
        controller_id: str,
        camera_id: str,
        event_start: datetime,
        event_end: datetime
    ) -> Optional[Path]:
        """
        Download a motion video from UniFi Protect for permanent storage.

        Downloads the video clip for the specified time range from the
        Protect controller and saves it to data/videos/{event_id}.mp4.
        Does NOT retry on failure - gracefully returns None.

        Args:
            event_id: Unique identifier for the event (used for filename)
            controller_id: UUID of the Protect controller
            camera_id: Native Protect camera ID
            event_start: Start time of the clip
            event_end: End time of the clip

        Returns:
            Path to the downloaded video file on success, None on failure.
            Never raises exceptions - all errors are logged and return None.

        Note:
            - Uses existing controller credentials from ProtectService
            - Download must complete within 60 seconds
            - Creates data/videos/ directory if needed
            - Does NOT block event processing on failure
        """
        start_time = time.time()

        logger.info(
            "Starting video download for storage",
            extra={
                "event_type": "video_download_start",
                "event_id": event_id,
                "controller_id": controller_id,
                "camera_id": camera_id,
                "event_start": event_start.isoformat(),
                "event_end": event_end.isoformat()
            }
        )

        # Ensure directory exists
        self._ensure_video_dir()

        # Get authenticated client from ProtectService
        client = self._protect_service._connections.get(controller_id)
        if not client:
            logger.warning(
                "Video download failed - controller not connected",
                extra={
                    "event_type": "video_download_not_connected",
                    "event_id": event_id,
                    "controller_id": controller_id
                }
            )
            return None

        # Get output path
        output_path = self._get_video_path(event_id)

        try:
            # Download with timeout
            async with asyncio.timeout(DOWNLOAD_TIMEOUT):
                await client.get_camera_video(
                    camera_id=camera_id,
                    start=event_start,
                    end=event_end,
                    output_file=output_path
                )

            # Verify file was created and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                duration = time.time() - start_time
                file_size = output_path.stat().st_size

                logger.info(
                    "Video download succeeded",
                    extra={
                        "event_type": "video_download_success",
                        "event_id": event_id,
                        "controller_id": controller_id,
                        "camera_id": camera_id,
                        "file_path": str(output_path),
                        "file_size_bytes": file_size,
                        "file_size_mb": round(file_size / (1024 * 1024), 2),
                        "download_duration_seconds": round(duration, 2)
                    }
                )
                return output_path
            else:
                # Empty or missing file
                if output_path.exists():
                    output_path.unlink()
                logger.warning(
                    "Video download produced empty or missing file",
                    extra={
                        "event_type": "video_download_empty",
                        "event_id": event_id,
                        "camera_id": camera_id
                    }
                )
                return None

        except asyncio.TimeoutError:
            logger.warning(
                f"Video download timed out after {DOWNLOAD_TIMEOUT}s",
                extra={
                    "event_type": "video_download_timeout",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "timeout_seconds": DOWNLOAD_TIMEOUT
                }
            )
            # Clean up partial file
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            return None

        except Exception as e:
            logger.error(
                f"Video download failed: {type(e).__name__}: {e}",
                extra={
                    "event_type": "video_download_error",
                    "event_id": event_id,
                    "camera_id": camera_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            # Clean up partial file
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            return None

    def delete_video(self, event_id: str) -> bool:
        """
        Delete a video file by event ID.

        Args:
            event_id: Unique identifier for the event

        Returns:
            True if video was deleted successfully, False if not found
        """
        video_path = self._get_video_path(event_id)

        if not video_path.exists():
            return False

        try:
            file_size = video_path.stat().st_size
            video_path.unlink()
            logger.info(
                "Video deleted successfully",
                extra={
                    "event_type": "video_deleted",
                    "event_id": event_id,
                    "file_size_bytes": file_size
                }
            )
            return True
        except OSError as e:
            logger.warning(
                f"Failed to delete video: {e}",
                extra={
                    "event_type": "video_delete_error",
                    "event_id": event_id,
                    "error_message": str(e)
                }
            )
            return False

    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get statistics about video storage.

        Returns:
            Dict with:
                - total_videos: Number of video files
                - total_size_mb: Total size in megabytes
                - oldest_video_age_days: Age of oldest video in days
        """
        video_dir = Path(VIDEO_DIR)
        if not video_dir.exists():
            return {
                "total_videos": 0,
                "total_size_mb": 0.0,
                "oldest_video_age_days": 0
            }

        total_size = 0
        oldest_mtime = None
        video_count = 0

        for video_file in video_dir.glob("*.mp4"):
            try:
                stat = video_file.stat()
                total_size += stat.st_size
                video_count += 1
                if oldest_mtime is None or stat.st_mtime < oldest_mtime:
                    oldest_mtime = stat.st_mtime
            except OSError:
                pass

        oldest_age_days = 0
        if oldest_mtime:
            oldest_age_days = (time.time() - oldest_mtime) / (24 * 3600)

        return {
            "total_videos": video_count,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "oldest_video_age_days": round(oldest_age_days, 1)
        }


# Backward compatible thin getter (delegates to @singleton decorator)
def get_video_storage_service() -> VideoStorageService:
    """
    Get the global VideoStorageService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer VideoStorageService() directly.
    """
    from app.services.protect_service import get_protect_service
    return VideoStorageService(get_protect_service())


def reset_video_storage_service() -> None:
    """Reset the global VideoStorageService instance (for testing)."""
    VideoStorageService._reset_instance()


def reset_video_storage_service() -> None:
    """Reset the global VideoStorageService instance (for testing)."""
    VideoStorageService._reset_instance()
