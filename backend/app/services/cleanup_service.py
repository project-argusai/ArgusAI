"""
Data Retention and Cleanup Service

This module implements automated and manual cleanup of old events based on retention
policies, along with storage monitoring functionality.

Features:
    - Batch deletion of old events (max 1000 per batch)
    - Thumbnail file cleanup with graceful error handling
    - Database and thumbnail size monitoring
    - Transaction-based deletion for data integrity
    - Comprehensive logging of deletion statistics

Usage:
    cleanup_service = CleanupService()
    stats = await cleanup_service.cleanup_old_events(retention_days=30)

# Migrated to @singleton as part of #450 (Lightweight DI Container).
"""
import os
import logging
from app.core.decorators import singleton
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.event import Event
from app.core.database import SessionLocal
from app.services.frame_storage_service import get_frame_storage_service

logger = logging.getLogger(__name__)


@singleton
class CleanupService:
    """
    Service for managing data retention and cleanup operations

    Handles:
        - Batch deletion of old events based on retention policy
        - Thumbnail file cleanup with error handling
        - Database size calculation (SQLite PRAGMA queries)
        - Thumbnail directory size calculation
        - Deletion statistics tracking
    """

    def __init__(self, session_factory=None):
        """
        Initialize CleanupService

        Args:
            session_factory: Optional SQLAlchemy session factory (for testing).
                           Defaults to SessionLocal from app.core.database.
        """
        self.session_factory = session_factory or SessionLocal
        self.thumbnail_base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data',
            'thumbnails'
        )
        # Story P8-3.2: Video storage directory for cleanup
        self.video_base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data',
            'videos'
        )
        logger.info(f"CleanupService initialized with thumbnail dir: {self.thumbnail_base_dir}, video dir: {self.video_base_dir}")

    async def cleanup_old_events(
        self,
        retention_days: int,
        batch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Clean up events older than retention period

        Deletes events in batches with transaction safety. Also removes associated
        thumbnail files from filesystem. Continues until all eligible events are deleted.

        Args:
            retention_days: Number of days to retain events (events older will be deleted)
            batch_size: Maximum number of events to delete per batch (default 1000)

        Returns:
            Dict with deletion statistics:
            {
                "events_deleted": int,
                "thumbnails_deleted": int,
                "thumbnails_failed": int,
                "space_freed_mb": float,
                "batches_processed": int
            }

        Raises:
            None - All errors are caught and logged, operation continues
        """
        logger.info(f"Starting cleanup: retention_days={retention_days}, batch_size={batch_size}")

        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Statistics tracking
        total_events_deleted = 0
        total_thumbnails_deleted = 0
        total_thumbnails_failed = 0
        total_frames_deleted = 0
        total_space_freed = 0.0
        batches_processed = 0

        # Get frame storage service for cleanup
        frame_storage_service = get_frame_storage_service()

        # Batch deletion loop
        while True:
            db = self.session_factory()
            try:
                # Query batch of events to delete (based on event timestamp, not record creation)
                events_batch = db.query(Event.id, Event.thumbnail_path).filter(
                    Event.timestamp < cutoff_date
                ).limit(batch_size).all()

                if not events_batch:
                    logger.info("No more events to delete")
                    break

                batch_event_ids = [event.id for event in events_batch]
                batch_size_actual = len(batch_event_ids)

                logger.info(f"Processing batch {batches_processed + 1}: {batch_size_actual} events")

                # Delete thumbnail files first (before database records)
                thumbnail_stats = self._delete_thumbnails(events_batch)
                total_thumbnails_deleted += thumbnail_stats["deleted"]
                total_thumbnails_failed += thumbnail_stats["failed"]
                total_space_freed += thumbnail_stats["space_freed_mb"]

                # Story P8-2.1 AC1.5: Delete frame files for each event in batch
                for event in events_batch:
                    try:
                        frames_deleted = frame_storage_service.delete_frames_sync(event.id)
                        total_frames_deleted += frames_deleted
                    except Exception as frame_e:
                        logger.warning(
                            f"Failed to delete frames for event {event.id}: {frame_e}",
                            extra={
                                "event_type": "frame_cleanup_error",
                                "event_id": event.id,
                                "error": str(frame_e)
                            }
                        )

                # Delete event records (cascade deletes ai_usage and event_frames via foreign key)
                db.query(Event).filter(Event.id.in_(batch_event_ids)).delete(
                    synchronize_session=False
                )
                db.commit()

                total_events_deleted += batch_size_actual
                batches_processed += 1

                logger.info(
                    f"Batch {batches_processed} complete: {batch_size_actual} events deleted",
                    extra={
                        "batch_number": batches_processed,
                        "events_in_batch": batch_size_actual,
                        "thumbnails_deleted": thumbnail_stats["deleted"],
                        "thumbnails_failed": thumbnail_stats["failed"],
                        "frames_deleted": total_frames_deleted
                    }
                )

            except Exception as e:
                logger.error(
                    f"Error during batch deletion (batch {batches_processed + 1}): {e}",
                    exc_info=True
                )
                db.rollback()
                # Stop processing on database errors to prevent data inconsistency
                break
            finally:
                db.close()

        # Final statistics
        stats = {
            "events_deleted": total_events_deleted,
            "thumbnails_deleted": total_thumbnails_deleted,
            "thumbnails_failed": total_thumbnails_failed,
            "frames_deleted": total_frames_deleted,  # Story P8-2.1 AC1.5
            "space_freed_mb": round(total_space_freed, 2),
            "batches_processed": batches_processed
        }

        logger.info(
            f"Cleanup complete: {total_events_deleted} events deleted, {total_frames_deleted} frames deleted across {batches_processed} batches",
            extra=stats
        )

        return stats

    def _delete_thumbnails(self, events_batch) -> Dict[str, Any]:
        """
        Delete thumbnail files for a batch of events

        Handles missing files gracefully (warns but continues).

        Args:
            events_batch: List of (id, thumbnail_path) tuples

        Returns:
            Dict with thumbnail deletion stats:
            {
                "deleted": int,
                "failed": int,
                "space_freed_mb": float
            }
        """
        deleted = 0
        failed = 0
        space_freed_bytes = 0

        for event in events_batch:
            if not event.thumbnail_path:
                continue

            thumbnail_path = event.thumbnail_path

            # Handle both absolute and relative paths
            if not os.path.isabs(thumbnail_path):
                # If relative path starts with "thumbnails/", strip prefix and use base dir
                if thumbnail_path.startswith("thumbnails/"):
                    # Strip "thumbnails/" prefix and join with thumbnail_base_dir
                    relative_to_thumbnails = thumbnail_path[len("thumbnails/"):]
                    thumbnail_path = os.path.join(
                        self.thumbnail_base_dir,
                        relative_to_thumbnails
                    )
                else:
                    # Legacy: Use backend root directory
                    thumbnail_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                        thumbnail_path
                    )

            try:
                if os.path.exists(thumbnail_path):
                    # Get file size before deletion
                    file_size = os.path.getsize(thumbnail_path)
                    os.remove(thumbnail_path)
                    space_freed_bytes += file_size
                    deleted += 1
                    logger.debug(f"Deleted thumbnail: {thumbnail_path}")
                else:
                    logger.warning(f"Thumbnail file not found: {thumbnail_path}")
                    failed += 1

            except Exception as e:
                logger.warning(
                    f"Failed to delete thumbnail {thumbnail_path}: {e}",
                    extra={"thumbnail_path": thumbnail_path, "error": str(e)}
                )
                failed += 1

        space_freed_mb = space_freed_bytes / (1024 * 1024)

        return {
            "deleted": deleted,
            "failed": failed,
            "space_freed_mb": space_freed_mb
        }

    async def get_database_size(self) -> float:
        """
        Get database size in megabytes using SQLite PRAGMA queries

        Returns:
            Database size in MB

        Example:
            >>> size_mb = await cleanup_service.get_database_size()
            >>> print(f"Database: {size_mb:.2f} MB")
        """
        db = self.session_factory()
        try:
            # Get page count and page size
            page_count_result = db.execute(text("PRAGMA page_count")).scalar()
            page_size_result = db.execute(text("PRAGMA page_size")).scalar()

            if page_count_result is None or page_size_result is None:
                logger.warning("Could not retrieve database size from PRAGMA queries")
                return 0.0

            # Calculate size in bytes, then convert to MB
            size_bytes = page_count_result * page_size_result
            size_mb = size_bytes / (1024 * 1024)

            logger.debug(f"Database size: {size_mb:.2f} MB ({page_count_result} pages * {page_size_result} bytes)")

            return round(size_mb, 2)

        except Exception as e:
            logger.error(f"Error getting database size: {e}", exc_info=True)
            return 0.0
        finally:
            db.close()

    def get_thumbnails_size(self) -> float:
        """
        Get total size of thumbnails directory in megabytes

        Recursively calculates size of all files in thumbnail directory.

        Returns:
            Thumbnails directory size in MB

        Example:
            >>> size_mb = cleanup_service.get_thumbnails_size()
            >>> print(f"Thumbnails: {size_mb:.2f} MB")
        """
        if not os.path.exists(self.thumbnail_base_dir):
            logger.warning(f"Thumbnails directory does not exist: {self.thumbnail_base_dir}")
            return 0.0

        total_size_bytes = 0
        file_count = 0

        try:
            for dirpath, dirnames, filenames in os.walk(self.thumbnail_base_dir):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        file_size = os.path.getsize(filepath)
                        total_size_bytes += file_size
                        file_count += 1
                    except Exception as e:
                        logger.warning(f"Could not get size of {filepath}: {e}")

            size_mb = total_size_bytes / (1024 * 1024)

            logger.debug(
                f"Thumbnails size: {size_mb:.2f} MB ({file_count} files)",
                extra={"size_mb": size_mb, "file_count": file_count}
            )

            return round(size_mb, 2)

        except Exception as e:
            logger.error(f"Error calculating thumbnails size: {e}", exc_info=True)
            return 0.0

    async def get_storage_info(self) -> Dict[str, Any]:
        """
        Get comprehensive storage information

        Returns:
            Dict with storage statistics:
            {
                "database_mb": float,
                "thumbnails_mb": float,
                "total_mb": float,
                "event_count": int
            }

        Example:
            >>> info = await cleanup_service.get_storage_info()
            >>> print(f"Total storage: {info['total_mb']} MB")
        """
        db = self.session_factory()
        try:
            # Get database size
            database_mb = await self.get_database_size()

            # Get thumbnails size
            thumbnails_mb = self.get_thumbnails_size()

            # Get event count
            event_count = db.query(Event).count()

            storage_info = {
                "database_mb": database_mb,
                "thumbnails_mb": thumbnails_mb,
                "total_mb": round(database_mb + thumbnails_mb, 2),
                "event_count": event_count
            }

            logger.info(
                f"Storage info: {storage_info['total_mb']} MB total ({event_count} events)",
                extra=storage_info
            )

            return storage_info

        except Exception as e:
            logger.error(f"Error getting storage info: {e}", exc_info=True)
            return {
                "database_mb": 0.0,
                "thumbnails_mb": 0.0,
                "total_mb": 0.0,
                "event_count": 0
            }
        finally:
            db.close()


    async def cleanup_old_videos(
        self,
        video_retention_days: int
    ) -> Dict[str, Any]:
        """
        Clean up videos older than video retention period (Story P8-3.2 AC2.10)

        Deletes video files older than video_retention_days and clears
        video_path in the database for those events.

        This is a separate retention policy from event retention, allowing
        users to keep events longer while purging video files earlier.

        Args:
            video_retention_days: Number of days to retain videos

        Returns:
            Dict with cleanup statistics:
            {
                "videos_deleted": int,
                "space_freed_mb": float,
                "events_updated": int
            }
        """
        logger.info(f"Starting video cleanup: retention_days={video_retention_days}")

        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=video_retention_days)

        videos_deleted = 0
        events_updated = 0
        space_freed_bytes = 0

        db = self.session_factory()
        try:
            # Find events with videos older than retention period
            events_with_videos = db.query(Event.id, Event.video_path, Event.timestamp).filter(
                Event.video_path.isnot(None),
                Event.timestamp < cutoff_date
            ).all()

            logger.info(f"Found {len(events_with_videos)} events with videos older than {video_retention_days} days")

            for event in events_with_videos:
                if not event.video_path:
                    continue

                # Build full path to video file
                video_filename = os.path.basename(event.video_path)
                video_path = os.path.join(self.video_base_dir, video_filename)

                # Delete video file if exists
                if os.path.exists(video_path):
                    try:
                        file_size = os.path.getsize(video_path)
                        os.remove(video_path)
                        space_freed_bytes += file_size
                        videos_deleted += 1
                        logger.debug(
                            f"Deleted video {video_filename}",
                            extra={
                                "event_id": event.id,
                                "video_path": video_path,
                                "file_size_bytes": file_size
                            }
                        )
                    except OSError as e:
                        logger.warning(
                            f"Failed to delete video {video_path}: {e}",
                            extra={
                                "event_id": event.id,
                                "video_path": video_path,
                                "error": str(e)
                            }
                        )
                        continue

                # Clear video_path in database
                db.query(Event).filter(Event.id == event.id).update(
                    {"video_path": None},
                    synchronize_session=False
                )
                events_updated += 1

            db.commit()

            stats = {
                "videos_deleted": videos_deleted,
                "space_freed_mb": round(space_freed_bytes / (1024 * 1024), 2),
                "events_updated": events_updated
            }

            logger.info(
                f"Video cleanup complete: {videos_deleted} videos deleted, {stats['space_freed_mb']} MB freed",
                extra=stats
            )

            return stats

        except Exception as e:
            logger.error(f"Error during video cleanup: {e}", exc_info=True)
            db.rollback()
            return {
                "videos_deleted": 0,
                "space_freed_mb": 0.0,
                "events_updated": 0,
                "error": str(e)
            }
        finally:
            db.close()


# Backward compatible thin getter (delegates to @singleton decorator)
def get_cleanup_service() -> CleanupService:
    """
    Get the global CleanupService instance.

    Note: This is now a thin backward-compatible wrapper.
          New code should prefer CleanupService() directly.
    """
    return CleanupService()


def reset_cleanup_service() -> None:
    """Reset the global CleanupService instance (for testing)."""
    CleanupService._reset_instance()
