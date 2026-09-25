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
import re
import shutil
from app.core.decorators import singleton
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Sequence, Set
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.event import Event
from app.core.database import SessionLocal
from app.services.frame_storage_service import get_frame_storage_service

# Stored thumbnail values seen in production and older builds.
_API_THUMBNAIL_MARKER = "/api/v1/thumbnails/"
_THUMBNAIL_PREFIXES = (
    ("api/v1/thumbnails/", len("api/v1/thumbnails/")),
    ("thumbnails/", len("thumbnails/")),
    ("/thumbnails/", len("/thumbnails/")),
    ("data/thumbnails/", len("data/thumbnails/")),
    ("/data/thumbnails/", len("/data/thumbnails/")),
)
_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mov"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Tables that reference events.id. ai_usage is included only when a deployment
# actually has an event_id column (the current model does not).
_EVENT_CHILD_TABLES = (
    "entity_events",
    "event_frames",
    "event_embeddings",
    "frame_embeddings",
    "face_embeddings",
    "vehicle_embeddings",
    "event_feedback",
    "entity_adjustments",
    "webhook_logs",
    "notifications",
    "ai_usage",
)
_DELETE_CHUNK = 400

logger = logging.getLogger(__name__)


def _is_within_directory(path: str, base: str) -> bool:
    """True when ``path`` resolves inside ``base`` (symlink-safe)."""
    try:
        base_real = os.path.realpath(base)
        path_real = os.path.realpath(path)
        return os.path.commonpath([base_real, path_real]) == base_real
    except (ValueError, OSError):
        return False


def _safe_join(base: str, relative: str) -> Optional[str]:
    """Join ``relative`` onto ``base``, rejecting parent-directory traversal."""
    if relative is None:
        return None
    relative = relative.replace("\\", "/").split("?", 1)[0].split("#", 1)[0]
    parts = [part for part in relative.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        logger.warning("Refusing media path with parent traversal: %s", relative)
        return None
    candidate = os.path.normpath(os.path.join(base, *parts))
    if not _is_within_directory(candidate, base):
        return None
    return candidate


def resolve_thumbnail_fs_path(stored: Optional[str], thumbnail_base_dir: str) -> Optional[str]:
    """Map a stored thumbnail value to a file under ``thumbnail_base_dir``.

    Production stores API URLs (``/api/v1/thumbnails/YYYY-MM-DD/file.jpg``).
    Older rows use ``thumbnails/...``, ``data/thumbnails/...``, or a real
    absolute path inside the thumbnail directory. A leading slash on an API
    URL is not a filesystem root.
    """
    if stored is None:
        return None
    raw = str(stored).strip()
    if not raw:
        return None
    raw = raw.split("?", 1)[0].split("#", 1)[0]

    marker_at = raw.find(_API_THUMBNAIL_MARKER)
    if marker_at != -1:
        return _safe_join(thumbnail_base_dir, raw[marker_at + len(_API_THUMBNAIL_MARKER):])

    for prefix, length in _THUMBNAIL_PREFIXES:
        if raw.startswith(prefix):
            return _safe_join(thumbnail_base_dir, raw[length:])

    if os.path.isabs(raw):
        if _is_within_directory(raw, thumbnail_base_dir):
            return os.path.normpath(raw)
        logger.warning("Refusing thumbnail path outside thumbnail directory: %s", raw)
        return None

    return _safe_join(thumbnail_base_dir, raw)


def annotated_sibling_path(path: str) -> str:
    """``frame.jpg`` → ``frame_annotated.jpg`` beside the original."""
    base, ext = os.path.splitext(path)
    return f"{base}_annotated{ext or '.jpg'}"


def _thumbnail_relative_key(stored: Optional[str], thumbnail_base_dir: str) -> Optional[str]:
    resolved = resolve_thumbnail_fs_path(stored, thumbnail_base_dir)
    if not resolved or not _is_within_directory(resolved, thumbnail_base_dir):
        return None
    return os.path.relpath(resolved, thumbnail_base_dir).replace(os.sep, "/")


def _date_dir_is_within_window(relative_path: str, cutoff: datetime) -> bool:
    """Keep files that live in a YYYY-MM-DD folder still inside the window."""
    folder = relative_path.split("/", 1)[0]
    if not _DATE_DIR_RE.match(folder):
        return False
    try:
        folder_day = datetime.strptime(folder, "%Y-%m-%d").date()
    except ValueError:
        return False
    return folder_day >= cutoff.date()


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
        self.frames_base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'data',
            'frames'
        )
        self._child_tables_cache: Optional[List[str]] = None
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
        total_videos_deleted = 0
        total_dependents_deleted = 0
        total_orphan_dependents = 0
        total_space_freed = 0.0
        batches_processed = 0

        # Get frame storage service for cleanup
        frame_storage_service = get_frame_storage_service()

        # Batch deletion loop
        while True:
            db = self.session_factory()
            try:
                # Query batch of events to delete (based on event timestamp, not record creation)
                events_batch = db.query(Event.id, Event.thumbnail_path, Event.video_path).filter(
                    Event.timestamp < cutoff_date
                ).limit(batch_size).all()

                if not events_batch:
                    logger.info("No more events to delete")
                    # Child rows whose events were deleted before foreign keys
                    # were enforced (or by an earlier partial run) are removed
                    # here, on the same open session.
                    orphan_counts = self._delete_orphan_dependent_rows(db)
                    total_orphan_dependents += sum(orphan_counts.values())
                    db.commit()
                    break

                batch_event_ids = [event.id for event in events_batch]
                batch_size_actual = len(batch_event_ids)

                logger.info(f"Processing batch {batches_processed + 1}: {batch_size_actual} events")

                # Delete thumbnail files first (before database records)
                thumbnail_stats = self._delete_thumbnails(events_batch)
                total_thumbnails_deleted += thumbnail_stats["deleted"]
                total_thumbnails_failed += thumbnail_stats["failed"]
                total_space_freed += thumbnail_stats["space_freed_mb"]

                video_stats = self._delete_event_videos(events_batch)
                total_videos_deleted += video_stats["deleted"]
                total_space_freed += video_stats["space_freed_mb"]

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

                # Remove child rows explicitly. Bulk Query.delete() does not
                # run ORM cascades, and SQLite ignores ON DELETE CASCADE unless
                # PRAGMA foreign_keys=ON was set on the connection. ai_usage has
                # no event_id in the current schema, so it is left as cost history
                # unless a deployment added that column.
                dependent_counts = self._delete_dependents_for_event_ids(db, batch_event_ids)
                total_dependents_deleted += sum(dependent_counts.values())

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
            "videos_deleted": total_videos_deleted,
            "dependents_deleted": total_dependents_deleted,
            "orphan_dependents_deleted": total_orphan_dependents,
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
            thumbnail_path = event.thumbnail_path
            if not thumbnail_path:
                continue

            resolved = resolve_thumbnail_fs_path(thumbnail_path, self.thumbnail_base_dir)
            if resolved is None:
                logger.warning(f"Thumbnail path could not be resolved: {thumbnail_path}")
                failed += 1
                continue

            try:
                removed, file_size = self._unlink_media_file(resolved)
                if removed:
                    space_freed_bytes += file_size
                    deleted += 1
                    logger.debug(f"Deleted thumbnail: {resolved}")
                    # Annotated copies sit beside the original and are not stored
                    # on the event row.
                    ann_removed, ann_size = self._unlink_media_file(annotated_sibling_path(resolved))
                    if ann_removed:
                        space_freed_bytes += ann_size
                        deleted += 1
                else:
                    logger.warning(f"Thumbnail file not found: {resolved}")
                    failed += 1

            except Exception as e:
                logger.warning(
                    f"Failed to delete thumbnail {resolved}: {e}",
                    extra={"thumbnail_path": resolved, "error": str(e)}
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


    def _unlink_media_file(self, path: Optional[str]) -> tuple:
        """Delete a regular file. Returns (removed, size_bytes). Symlinks are skipped."""
        if not path or not os.path.isfile(path) or os.path.islink(path):
            return False, 0
        size = os.path.getsize(path)
        os.remove(path)
        return True, size

    def _resolve_video_file(self, stored: Optional[str]) -> Optional[str]:
        """Map a stored video_path to a file inside the video directory."""
        if stored is None:
            return None
        raw = str(stored).strip()
        if not raw:
            return None
        raw = raw.split("?", 1)[0].split("#", 1)[0]
        if os.path.isabs(raw):
            if _is_within_directory(raw, self.video_base_dir):
                return os.path.normpath(raw)
            logger.warning("Refusing video path outside video directory: %s", raw)
            return None
        return _safe_join(self.video_base_dir, os.path.basename(raw.replace("\\", "/")))

    def _delete_event_videos(self, events_batch) -> Dict[str, Any]:
        """Delete motion-video files that belong to events being removed."""
        deleted = 0
        space_freed_bytes = 0
        seen = set()
        for event in events_batch:
            candidates = [os.path.join(self.video_base_dir, f"{event.id}.mp4")]
            resolved = self._resolve_video_file(getattr(event, "video_path", None))
            if resolved:
                candidates.append(resolved)
            for path in candidates:
                norm = os.path.normpath(path)
                if norm in seen:
                    continue
                seen.add(norm)
                if not _is_within_directory(norm, self.video_base_dir):
                    continue
                try:
                    removed, size = self._unlink_media_file(norm)
                except OSError as e:
                    logger.warning(f"Failed to delete video {norm}: {e}")
                    continue
                if removed:
                    deleted += 1
                    space_freed_bytes += size
        return {
            "deleted": deleted,
            "space_freed_mb": space_freed_bytes / (1024 * 1024),
        }

    def _table_columns(self, db: Session, table: str) -> Set[str]:
        if not _IDENTIFIER_RE.match(table):
            return set()
        bind = db.get_bind()
        if bind.dialect.name == "sqlite":
            rows = db.execute(text(f"PRAGMA table_info({table})")).fetchall()
            return {row[1] for row in rows}
        rows = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :table"
            ),
            {"table": table},
        ).fetchall()
        return {row[0] for row in rows}

    def _event_child_tables(self, db: Session) -> List[str]:
        """Child tables that have an event_id column on this database."""
        if self._child_tables_cache is not None:
            return self._child_tables_cache
        found = []
        for table in _EVENT_CHILD_TABLES:
            if "event_id" in self._table_columns(db, table):
                found.append(table)
        self._child_tables_cache = found
        return found

    def _delete_dependents_for_event_ids(
        self,
        db: Session,
        event_ids: Sequence[str],
    ) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        if not event_ids:
            return counts
        for table in self._event_child_tables(db):
            deleted = 0
            ids = list(event_ids)
            for start in range(0, len(ids), _DELETE_CHUNK):
                chunk = ids[start:start + _DELETE_CHUNK]
                params = {f"id{i}": event_id for i, event_id in enumerate(chunk)}
                placeholders = ", ".join(f":id{i}" for i in range(len(chunk)))
                extra = ""
                if table == "ai_usage":
                    extra = " AND event_id IS NOT NULL"
                result = db.execute(
                    text(
                        f"DELETE FROM {table} WHERE event_id IN ({placeholders}){extra}"
                    ),
                    params,
                )
                deleted += max(result.rowcount or 0, 0)
            if deleted:
                counts[table] = deleted
        return counts

    def _delete_orphan_dependent_rows(self, db: Session) -> Dict[str, int]:
        """Delete child rows whose event_id no longer exists."""
        counts: Dict[str, int] = {}
        for table in self._event_child_tables(db):
            extra = ""
            if table == "ai_usage":
                extra = " AND event_id IS NOT NULL"
            result = db.execute(
                text(
                    f"DELETE FROM {table} WHERE NOT EXISTS ("
                    f"SELECT 1 FROM events WHERE events.id = {table}.event_id"
                    f"){extra}"
                )
            )
            deleted = max(result.rowcount or 0, 0)
            if deleted:
                counts[table] = deleted
        if counts:
            logger.info("Deleted orphan event child rows", extra={"counts": counts})
        return counts

    def delete_orphan_dependents(self) -> Dict[str, int]:
        """Remove child rows left behind by events that are already gone."""
        db = self.session_factory()
        try:
            counts = self._delete_orphan_dependent_rows(db)
            db.commit()
            return counts
        except Exception:
            db.rollback()
            logger.exception("Failed to delete orphan event child rows")
            return {}
        finally:
            db.close()

    def cleanup_orphan_media(self, retention_days: int) -> Dict[str, Any]:
        """Delete unreferenced thumbnail and frame files older than the policy.

        Files still referenced by an event, or by ``recognized_entities.thumbnail_path``,
        are kept. So are files in a date folder that is still inside the retention
        window, and anything newer than the cutoff. ``retention_days <= 0`` skips
        the sweep (keep forever).

        Named-entity thumbnails are kept indefinitely. If that protection lookup
        fails, this pass deletes nothing and returns ``skipped``.
        """
        empty = {
            "thumbnails_deleted": 0,
            "frames_deleted": 0,
            "frame_dirs_deleted": 0,
            "space_freed_mb": 0.0,
            "skipped": True,
        }
        if retention_days <= 0:
            logger.info("Orphan media cleanup skipped (retention <= 0)")
            return empty

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        protected: Set[str] = set()
        live_event_ids: Set[str] = set()

        db = self.session_factory()
        try:
            for (stored,) in db.query(Event.thumbnail_path).all():
                key = _thumbnail_relative_key(stored, self.thumbnail_base_dir)
                if key:
                    protected.add(key)
                    protected.add(annotated_sibling_path(key).replace(os.sep, "/"))
            try:
                protected.update(self._protected_entity_thumbnail_keys(db))
            except Exception:
                # Fail closed: a partial or empty protected set must not delete
                # named person/vehicle thumbnails that are past the window.
                logger.exception(
                    "Entity thumbnail protection lookup failed; skipping orphan media cleanup"
                )
                return empty
            live_event_ids = {row[0] for row in db.query(Event.id).all()}
        finally:
            db.close()

        thumb_deleted, thumb_bytes = self._sweep_orphan_thumbnails(cutoff, protected)
        frame_files, frame_dirs, frame_bytes = self._sweep_orphan_frames(cutoff, live_event_ids)
        freed = (thumb_bytes + frame_bytes) / (1024 * 1024)
        stats = {
            "thumbnails_deleted": thumb_deleted,
            "frames_deleted": frame_files,
            "frame_dirs_deleted": frame_dirs,
            "space_freed_mb": round(freed, 2),
            "skipped": False,
        }
        logger.info("Orphan media cleanup complete", extra=stats)
        return stats

    def _sweep_orphan_thumbnails(self, cutoff: datetime, protected: Set[str]) -> tuple:
        deleted = 0
        freed = 0
        base = self.thumbnail_base_dir
        if not os.path.isdir(base):
            return 0, 0
        cutoff_ts = cutoff.timestamp()
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [
                name for name in dirnames
                if not os.path.islink(os.path.join(dirpath, name))
            ]
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                if os.path.splitext(filename)[1].lower() not in _IMAGE_EXTENSIONS:
                    continue
                relative = os.path.relpath(full, base).replace(os.sep, "/")
                if relative in protected:
                    continue
                if _date_dir_is_within_window(relative, cutoff):
                    continue
                try:
                    if os.path.getmtime(full) >= cutoff_ts:
                        continue
                    size = os.path.getsize(full)
                    os.remove(full)
                    deleted += 1
                    freed += size
                except OSError as e:
                    logger.warning(f"Failed to delete orphan thumbnail {full}: {e}")
        # Drop date directories that are now empty.
        for dirpath, dirnames, filenames in os.walk(base, topdown=False):
            if dirpath == base:
                continue
            if os.path.islink(dirpath):
                continue
            if not dirnames and not filenames:
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass
        return deleted, freed

    def _protected_entity_thumbnail_keys(self, db: Session) -> Set[str]:
        """Relative keys for named person/vehicle thumbnails.

        Callers must treat any exception as "do not delete". A partial result
        is never returned: the set is built locally and only handed back if
        the query completes.
        """
        from app.models.recognized_entity import RecognizedEntity

        keys: Set[str] = set()
        for (stored,) in db.query(RecognizedEntity.thumbnail_path).all():
            key = _thumbnail_relative_key(stored, self.thumbnail_base_dir)
            if key:
                keys.add(key)
                keys.add(annotated_sibling_path(key).replace(os.sep, "/"))
        return keys

    def _sweep_orphan_frames(self, cutoff: datetime, live_event_ids: Set[str]) -> tuple:
        base = self.frames_base_dir
        if not os.path.isdir(base):
            return 0, 0, 0
        cutoff_ts = cutoff.timestamp()
        files_deleted = 0
        dirs_deleted = 0
        freed = 0
        for name in os.listdir(base):
            event_dir = os.path.join(base, name)
            if os.path.islink(event_dir) or not os.path.isdir(event_dir):
                continue
            if name in live_event_ids:
                continue
            newest = os.path.getmtime(event_dir)
            file_count = 0
            dir_bytes = 0
            for dirpath, dirnames, filenames in os.walk(event_dir):
                dirnames[:] = [
                    child for child in dirnames
                    if not os.path.islink(os.path.join(dirpath, child))
                ]
                for filename in filenames:
                    full = os.path.join(dirpath, filename)
                    if os.path.islink(full) or not os.path.isfile(full):
                        continue
                    file_count += 1
                    try:
                        newest = max(newest, os.path.getmtime(full))
                        dir_bytes += os.path.getsize(full)
                    except OSError:
                        pass
            if newest >= cutoff_ts:
                continue
            try:
                shutil.rmtree(event_dir)
            except OSError as e:
                logger.warning(f"Failed to delete orphan frame dir {event_dir}: {e}")
                continue
            files_deleted += file_count
            dirs_deleted += 1
            freed += dir_bytes
        return files_deleted, dirs_deleted, freed

    async def cleanup_old_videos(
        self,
        video_retention_days: int
    ) -> Dict[str, Any]:
        """
        Clean up videos older than video retention period (Story P8-3.2 AC2.10)

        Deletes video files for events older than video_retention_days, including
        ``{event_id}.mp4`` when ``video_path`` was never stored. Also removes
        unreferenced files in the video directory whose mtime is past the cutoff.
        Files for events still inside the window are kept even if their mtime
        is old. ``video_retention_days <= 0`` skips the run.

        Returns:
            Dict with cleanup statistics:
            {
                "videos_deleted": int,
                "orphans_deleted": int,
                "space_freed_mb": float,
                "events_updated": int
            }
        """
        if video_retention_days <= 0:
            logger.info("Video cleanup skipped (retention <= 0)")
            return {
                "videos_deleted": 0,
                "orphans_deleted": 0,
                "space_freed_mb": 0.0,
                "events_updated": 0,
                "skipped": True,
            }

        logger.info(f"Starting video cleanup: retention_days={video_retention_days}")
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=video_retention_days)
        videos_deleted = 0
        orphans_deleted = 0
        events_updated = 0
        space_freed_bytes = 0
        removed_paths: Set[str] = set()

        def _remove_video(path: Optional[str]) -> bool:
            nonlocal videos_deleted, space_freed_bytes
            if not path:
                return False
            norm = os.path.normpath(path)
            if norm in removed_paths:
                return False
            if not _is_within_directory(norm, self.video_base_dir):
                return False
            try:
                removed, size = self._unlink_media_file(norm)
            except OSError as e:
                logger.warning(f"Failed to delete video {norm}: {e}")
                return False
            if not removed:
                return False
            removed_paths.add(norm)
            videos_deleted += 1
            space_freed_bytes += size
            return True

        db = self.session_factory()
        try:
            old_events = db.query(Event.id, Event.video_path).filter(
                Event.timestamp < cutoff_date
            ).all()
            recent_events = db.query(Event.id, Event.video_path).filter(
                Event.timestamp >= cutoff_date
            ).all()

            protected_names: Set[str] = set()
            for event in recent_events:
                protected_names.add(f"{event.id}.mp4")
                protected_names.add(str(event.id))
                if event.video_path:
                    base_name = os.path.basename(str(event.video_path))
                    protected_names.add(base_name)
                    protected_names.add(os.path.splitext(base_name)[0])

            logger.info(
                f"Found {len(old_events)} events older than {video_retention_days} days"
            )

            for event in old_events:
                _remove_video(os.path.join(self.video_base_dir, f"{event.id}.mp4"))
                if not event.video_path:
                    continue
                resolved = self._resolve_video_file(event.video_path)
                if resolved is None:
                    # Path is outside the video directory. Leave the column so
                    # a later run can still see it.
                    continue
                if os.path.isfile(resolved) and not _remove_video(resolved):
                    continue
                db.query(Event).filter(Event.id == event.id).update(
                    {"video_path": None},
                    synchronize_session=False
                )
                events_updated += 1

            if os.path.isdir(self.video_base_dir):
                cutoff_ts = cutoff_date.timestamp()
                for filename in os.listdir(self.video_base_dir):
                    if os.path.splitext(filename)[1].lower() not in _VIDEO_EXTENSIONS:
                        continue
                    stem = os.path.splitext(filename)[0]
                    if filename in protected_names or stem in protected_names:
                        continue
                    full = os.path.join(self.video_base_dir, filename)
                    if os.path.islink(full) or not os.path.isfile(full):
                        continue
                    try:
                        if os.path.getmtime(full) >= cutoff_ts:
                            continue
                    except OSError:
                        continue
                    if _remove_video(full):
                        orphans_deleted += 1

            db.commit()

            stats = {
                "videos_deleted": videos_deleted,
                "orphans_deleted": orphans_deleted,
                "space_freed_mb": round(space_freed_bytes / (1024 * 1024), 2),
                "events_updated": events_updated,
            }
            logger.info(
                f"Video cleanup complete: {videos_deleted} videos deleted, "
                f"{stats['space_freed_mb']} MB freed",
                extra=stats,
            )
            return stats

        except Exception as e:
            logger.error(f"Error during video cleanup: {e}", exc_info=True)
            db.rollback()
            return {
                "videos_deleted": 0,
                "orphans_deleted": 0,
                "space_freed_mb": 0.0,
                "events_updated": 0,
                "error": str(e),
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
