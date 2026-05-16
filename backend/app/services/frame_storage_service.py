"""
Frame Storage Service for AI Analysis Frames

Story P8-2.1: Store All Analysis Frames During Event Processing

This service handles:
- Saving extracted frames to filesystem as JPEG files
- Creating EventFrame database records with metadata
- Deleting frame files when events are cleaned up
- Managing frame directories (data/frames/{event_id}/)

Storage pattern follows the existing thumbnail pattern:
- Frames stored in data/frames/{event_id}/frame_NNN.jpg
- JPEG quality 85, max width 1280px
- ~50KB per frame typical size

Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import io
import logging
from app.core.decorators import singleton
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.event_frame import EventFrame

logger = logging.getLogger(__name__)

# Frame storage configuration
FRAME_STORAGE_BASE_DIR = "data/frames"
FRAME_JPEG_QUALITY = 85
FRAME_MAX_WIDTH = 1280


@singleton
class FrameStorageService:
    """
    Service for storing and managing AI analysis frames.

    Stores frames as JPEG files on disk with metadata tracked in the database.
    Follows the same pattern as thumbnail storage but organized by event.

    Attributes:
        base_dir: Base directory for frame storage (relative to backend root)
        jpeg_quality: JPEG encoding quality (0-100)
        max_width: Maximum frame width in pixels
    """

    def __init__(self, session_factory=None):
        """
        Initialize FrameStorageService.

        Args:
            session_factory: Optional SQLAlchemy session factory (for testing).
                           Defaults to SessionLocal from app.core.database.
        """
        self.session_factory = session_factory or SessionLocal
        self.base_dir = Path(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        ) / FRAME_STORAGE_BASE_DIR
        self.jpeg_quality = FRAME_JPEG_QUALITY
        self.max_width = FRAME_MAX_WIDTH

        logger.info(
            "FrameStorageService initialized",
            extra={
                "event_type": "frame_storage_init",
                "base_dir": str(self.base_dir),
                "jpeg_quality": self.jpeg_quality,
                "max_width": self.max_width
            }
        )

    def _get_event_frame_dir(self, event_id: str) -> Path:
        """
        Get the directory path for storing frames for an event.

        Args:
            event_id: UUID of the event

        Returns:
            Path to the event's frame directory
        """
        return self.base_dir / event_id

    def _get_relative_frame_path(self, event_id: str, frame_number: int) -> str:
        """
        Get the relative path for a frame file (for database storage).

        Args:
            event_id: UUID of the event
            frame_number: 1-indexed frame number

        Returns:
            Relative path string (e.g., "frames/{event_id}/frame_001.jpg")
        """
        return f"frames/{event_id}/frame_{frame_number:03d}.jpg"

    def _resize_and_encode_frame(self, frame_bytes: bytes) -> Tuple[bytes, int, int]:
        """
        Resize frame if needed and encode as JPEG.

        Args:
            frame_bytes: Raw JPEG bytes from frame extractor

        Returns:
            Tuple of (encoded_bytes, width, height)
        """
        # Decode JPEG to PIL Image
        img = Image.open(io.BytesIO(frame_bytes))
        width, height = img.size

        # Resize if needed (maintain aspect ratio)
        if width > self.max_width:
            ratio = self.max_width / width
            new_width = self.max_width
            new_height = int(height * ratio)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            width, height = new_width, new_height

        # Encode as JPEG
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=self.jpeg_quality)
        encoded_bytes = buffer.getvalue()

        return encoded_bytes, width, height

    async def save_frames(
        self,
        event_id: str,
        frames: List[bytes],
        timestamps_ms: List[int],
        db: Optional[Session] = None
    ) -> List[EventFrame]:
        """
        Save extracted frames to filesystem and create database records.

        Args:
            event_id: UUID of the event
            frames: List of JPEG-encoded frame bytes
            timestamps_ms: List of timestamps in milliseconds from video start
            db: Optional database session. If not provided, creates a new one.

        Returns:
            List of created EventFrame records

        AC1.1: Given multi-frame analysis, when frames are extracted,
               then all frames saved to data/frames/{event_id}/
        AC1.2: Given frame storage, when frames saved,
               then EventFrame records created in database
        AC1.3: Given frame metadata, when stored,
               then includes frame_number, path, timestamp_offset_ms
        """
        if not frames:
            logger.debug(
                "No frames to save",
                extra={
                    "event_type": "frame_storage_empty",
                    "event_id": event_id
                }
            )
            return []

        # Ensure timestamps list matches frames list
        if len(timestamps_ms) != len(frames):
            logger.warning(
                f"Timestamps count ({len(timestamps_ms)}) doesn't match frames count ({len(frames)})",
                extra={
                    "event_type": "frame_storage_mismatch",
                    "event_id": event_id,
                    "frame_count": len(frames),
                    "timestamp_count": len(timestamps_ms)
                }
            )
            # Pad timestamps with 0 if needed
            while len(timestamps_ms) < len(frames):
                timestamps_ms.append(0)

        # Create event frame directory
        frame_dir = self._get_event_frame_dir(event_id)
        frame_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Saving {len(frames)} frames for event {event_id}",
            extra={
                "event_type": "frame_storage_start",
                "event_id": event_id,
                "frame_count": len(frames),
                "frame_dir": str(frame_dir)
            }
        )

        # Track whether we created the session
        session_created = False
        if db is None:
            db = self.session_factory()
            session_created = True

        try:
            event_frames: List[EventFrame] = []
            total_bytes = 0

            for i, (frame_bytes, timestamp_ms) in enumerate(zip(frames, timestamps_ms)):
                frame_number = i + 1  # 1-indexed

                # Process and encode frame
                encoded_bytes, width, height = self._resize_and_encode_frame(frame_bytes)
                file_size = len(encoded_bytes)
                total_bytes += file_size

                # Write frame to disk
                relative_path = self._get_relative_frame_path(event_id, frame_number)
                file_path = self.base_dir.parent / relative_path
                file_path.write_bytes(encoded_bytes)

                # Create database record
                event_frame = EventFrame(
                    event_id=event_id,
                    frame_number=frame_number,
                    frame_path=relative_path,
                    timestamp_offset_ms=timestamp_ms,
                    width=width,
                    height=height,
                    file_size_bytes=file_size,
                    created_at=datetime.now(timezone.utc)
                )
                db.add(event_frame)
                event_frames.append(event_frame)

                logger.debug(
                    f"Saved frame {frame_number} for event {event_id}",
                    extra={
                        "event_type": "frame_saved",
                        "event_id": event_id,
                        "frame_number": frame_number,
                        "file_path": relative_path,
                        "file_size_bytes": file_size,
                        "width": width,
                        "height": height,
                        "timestamp_offset_ms": timestamp_ms
                    }
                )

            db.commit()

            logger.info(
                f"Saved {len(event_frames)} frames for event {event_id}",
                extra={
                    "event_type": "frame_storage_complete",
                    "event_id": event_id,
                    "frame_count": len(event_frames),
                    "total_bytes": total_bytes
                }
            )

            return event_frames

        except Exception as e:
            logger.error(
                f"Error saving frames for event {event_id}: {e}",
                extra={
                    "event_type": "frame_storage_error",
                    "event_id": event_id,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            db.rollback()
            # Clean up any partial writes
            if frame_dir.exists():
                shutil.rmtree(frame_dir, ignore_errors=True)
            raise

        finally:
            if session_created:
                db.close()

    def delete_frames_sync(self, event_id: str) -> int:
        """
        Synchronously delete all frame files for an event.

        Called during event cleanup to remove frame files from disk.
        Database records are deleted via CASCADE when event is deleted.

        Args:
            event_id: UUID of the event

        Returns:
            Number of files deleted

        AC1.4: Given event deletion, when cascade occurs,
               then frame files and records deleted
        AC1.5: Given retention policy, when cleanup runs,
               then old frames deleted with events
        """
        frame_dir = self._get_event_frame_dir(event_id)

        if not frame_dir.exists():
            logger.debug(
                f"Frame directory does not exist for event {event_id}",
                extra={
                    "event_type": "frame_delete_not_found",
                    "event_id": event_id
                }
            )
            return 0

        try:
            # Count files before deletion
            files_deleted = sum(1 for _ in frame_dir.glob("*.jpg"))

            # Remove the entire directory
            shutil.rmtree(frame_dir)

            logger.info(
                f"Deleted {files_deleted} frames for event {event_id}",
                extra={
                    "event_type": "frame_delete_complete",
                    "event_id": event_id,
                    "files_deleted": files_deleted
                }
            )

            return files_deleted

        except Exception as e:
            logger.error(
                f"Error deleting frames for event {event_id}: {e}",
                extra={
                    "event_type": "frame_delete_error",
                    "event_id": event_id,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            return 0

    async def delete_frames(self, event_id: str) -> int:
        """
        Async wrapper for delete_frames_sync.

        Args:
            event_id: UUID of the event

        Returns:
            Number of files deleted
        """
        return self.delete_frames_sync(event_id)

    def get_frames_size(self) -> float:
        """
        Get total size of frames directory in megabytes.

        Returns:
            Frames directory size in MB
        """
        if not self.base_dir.exists():
            return 0.0

        total_size_bytes = 0
        file_count = 0

        try:
            for dirpath, _, filenames in os.walk(self.base_dir):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size_bytes += os.path.getsize(filepath)
                        file_count += 1
                    except Exception:
                        pass

            size_mb = total_size_bytes / (1024 * 1024)

            logger.debug(
                f"Frames size: {size_mb:.2f} MB ({file_count} files)",
                extra={
                    "event_type": "frames_size_calculated",
                    "size_mb": size_mb,
                    "file_count": file_count
                }
            )

            return round(size_mb, 2)

        except Exception as e:
            logger.error(f"Error calculating frames size: {e}")
            return 0.0


# Backward compatible thin getter (delegates to @singleton decorator)
def get_frame_storage_service() -> FrameStorageService:
    """
    Get the global FrameStorageService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer FrameStorageService() directly.
    """
    return FrameStorageService()


def reset_frame_storage_service() -> None:
    """Reset the global FrameStorageService instance (for testing)."""
    FrameStorageService._reset_instance()
    return _frame_storage_service


def reset_frame_storage_service() -> None:
    """Reset the global FrameStorageService instance (for testing)."""
    FrameStorageService._reset_instance()
