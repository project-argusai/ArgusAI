"""Scheduled retention jobs.

Event cleanup runs daily at 02:00. Video cleanup runs daily at 02:15.
Both honor ``settings_auto_cleanup`` and skip when their retention days are
``<= 0`` (keep forever).
"""
import logging

from apscheduler.triggers.cron import CronTrigger

from app.services.cleanup_service import get_cleanup_service
from app.services.retention_settings import (
    get_video_retention_days,
    is_auto_cleanup_enabled,
    reconcile_retention_policy,
)

logger = logging.getLogger(__name__)


async def scheduled_cleanup_job():
    """Delete aged events, their media, dependent rows, and unreferenced files."""
    try:
        if not is_auto_cleanup_enabled():
            logger.info("Scheduled cleanup skipped (auto_cleanup disabled)")
            return

        retention_days = reconcile_retention_policy()
        cleanup_service = get_cleanup_service()

        if retention_days <= 0:
            logger.info("Scheduled cleanup skipped (retention policy set to forever)")
            # Events already removed by older runs can still leave child rows.
            orphan_rows = cleanup_service.delete_orphan_dependents()
            logger.info(
                "Orphan dependent-row cleanup complete",
                extra=orphan_rows,
            )
            return

        logger.info(f"Starting scheduled cleanup (retention: {retention_days} days)")
        stats = await cleanup_service.cleanup_old_events(retention_days=retention_days)
        media_stats = cleanup_service.cleanup_orphan_media(retention_days=retention_days)
        logger.info(
            f"Scheduled cleanup complete: {stats['events_deleted']} events deleted, "
            f"{stats['space_freed_mb']} MB freed",
            extra={**stats, "orphan_media": media_stats},
        )
    except Exception as e:
        logger.error(f"Scheduled cleanup failed: {e}", exc_info=True)


async def scheduled_video_cleanup_job():
    """Delete aged motion videos, including files with no ``video_path`` row."""
    try:
        if not is_auto_cleanup_enabled():
            logger.info("Scheduled video cleanup skipped (auto_cleanup disabled)")
            return

        video_retention_days = get_video_retention_days()
        if video_retention_days <= 0:
            logger.info("Scheduled video cleanup skipped (video retention set to forever)")
            return

        logger.info(
            f"Starting scheduled video cleanup (retention: {video_retention_days} days)"
        )
        cleanup_service = get_cleanup_service()
        stats = await cleanup_service.cleanup_old_videos(
            video_retention_days=video_retention_days
        )
        logger.info(
            f"Scheduled video cleanup complete: {stats.get('videos_deleted', 0)} videos deleted, "
            f"{stats.get('space_freed_mb', 0)} MB freed",
            extra=stats,
        )
    except Exception as e:
        logger.error(f"Scheduled video cleanup failed: {e}", exc_info=True)


def register_retention_jobs(scheduler) -> None:
    """Register the daily event and video retention jobs."""
    scheduler.add_job(
        scheduled_cleanup_job,
        trigger=CronTrigger(hour=2, minute=0),
        id="daily_cleanup",
        name="Daily event cleanup based on retention policy",
        replace_existing=True,
    )
    scheduler.add_job(
        scheduled_video_cleanup_job,
        trigger=CronTrigger(hour=2, minute=15),
        id="daily_video_cleanup",
        name="Daily motion video cleanup based on video retention policy",
        replace_existing=True,
    )
