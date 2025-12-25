"""
ClipService for downloading motion video clips from UniFi Protect (Story P3-1.1, P3-1.2, P3-1.3)

Provides functionality to:
- Download motion clips from Protect cameras for AI analysis
- Manage temporary clip storage with automatic cleanup
- Handle download failures gracefully with logging
- Clean up old clips based on age (MAX_CLIP_AGE_HOURS)
- Enforce storage limits (MAX_STORAGE_MB)
- Run periodic background cleanup every 15 minutes
- Retry failed downloads with exponential backoff (Story P3-1.3)

Architecture Reference: docs/architecture.md#Phase-3-Service-Architecture
"""
import asyncio
import atexit
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from apscheduler.schedulers.background import BackgroundScheduler
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryCallState,
)

if TYPE_CHECKING:
    from app.services.protect_service import ProtectService

logger = logging.getLogger(__name__)

# Clip storage configuration (from architecture.md)
TEMP_CLIP_DIR = "data/clips"
MAX_CLIP_AGE_HOURS = 1
MAX_STORAGE_MB = 1024

# Storage pressure threshold (90% of MAX_STORAGE_MB)
STORAGE_PRESSURE_TARGET_MB = int(MAX_STORAGE_MB * 0.9)  # 900MB

# Download timeout in seconds (NFR1: must complete within 10 seconds)
DOWNLOAD_TIMEOUT = 10.0

# Cleanup scheduler interval in minutes
CLEANUP_INTERVAL_MINUTES = 15

# Retry configuration (Story P3-1.3, NFR5)
MAX_RETRY_ATTEMPTS = 3
RETRY_MIN_WAIT = 1  # seconds
RETRY_MAX_WAIT = 4  # seconds


class RetriableClipError(Exception):
    """
    Exception for clip download errors that should trigger retry.

    Used for transient failures like:
    - Network timeouts (asyncio.TimeoutError)
    - Connection errors (ConnectionError)
    - Temporary server errors
    """
    pass


class NonRetriableClipError(Exception):
    """
    Exception for clip download errors that should NOT retry.

    Used for permanent failures like:
    - 404 Not Found (clip doesn't exist)
    - Invalid camera ID
    - Authentication failures
    - Empty/missing file after download
    """
    pass


class ClipService:
    """
    Service for downloading and managing video clips from UniFi Protect.

    This service handles:
    - Downloading motion clips via the uiprotect library
    - Storing clips temporarily in data/clips/{event_id}.mp4
    - Ensuring the clip directory exists
    - Graceful error handling (returns None, never raises)
    - Automatic cleanup of old clips (> MAX_CLIP_AGE_HOURS)
    - Storage pressure management (target < 900MB when over 1GB)
    - Background cleanup scheduler (every 15 minutes)
    - Retry failed downloads with exponential backoff (Story P3-1.3)

    Uses ProtectService singleton to access authenticated ProtectApiClient
    connections - does NOT create new connections.

    Attributes:
        _protect_service: Reference to ProtectService for client access
        _scheduler: APScheduler instance for background cleanup tasks
    """

    def __init__(self, protect_service: "ProtectService"):
        """
        Initialize ClipService with ProtectService dependency.

        On initialization:
        - Creates clip directory if not exists
        - Runs initial cleanup of stale files
        - Starts background scheduler for periodic cleanup

        Args:
            protect_service: ProtectService instance for accessing
                           authenticated Protect controller connections
        """
        self._protect_service = protect_service
        self._scheduler: Optional[BackgroundScheduler] = None

        # Ensure clip directory exists on init
        self._ensure_clip_dir()

        # Run initial cleanup (don't fail init on cleanup errors)
        try:
            deleted_count = self.cleanup_old_clips()
            if deleted_count > 0:
                logger.info(
                    "Startup cleanup completed",
                    extra={
                        "event_type": "clip_startup_cleanup",
                        "deleted_count": deleted_count
                    }
                )
        except Exception as e:
            logger.warning(
                f"Startup cleanup failed: {type(e).__name__}",
                extra={
                    "event_type": "clip_startup_cleanup_error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

        # Start background cleanup scheduler
        self._start_scheduler()

    def _ensure_clip_dir(self) -> None:
        """
        Create the clip storage directory if it doesn't exist.

        Creates data/clips/ directory for temporary clip storage.
        This directory should be gitignored.
        """
        clip_dir = Path(TEMP_CLIP_DIR)
        if not clip_dir.exists():
            clip_dir.mkdir(parents=True, exist_ok=True)
            logger.info(
                "Created clip storage directory",
                extra={
                    "event_type": "clip_dir_created",
                    "path": str(clip_dir)
                }
            )

    def _get_clip_path(self, event_id: str) -> Path:
        """
        Get the file path for storing a clip.

        Args:
            event_id: Unique identifier for the event

        Returns:
            Path object for data/clips/{event_id}.mp4
        """
        return Path(TEMP_CLIP_DIR) / f"{event_id}.mp4"

    def _get_directory_size_bytes(self) -> int:
        """
        Calculate total size of clips directory in bytes.

        Returns:
            Total size of all .mp4 files in data/clips/ in bytes
        """
        total = 0
        clip_dir = Path(TEMP_CLIP_DIR)
        if clip_dir.exists():
            for f in clip_dir.glob("*.mp4"):
                try:
                    total += f.stat().st_size
                except OSError:
                    pass  # File may have been deleted
        return total

    def _start_scheduler(self) -> None:
        """
        Start the background cleanup scheduler.

        Schedules cleanup_old_clips() to run every 15 minutes.
        """
        if self._scheduler is not None:
            return  # Already running

        try:
            self._scheduler = BackgroundScheduler()
            self._scheduler.add_job(
                self.cleanup_old_clips,
                'interval',
                minutes=CLEANUP_INTERVAL_MINUTES,
                id='clip_cleanup',
                replace_existing=True
            )
            self._scheduler.start()

            # Register shutdown handler
            atexit.register(self._stop_scheduler)

            logger.info(
                "Clip cleanup scheduler started",
                extra={
                    "event_type": "clip_scheduler_started",
                    "interval_minutes": CLEANUP_INTERVAL_MINUTES
                }
            )
        except Exception as e:
            logger.warning(
                f"Failed to start cleanup scheduler: {type(e).__name__}",
                extra={
                    "event_type": "clip_scheduler_start_error",
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )

    def _stop_scheduler(self) -> None:
        """
        Stop the background cleanup scheduler gracefully.

        Handles the case where logging streams may be closed during
        pytest teardown (when atexit handlers run after stream closure).
        """
        if self._scheduler is not None:
            try:
                # Suppress APScheduler's internal logging during shutdown
                # to avoid "I/O operation on closed file" errors when
                # pytest closes streams before atexit handlers run
                apscheduler_logger = logging.getLogger('apscheduler')
                original_level = apscheduler_logger.level
                apscheduler_logger.setLevel(logging.CRITICAL + 1)

                # Also suppress our own logger to avoid logging errors
                original_self_level = logger.level
                logger.setLevel(logging.CRITICAL + 1)

                try:
                    self._scheduler.shutdown(wait=False)
                finally:
                    # Restore original levels (suppress any errors from this)
                    try:
                        apscheduler_logger.setLevel(original_level)
                        logger.setLevel(original_self_level)
                    except Exception:
                        pass

            except Exception:
                # Silently handle any shutdown errors - logging may not work
                pass
            finally:
                self._scheduler = None

    def _check_storage_pressure(self) -> int:
        """
        Check and enforce storage limits by deleting oldest clips.

        If total clips directory size exceeds MAX_STORAGE_MB (1GB),
        deletes oldest files until under STORAGE_PRESSURE_TARGET_MB (900MB).

        Returns:
            Number of files deleted due to storage pressure
        """
        clip_dir = Path(TEMP_CLIP_DIR)
        if not clip_dir.exists():
            return 0

        total_bytes = self._get_directory_size_bytes()
        max_bytes = MAX_STORAGE_MB * 1024 * 1024
        target_bytes = STORAGE_PRESSURE_TARGET_MB * 1024 * 1024

        if total_bytes <= max_bytes:
            return 0

        # Log warning about storage pressure
        logger.warning(
            f"Storage pressure detected: {total_bytes / (1024*1024):.1f}MB > {MAX_STORAGE_MB}MB limit",
            extra={
                "event_type": "clip_storage_pressure",
                "current_size_mb": total_bytes / (1024 * 1024),
                "limit_mb": MAX_STORAGE_MB,
                "target_mb": STORAGE_PRESSURE_TARGET_MB
            }
        )

        # Get all clips sorted by mtime (oldest first)
        clips = []
        for f in clip_dir.glob("*.mp4"):
            try:
                clips.append((f, f.stat().st_mtime, f.stat().st_size))
            except OSError:
                pass

        clips.sort(key=lambda x: x[1])  # Sort by mtime ascending (oldest first)

        deleted_count = 0
        for clip_path, _, clip_size in clips:
            if total_bytes <= target_bytes:
                break

            try:
                clip_path.unlink()
                total_bytes -= clip_size
                deleted_count += 1
                logger.info(
                    "Deleted clip due to storage pressure",
                    extra={
                        "event_type": "clip_storage_pressure_delete",
                        "file_path": str(clip_path),
                        "file_size_bytes": clip_size,
                        "remaining_size_mb": total_bytes / (1024 * 1024)
                    }
                )
            except OSError as e:
                logger.warning(
                    f"Failed to delete clip during storage cleanup: {e}",
                    extra={
                        "event_type": "clip_storage_pressure_delete_error",
                        "file_path": str(clip_path),
                        "error_message": str(e)
                    }
                )

        if deleted_count > 0:
            logger.info(
                f"Storage pressure resolved: deleted {deleted_count} clips",
                extra={
                    "event_type": "clip_storage_pressure_resolved",
                    "deleted_count": deleted_count,
                    "new_size_mb": total_bytes / (1024 * 1024)
                }
            )

        return deleted_count

    def cleanup_clip(self, event_id: str) -> bool:
        """
        Delete a single clip by event ID.

        Args:
            event_id: Unique identifier for the event

        Returns:
            True if clip was deleted successfully, False if not found
        """
        clip_path = self._get_clip_path(event_id)

        if not clip_path.exists():
            logger.debug(
                "Clip not found for cleanup",
                extra={
                    "event_type": "clip_cleanup_not_found",
                    "event_id": event_id,
                    "file_path": str(clip_path)
                }
            )
            return False

        try:
            file_size = clip_path.stat().st_size
            clip_path.unlink()
            logger.info(
                "Clip deleted successfully",
                extra={
                    "event_type": "clip_cleanup_success",
                    "event_id": event_id,
                    "file_path": str(clip_path),
                    "file_size_bytes": file_size
                }
            )
            return True
        except OSError as e:
            logger.warning(
                f"Failed to delete clip: {e}",
                extra={
                    "event_type": "clip_cleanup_error",
                    "event_id": event_id,
                    "file_path": str(clip_path),
                    "error_message": str(e)
                }
            )
            return False

    def cleanup_old_clips(self) -> int:
        """
        Delete all clips older than MAX_CLIP_AGE_HOURS.

        Also checks and enforces storage pressure limits after age-based cleanup.

        Returns:
            Total count of deleted files (age + storage pressure)
        """
        clip_dir = Path(TEMP_CLIP_DIR)
        if not clip_dir.exists():
            return 0

        cutoff_time = time.time() - (MAX_CLIP_AGE_HOURS * 3600)
        deleted_count = 0

        for clip_path in clip_dir.glob("*.mp4"):
            try:
                mtime = clip_path.stat().st_mtime
                if mtime < cutoff_time:
                    file_size = clip_path.stat().st_size
                    clip_path.unlink()
                    deleted_count += 1
                    logger.info(
                        "Deleted old clip",
                        extra={
                            "event_type": "clip_age_cleanup",
                            "file_path": str(clip_path),
                            "file_size_bytes": file_size,
                            "file_age_hours": (time.time() - mtime) / 3600
                        }
                    )
            except OSError as e:
                logger.warning(
                    f"Failed to check/delete clip: {e}",
                    extra={
                        "event_type": "clip_age_cleanup_error",
                        "file_path": str(clip_path),
                        "error_message": str(e)
                    }
                )

        if deleted_count > 0:
            logger.info(
                f"Age-based cleanup completed: deleted {deleted_count} clips",
                extra={
                    "event_type": "clip_age_cleanup_complete",
                    "deleted_count": deleted_count
                }
            )

        # Also check storage pressure
        pressure_deleted = self._check_storage_pressure()

        return deleted_count + pressure_deleted

    def _log_retry_attempt(self, retry_state: RetryCallState) -> None:
        """
        Log each retry attempt with structured logging (Story P3-1.3).

        Called by tenacity before sleeping between retry attempts.

        Args:
            retry_state: Tenacity retry state with attempt info
        """
        # Extract attempt number and wait time
        attempt_number = retry_state.attempt_number
        # Calculate wait time (exponential: 1, 2, 4 seconds)
        wait_seconds = min(
            RETRY_MAX_WAIT,
            RETRY_MIN_WAIT * (2 ** (attempt_number - 1))
        )

        # Get error info from the outcome
        exception = retry_state.outcome.exception() if retry_state.outcome else None
        error_type = type(exception).__name__ if exception else "Unknown"
        error_message = str(exception) if exception else ""

        logger.warning(
            f"Clip download retry attempt {attempt_number} after {error_type}",
            extra={
                "event_type": "clip_download_retry",
                "attempt_number": attempt_number,
                "wait_seconds": wait_seconds,
                "error_type": error_type,
                "error_message": error_message
            }
        )

    async def _download_clip_attempt(
        self,
        client,
        camera_id: str,
        event_start: datetime,
        event_end: datetime,
        output_path: Path
    ) -> Path:
        """
        Internal method to attempt a single clip download.

        This method is wrapped with retry logic and raises exceptions
        that are classified as retriable or non-retriable.

        Args:
            client: Authenticated ProtectApiClient
            camera_id: Native Protect camera ID
            event_start: Start time of the clip
            event_end: End time of the clip
            output_path: Path to save the clip file

        Returns:
            Path to the downloaded clip file on success

        Raises:
            RetriableClipError: For transient errors (timeout, connection)
            NonRetriableClipError: For permanent errors (404, empty file)
        """
        try:
            # Download with timeout (NFR1: 10 second limit per attempt)
            async with asyncio.timeout(DOWNLOAD_TIMEOUT):
                await client.get_camera_video(
                    camera_id=camera_id,
                    start=event_start,
                    end=event_end,
                    output_file=output_path
                )

            # Verify file was created and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                return output_path
            else:
                # Empty or missing file - non-retriable (likely no video recorded)
                if output_path.exists():
                    output_path.unlink()
                raise NonRetriableClipError(
                    f"Download produced empty or missing file for camera {camera_id}"
                )

        except asyncio.TimeoutError as e:
            # Timeout is retriable
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            raise RetriableClipError(f"Download timed out after {DOWNLOAD_TIMEOUT}s") from e

        except (ConnectionError, OSError) as e:
            # Connection errors are retriable
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            raise RetriableClipError(f"Connection error: {e}") from e

        except NonRetriableClipError:
            # Re-raise non-retriable errors
            raise

        except RetriableClipError:
            # Re-raise retriable errors
            raise

        except Exception as e:
            # Classify unknown exceptions
            error_str = str(e).lower()
            # Check for 404/not found errors - non-retriable
            if "404" in error_str or "not found" in error_str:
                raise NonRetriableClipError(f"Clip not found: {e}") from e
            # Check for authentication errors - non-retriable
            if "auth" in error_str or "unauthorized" in error_str or "403" in error_str:
                raise NonRetriableClipError(f"Authentication error: {e}") from e
            # Default to retriable for unknown errors
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            raise RetriableClipError(f"Download failed: {e}") from e

    async def download_clip(
        self,
        controller_id: str,
        camera_id: str,
        event_start: datetime,
        event_end: datetime,
        event_id: str
    ) -> Optional[Path]:
        """
        Download a motion clip from UniFi Protect with retry logic.

        Downloads the video clip for the specified time range from the
        Protect controller and saves it to data/clips/{event_id}.mp4.
        Automatically retries up to 3 times with exponential backoff
        (1s, 2s, 4s) for transient failures (Story P3-1.3).

        Args:
            controller_id: UUID of the Protect controller
            camera_id: Native Protect camera ID
            event_start: Start time of the clip
            event_end: End time of the clip
            event_id: Unique identifier for the event (used for filename)

        Returns:
            Path to the downloaded clip file on success, None on failure.
            Never raises exceptions - all errors are logged and return None.

        Note:
            - Uses existing controller credentials from ProtectService
            - Download must complete within 10 seconds per attempt (NFR1)
            - Retries up to 3 times with exponential backoff (NFR5)
            - Creates data/clips/ directory if needed
        """
        logger.info(
            "Starting clip download",
            extra={
                "event_type": "clip_download_start",
                "controller_id": controller_id,
                "camera_id": camera_id,
                "event_id": event_id,
                "event_start": event_start.isoformat(),
                "event_end": event_end.isoformat()
            }
        )

        # Ensure directory exists
        self._ensure_clip_dir()

        # Get authenticated client from ProtectService
        client = self._protect_service._connections.get(controller_id)
        if not client:
            logger.warning(
                "Clip download failed - controller not connected",
                extra={
                    "event_type": "clip_download_not_connected",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "event_id": event_id
                }
            )
            return None

        # Get output path
        output_path = self._get_clip_path(event_id)

        # Create retry-wrapped version of _download_clip_attempt
        @retry(
            stop=stop_after_attempt(MAX_RETRY_ATTEMPTS),
            wait=wait_exponential(multiplier=1, min=RETRY_MIN_WAIT, max=RETRY_MAX_WAIT),
            retry=retry_if_exception_type(RetriableClipError),
            before_sleep=self._log_retry_attempt,
            reraise=True
        )
        async def attempt_with_retry():
            return await self._download_clip_attempt(
                client=client,
                camera_id=camera_id,
                event_start=event_start,
                event_end=event_end,
                output_path=output_path
            )

        try:
            result = await attempt_with_retry()

            # Log success with attempt count
            # Note: attempt_with_retry.statistics gives us retry info
            logger.info(
                "Clip download succeeded",
                extra={
                    "event_type": "clip_download_success",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "file_path": str(result),
                    "file_size_bytes": result.stat().st_size
                }
            )
            return result

        except RetriableClipError as e:
            # All retries exhausted
            logger.error(
                f"Clip download failed after {MAX_RETRY_ATTEMPTS} attempts",
                extra={
                    "event_type": "clip_download_failed_all_retries",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "attempts_made": MAX_RETRY_ATTEMPTS,
                    "final_error": str(e)
                }
            )
            return None

        except NonRetriableClipError as e:
            # Non-retriable error - immediate failure
            logger.warning(
                f"Clip download failed (non-retriable): {e}",
                extra={
                    "event_type": "clip_download_non_retriable_error",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            return None

        except Exception as e:
            # Unexpected error
            logger.error(
                f"Clip download failed unexpectedly: {type(e).__name__}",
                extra={
                    "event_type": "clip_download_unexpected_error",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "event_id": event_id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            # Clean up any partial file
            if output_path.exists():
                try:
                    output_path.unlink()
                except Exception:
                    pass
            return None


# Singleton instance
_clip_service: Optional[ClipService] = None


def get_clip_service() -> ClipService:
    """
    Get the singleton ClipService instance.

    Creates the instance on first call, using the ProtectService singleton.

    Returns:
        ClipService singleton instance
    """
    global _clip_service
    if _clip_service is None:
        from app.services.protect_service import get_protect_service
        _clip_service = ClipService(get_protect_service())
    return _clip_service


def reset_clip_service() -> None:
    """
    Reset the singleton instance (useful for testing).

    Stops the scheduler if running before resetting.
    """
    global _clip_service
    if _clip_service is not None:
        _clip_service._stop_scheduler()
    _clip_service = None
