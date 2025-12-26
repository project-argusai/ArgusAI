"""
UniFi Protect Snapshot Service (Story P2-3.2)

Handles snapshot retrieval from Protect cameras with image processing,
retry logic, and concurrency limiting.

Snapshot Flow:
    Event passes filtering (Story P2-3.1)
            ↓
    SnapshotService.get_snapshot(controller_id, camera_id, timestamp)
            ↓
    1. Acquire controller semaphore (limit: 3 concurrent)
            ↓
    2. Call uiprotect: await client.get_camera_snapshot()
            ↓ (retry once on failure)
    3. Resize to max 1920x1080
            ↓
    4. Generate thumbnail (320x180)
            ↓
    5. Convert to base64
            ↓
    6. Return SnapshotResult(base64, thumbnail_path)
            ↓
    7. Pass to AI pipeline (Story P2-3.3)
"""
import asyncio
import base64
import io
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from PIL import Image

# Note: get_protect_service is imported lazily to avoid circular imports
# See _fetch_snapshot_with_retry method

logger = logging.getLogger(__name__)

# Snapshot retrieval timeout in seconds (AC1, AC12 - NFR4)
SNAPSHOT_TIMEOUT_SECONDS = 1.0

# Retry delay in seconds (AC8)
RETRY_DELAY_SECONDS = 0.5

# Maximum concurrent snapshots per controller (AC11)
MAX_CONCURRENT_SNAPSHOTS = 3

# Semaphore acquisition timeout in seconds
SEMAPHORE_TIMEOUT_SECONDS = 5.0

# Image dimensions for AI processing (AC4)
AI_MAX_WIDTH = 1920
AI_MAX_HEIGHT = 1080

# Thumbnail dimensions (AC6)
THUMBNAIL_WIDTH = 320
THUMBNAIL_HEIGHT = 180

# Default thumbnail storage path
DEFAULT_THUMBNAIL_PATH = "data/thumbnails"


@dataclass
class SnapshotResult:
    """
    Result of snapshot retrieval and processing (Story P2-3.2).

    Attributes:
        image_base64: Base64-encoded JPEG for AI API submission
        thumbnail_path: Path to saved thumbnail for event record
        width: Final image width after resizing
        height: Final image height after resizing
        camera_id: Camera that captured snapshot
        timestamp: When snapshot was taken (UTC)
    """
    image_base64: str
    thumbnail_path: str
    width: int
    height: int
    camera_id: str
    timestamp: datetime


class SnapshotService:
    """
    Service for retrieving and processing snapshots from Protect cameras (Story P2-3.2).

    Responsibilities:
    - Fetch snapshots from Protect API with timeout (AC1, AC12)
    - Resize images for AI processing (AC4)
    - Generate and save thumbnails (AC6)
    - Convert to base64 for AI API (AC5)
    - Retry on failure (AC8)
    - Track failure metrics (AC10)
    - Limit concurrent snapshots per controller (AC11)

    Attributes:
        _controller_semaphores: Per-controller semaphores for concurrency limiting
        _thumbnail_path: Path to store thumbnails
        _snapshot_failures_total: Counter for monitoring failures
        _snapshot_success_total: Counter for monitoring successes
    """

    def __init__(self, thumbnail_path: str = DEFAULT_THUMBNAIL_PATH):
        """
        Initialize snapshot service.

        Args:
            thumbnail_path: Directory to store thumbnails
        """
        self._controller_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._thumbnail_path = thumbnail_path
        self._snapshot_failures_total = 0
        self._snapshot_success_total = 0

        # Ensure thumbnail directory exists
        os.makedirs(thumbnail_path, exist_ok=True)

    async def get_snapshot(
        self,
        controller_id: str,
        protect_camera_id: str,
        camera_id: str,
        camera_name: str,
        timestamp: Optional[datetime] = None
    ) -> Optional[SnapshotResult]:
        """
        Get snapshot from Protect camera and process it (Story P2-3.2 AC1).

        Acquires semaphore, fetches snapshot with retry, processes image,
        and returns result for AI pipeline.

        Args:
            controller_id: Controller UUID
            protect_camera_id: Native Protect camera ID
            camera_id: Internal camera UUID for result
            camera_name: Camera name for logging
            timestamp: Optional timestamp for event-time snapshot

        Returns:
            SnapshotResult with processed image, or None on failure
        """
        # Get or create semaphore for this controller (AC11)
        semaphore = self._get_controller_semaphore(controller_id)

        try:
            # Acquire semaphore with timeout (AC11)
            try:
                await asyncio.wait_for(
                    semaphore.acquire(),
                    timeout=SEMAPHORE_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Semaphore acquisition timeout for camera '{camera_name}'",
                    extra={
                        "event_type": "snapshot_semaphore_timeout",
                        "controller_id": controller_id,
                        "camera_id": camera_id,
                        "camera_name": camera_name
                    }
                )
                self._snapshot_failures_total += 1
                return None

            try:
                # Fetch snapshot with retry (AC8, AC9)
                snapshot_bytes = await self._fetch_snapshot_with_retry(
                    controller_id,
                    protect_camera_id,
                    camera_name,
                    timestamp
                )

                if snapshot_bytes is None:
                    return None

                # Process image: resize and generate thumbnail (AC4, AC5, AC6)
                result = await self._process_snapshot(
                    snapshot_bytes,
                    camera_id,
                    camera_name,
                    timestamp or datetime.now(timezone.utc)
                )

                if result:
                    self._snapshot_success_total += 1
                    logger.info(
                        f"Snapshot processed successfully for camera '{camera_name}'",
                        extra={
                            "event_type": "snapshot_success",
                            "controller_id": controller_id,
                            "camera_id": camera_id,
                            "camera_name": camera_name,
                            "width": result.width,
                            "height": result.height,
                            "thumbnail_path": result.thumbnail_path
                        }
                    )

                return result

            finally:
                # Always release semaphore
                semaphore.release()

        except Exception as e:
            logger.error(
                f"Unexpected error in snapshot retrieval for camera '{camera_name}': {e}",
                extra={
                    "event_type": "snapshot_unexpected_error",
                    "controller_id": controller_id,
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            self._snapshot_failures_total += 1
            return None

    def _get_controller_semaphore(self, controller_id: str) -> asyncio.Semaphore:
        """
        Get or create semaphore for controller (Story P2-3.2 AC11).

        Args:
            controller_id: Controller UUID

        Returns:
            Semaphore limited to MAX_CONCURRENT_SNAPSHOTS
        """
        if controller_id not in self._controller_semaphores:
            self._controller_semaphores[controller_id] = asyncio.Semaphore(
                MAX_CONCURRENT_SNAPSHOTS
            )
        return self._controller_semaphores[controller_id]

    async def _fetch_snapshot_with_retry(
        self,
        controller_id: str,
        protect_camera_id: str,
        camera_name: str,
        timestamp: Optional[datetime] = None
    ) -> Optional[bytes]:
        """
        Fetch snapshot with single retry on failure (Story P2-3.2 AC8, AC9).

        Args:
            controller_id: Controller UUID
            protect_camera_id: Native Protect camera ID
            camera_name: Camera name for logging
            timestamp: Optional event timestamp

        Returns:
            JPEG bytes or None on failure
        """
        # Lazy import to avoid circular imports
        from app.services.protect_service import get_protect_service
        protect_service = get_protect_service()

        for attempt in range(2):  # Initial + 1 retry (AC8)
            try:
                # Fetch with timeout (AC1, AC12)
                snapshot_bytes = await asyncio.wait_for(
                    protect_service.get_camera_snapshot(
                        controller_id=controller_id,
                        protect_camera_id=protect_camera_id,
                        width=None,  # Full resolution (AC4)
                        height=None
                    ),
                    timeout=SNAPSHOT_TIMEOUT_SECONDS
                )

                if snapshot_bytes:
                    logger.debug(
                        f"Snapshot fetched for camera '{camera_name}' (attempt {attempt + 1})",
                        extra={
                            "event_type": "snapshot_fetched",
                            "controller_id": controller_id,
                            "camera_name": camera_name,
                            "attempt": attempt + 1,
                            "size_bytes": len(snapshot_bytes)
                        }
                    )
                    return snapshot_bytes

                # Empty response, try again
                logger.warning(
                    f"Empty snapshot response for camera '{camera_name}' (attempt {attempt + 1})",
                    extra={
                        "event_type": "snapshot_empty",
                        "controller_id": controller_id,
                        "camera_name": camera_name,
                        "attempt": attempt + 1
                    }
                )

            except asyncio.TimeoutError:
                logger.warning(
                    f"Snapshot timeout for camera '{camera_name}' (attempt {attempt + 1})",
                    extra={
                        "event_type": "snapshot_timeout",
                        "controller_id": controller_id,
                        "camera_name": camera_name,
                        "attempt": attempt + 1,
                        "timeout_seconds": SNAPSHOT_TIMEOUT_SECONDS
                    }
                )

            except Exception as e:
                logger.warning(
                    f"Snapshot error for camera '{camera_name}' (attempt {attempt + 1}): {e}",
                    extra={
                        "event_type": "snapshot_fetch_error",
                        "controller_id": controller_id,
                        "camera_name": camera_name,
                        "attempt": attempt + 1,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )

            # Wait before retry (AC8)
            if attempt == 0:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        # Both attempts failed (AC9, AC10)
        logger.error(
            f"Snapshot failed after retries for camera '{camera_name}'",
            extra={
                "event_type": "snapshot_failed_after_retry",
                "controller_id": controller_id,
                "camera_name": camera_name
            }
        )
        self._snapshot_failures_total += 1
        return None

    async def _process_snapshot(
        self,
        image_bytes: bytes,
        camera_id: str,
        camera_name: str,
        timestamp: datetime
    ) -> Optional[SnapshotResult]:
        """
        Process snapshot: resize, generate thumbnail, convert to base64 (Story P2-3.2 AC4-AC7).

        Args:
            image_bytes: Raw JPEG bytes from Protect API
            camera_id: Internal camera UUID
            camera_name: Camera name for logging
            timestamp: Event timestamp

        Returns:
            SnapshotResult or None on processing error
        """
        try:
            # Load image (AC3 - JPEG format)
            image = Image.open(io.BytesIO(image_bytes))

            # Resize for AI processing (AC4)
            resized_image = self._resize_for_ai(image)
            resized_width, resized_height = resized_image.size

            # Generate thumbnail (AC6)
            thumbnail_path = await self._generate_thumbnail(
                image,
                camera_id,
                timestamp
            )

            # Convert resized image to base64 (AC5)
            image_base64 = self._to_base64(resized_image)

            # Clean up - image objects will be garbage collected (AC7)
            # Explicit del to help garbage collector
            del image
            del resized_image

            return SnapshotResult(
                image_base64=image_base64,
                thumbnail_path=thumbnail_path,
                width=resized_width,
                height=resized_height,
                camera_id=camera_id,
                timestamp=timestamp
            )

        except Exception as e:
            logger.error(
                f"Image processing error for camera '{camera_name}': {e}",
                extra={
                    "event_type": "snapshot_processing_error",
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            self._snapshot_failures_total += 1
            return None

    def _resize_for_ai(
        self,
        image: Image.Image,
        max_width: int = AI_MAX_WIDTH,
        max_height: int = AI_MAX_HEIGHT
    ) -> Image.Image:
        """
        Resize image for AI processing while maintaining aspect ratio (Story P2-3.2 AC4).

        Args:
            image: PIL Image object
            max_width: Maximum width (default 1920)
            max_height: Maximum height (default 1080)

        Returns:
            Resized PIL Image
        """
        original_width, original_height = image.size

        # Only resize if larger than max dimensions
        if original_width <= max_width and original_height <= max_height:
            return image.copy()

        # Calculate scaling factor to fit within bounds
        width_ratio = max_width / original_width
        height_ratio = max_height / original_height
        scale_factor = min(width_ratio, height_ratio)

        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)

        # Use LANCZOS for high-quality downscaling
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    async def _generate_thumbnail(
        self,
        image: Image.Image,
        camera_id: str,
        timestamp: datetime,
        width: int = THUMBNAIL_WIDTH,
        height: int = THUMBNAIL_HEIGHT
    ) -> str:
        """
        Generate and save thumbnail for event record (Story P2-3.2 AC6).

        Args:
            image: PIL Image object
            camera_id: Camera UUID for filename
            timestamp: Event timestamp for filename
            width: Thumbnail width (default 320)
            height: Thumbnail height (default 180)

        Returns:
            API URL path to thumbnail (e.g., /api/v1/thumbnails/2025-12-01/filename.jpg)
        """
        # Create thumbnail maintaining aspect ratio
        thumbnail = image.copy()
        thumbnail.thumbnail((width, height), Image.Resampling.LANCZOS)

        # Generate unique filename with date-based directory (consistent with RTSP events)
        date_str = timestamp.strftime("%Y-%m-%d")
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{camera_id}_{timestamp_str}_{unique_id}.jpg"

        # Create date-based subdirectory
        date_dir = os.path.join(self._thumbnail_path, date_str)
        os.makedirs(date_dir, exist_ok=True)

        filepath = os.path.join(date_dir, filename)

        # Save as JPEG
        thumbnail.save(filepath, "JPEG", quality=85)

        # Return API URL path (not filesystem path) for frontend compatibility
        api_url_path = f"/api/v1/thumbnails/{date_str}/{filename}"

        logger.debug(
            f"Thumbnail saved: {filepath}",
            extra={
                "event_type": "thumbnail_saved",
                "camera_id": camera_id,
                "filepath": filepath,
                "api_url_path": api_url_path,
                "width": thumbnail.width,
                "height": thumbnail.height
            }
        )

        return api_url_path

    def _to_base64(self, image: Image.Image) -> str:
        """
        Convert PIL Image to base64-encoded JPEG string (Story P2-3.2 AC5).

        Args:
            image: PIL Image object

        Returns:
            Base64-encoded string
        """
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode("utf-8")

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get snapshot service metrics for monitoring (Story P2-3.2 AC10).

        Returns:
            Dictionary with success/failure counts
        """
        return {
            "snapshot_success_total": self._snapshot_success_total,
            "snapshot_failures_total": self._snapshot_failures_total,
            "active_semaphores": len(self._controller_semaphores)
        }

    def reset_metrics(self) -> None:
        """Reset metrics counters (useful for testing)."""
        self._snapshot_failures_total = 0
        self._snapshot_success_total = 0


# Global singleton instance
_snapshot_service: Optional[SnapshotService] = None


def get_snapshot_service() -> SnapshotService:
    """Get the global SnapshotService singleton instance."""
    global _snapshot_service
    if _snapshot_service is None:
        _snapshot_service = SnapshotService()
    return _snapshot_service


# =============================================================================
# Story P11-2.6: Notification Thumbnail Optimization
# =============================================================================

# Notification image constraints
NOTIFICATION_MAX_DIMENSION = 1024  # Max width/height for notification images
NOTIFICATION_MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB max for push notifications
NOTIFICATION_JPEG_QUALITY = 80  # Initial JPEG quality
NOTIFICATION_MIN_QUALITY = 20  # Minimum quality before giving up

# Optimized thumbnail cache directory suffix
NOTIFICATION_CACHE_SUFFIX = "_notification"


def optimize_thumbnail_for_notification(
    thumbnail_path: str,
    cache_dir: str = DEFAULT_THUMBNAIL_PATH,
) -> Optional[str]:
    """
    Optimize a thumbnail image for push notification display (Story P11-2.6).

    Resizes large images to max 1024x1024 and compresses to under 1MB.
    Results are cached to avoid re-processing.

    Args:
        thumbnail_path: Path to the original thumbnail (absolute or relative API path)
        cache_dir: Base directory for thumbnail storage

    Returns:
        Path to optimized thumbnail, or None if optimization fails.
        Returns original path if already optimized or under limits.

    Note:
        - iOS recommends <5MB attachments, but 1MB is safer for bandwidth
        - Android FCM BigPicture works best with images under 1MB
        - Cached files are named with _notification suffix
    """
    import os
    from pathlib import Path

    try:
        # Normalize path - handle both API paths and filesystem paths
        if thumbnail_path.startswith('/api/v1/thumbnails/'):
            relative_path = thumbnail_path[len('/api/v1/thumbnails/'):]
        else:
            relative_path = thumbnail_path

        # Build absolute path
        original_file = os.path.join(cache_dir, relative_path)

        if not os.path.exists(original_file):
            logger.warning(
                f"Original thumbnail not found for optimization: {original_file}",
                extra={"thumbnail_path": thumbnail_path}
            )
            return None

        # Check if cached version exists
        original_path = Path(original_file)
        cached_name = f"{original_path.stem}{NOTIFICATION_CACHE_SUFFIX}{original_path.suffix}"
        cached_file = original_path.parent / cached_name

        if cached_file.exists():
            # Return cached version
            logger.debug(
                "Using cached notification thumbnail",
                extra={"cached_file": str(cached_file)}
            )
            # Return relative path in same format as input
            if thumbnail_path.startswith('/api/v1/thumbnails/'):
                return f"/api/v1/thumbnails/{os.path.dirname(relative_path)}/{cached_name}"
            return str(cached_file)

        # Check if original is already small enough
        original_size = os.path.getsize(original_file)
        with Image.open(original_file) as img:
            width, height = img.size

            # If already under limits, return original
            if (width <= NOTIFICATION_MAX_DIMENSION and
                height <= NOTIFICATION_MAX_DIMENSION and
                original_size <= NOTIFICATION_MAX_FILE_SIZE):
                logger.debug(
                    "Thumbnail already optimized",
                    extra={
                        "width": width,
                        "height": height,
                        "size_bytes": original_size,
                    }
                )
                return thumbnail_path

            # Need to optimize
            logger.debug(
                "Optimizing thumbnail for notification",
                extra={
                    "original_width": width,
                    "original_height": height,
                    "original_size": original_size,
                }
            )

            # Resize if too large
            if width > NOTIFICATION_MAX_DIMENSION or height > NOTIFICATION_MAX_DIMENSION:
                img.thumbnail(
                    (NOTIFICATION_MAX_DIMENSION, NOTIFICATION_MAX_DIMENSION),
                    Image.Resampling.LANCZOS
                )

            # Convert to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')

            # Save with compression, reducing quality if needed
            quality = NOTIFICATION_JPEG_QUALITY

            while quality >= NOTIFICATION_MIN_QUALITY:
                # Save to buffer first to check size
                buffer = io.BytesIO()
                img.save(buffer, "JPEG", quality=quality, optimize=True)
                compressed_size = buffer.tell()

                if compressed_size <= NOTIFICATION_MAX_FILE_SIZE:
                    # Size is good, save to file
                    buffer.seek(0)
                    with open(cached_file, 'wb') as f:
                        f.write(buffer.read())

                    logger.info(
                        "Notification thumbnail optimized",
                        extra={
                            "cached_file": str(cached_file),
                            "original_size": original_size,
                            "optimized_size": compressed_size,
                            "quality": quality,
                            "width": img.width,
                            "height": img.height,
                        }
                    )

                    # Return path in same format as input
                    if thumbnail_path.startswith('/api/v1/thumbnails/'):
                        return f"/api/v1/thumbnails/{os.path.dirname(relative_path)}/{cached_name}"
                    return str(cached_file)

                # Still too large, reduce quality
                quality -= 10

            # Couldn't get under size limit even at minimum quality
            logger.warning(
                "Could not optimize thumbnail under size limit",
                extra={
                    "thumbnail_path": thumbnail_path,
                    "min_size": compressed_size,
                    "target_size": NOTIFICATION_MAX_FILE_SIZE,
                }
            )
            # Return original as fallback
            return thumbnail_path

    except Exception as e:
        logger.error(
            f"Failed to optimize thumbnail for notification: {e}",
            extra={"thumbnail_path": thumbnail_path},
            exc_info=True
        )
        # Return original as fallback
        return thumbnail_path


def cleanup_notification_cache(cache_dir: str = DEFAULT_THUMBNAIL_PATH) -> int:
    """
    Clean up notification thumbnail cache files (Story P11-2.6).

    Should be called during retention cleanup to remove orphaned cache files.

    Args:
        cache_dir: Base directory for thumbnail storage

    Returns:
        Number of cache files deleted
    """
    import os
    from pathlib import Path

    deleted_count = 0

    try:
        cache_path = Path(cache_dir)
        if not cache_path.exists():
            return 0

        # Find all notification cache files
        for cache_file in cache_path.rglob(f"*{NOTIFICATION_CACHE_SUFFIX}*"):
            if cache_file.is_file():
                # Check if original exists
                original_name = cache_file.name.replace(NOTIFICATION_CACHE_SUFFIX, "")
                original_file = cache_file.parent / original_name

                if not original_file.exists():
                    # Original was deleted, clean up cache
                    try:
                        cache_file.unlink()
                        deleted_count += 1
                        logger.debug(
                            "Deleted orphaned notification cache file",
                            extra={"file": str(cache_file)}
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete cache file {cache_file}: {e}"
                        )

        if deleted_count > 0:
            logger.info(
                f"Cleaned up {deleted_count} notification cache files",
                extra={"cache_dir": cache_dir, "deleted_count": deleted_count}
            )

        return deleted_count

    except Exception as e:
        logger.error(
            f"Error cleaning up notification cache: {e}",
            exc_info=True
        )
        return deleted_count
