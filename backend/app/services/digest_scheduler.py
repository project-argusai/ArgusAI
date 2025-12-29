"""
Digest Scheduler Service (Story P4-4.2)

Provides scheduled daily digest generation using APScheduler.
Orchestrates calls to SummaryService to generate and store daily summaries.

Architecture:
    APScheduler (cron trigger at configurable time)
        │
        ▼
    DigestScheduler.run_scheduled_digest()
        │
        ├── Check if digest exists (idempotent)
        ├── Calculate yesterday's date range
        └── Call SummaryService.generate_summary()
                    │
                    ▼
            Store with digest_type='daily'
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, date
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.job import Job
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db_session
from app.models.activity_summary import ActivitySummary
from app.models.system_setting import SystemSetting
from app.services.summary_service import get_summary_service, SummaryResult
from app.services.delivery_service import get_delivery_service, DeliveryResult

logger = logging.getLogger(__name__)

# Default schedule time (6:00 AM)
DEFAULT_DIGEST_TIME = "06:00"

# Job ID for daily digest
DAILY_DIGEST_JOB_ID = "daily_digest_job"


@dataclass
class DigestStatus:
    """Status information about the digest scheduler."""
    enabled: bool
    schedule_time: str
    last_run: Optional[datetime] = None
    last_status: str = "never_run"
    last_error: Optional[str] = None
    next_run: Optional[datetime] = None


class DigestScheduler:
    """
    Manages scheduled daily digest generation.

    Uses APScheduler to trigger digest generation at a configurable time each day.
    Integrates with SummaryService for actual summary generation.

    Attributes:
        DEFAULT_TIMEOUT_SECONDS: Maximum time for digest generation (60s per NFR2)
    """

    DEFAULT_TIMEOUT_SECONDS = 60

    def __init__(self):
        """Initialize DigestScheduler with APScheduler."""
        self._scheduler = AsyncIOScheduler()
        self._enabled = False
        self._schedule_time = DEFAULT_DIGEST_TIME
        self._last_run: Optional[datetime] = None
        self._last_status: str = "never_run"
        self._last_error: Optional[str] = None
        self._running = False

        logger.info(
            "DigestScheduler initialized",
            extra={"event_type": "digest_scheduler_init"}
        )

    def start(self) -> None:
        """Start the scheduler if not already running."""
        if not self._running:
            self._scheduler.start()
            self._running = True
            logger.info(
                "DigestScheduler started",
                extra={"event_type": "digest_scheduler_started"}
            )

    def stop(self) -> None:
        """Stop the scheduler cleanly."""
        if self._running:
            self._scheduler.shutdown(wait=False)
            self._running = False
            logger.info(
                "DigestScheduler stopped",
                extra={"event_type": "digest_scheduler_stopped"}
            )

    def schedule_daily_digest(self, time: str = DEFAULT_DIGEST_TIME) -> None:
        """
        Schedule or reschedule the daily digest job.

        Args:
            time: Time in HH:MM format (24-hour). Defaults to 06:00.
        """
        self._schedule_time = time

        try:
            hour, minute = map(int, time.split(":"))
        except ValueError:
            logger.error(f"Invalid time format: {time}. Expected HH:MM")
            hour, minute = 6, 0  # Fallback to 6:00 AM

        # Remove existing job if present
        existing_job = self._scheduler.get_job(DAILY_DIGEST_JOB_ID)
        if existing_job:
            self._scheduler.remove_job(DAILY_DIGEST_JOB_ID)
            logger.debug(f"Removed existing digest job")

        # Create cron trigger for daily execution
        trigger = CronTrigger(hour=hour, minute=minute)

        # Add job
        self._scheduler.add_job(
            self._run_scheduled_digest_wrapper,
            trigger=trigger,
            id=DAILY_DIGEST_JOB_ID,
            name="Daily Digest Generation",
            replace_existing=True,
            misfire_grace_time=3600,  # Allow 1 hour grace for misfired jobs
        )

        self._enabled = True

        logger.info(
            f"Daily digest scheduled for {hour:02d}:{minute:02d}",
            extra={
                "event_type": "digest_job_scheduled",
                "schedule_time": time,
                "hour": hour,
                "minute": minute
            }
        )

    def unschedule_daily_digest(self) -> None:
        """Remove the daily digest job from scheduler."""
        existing_job = self._scheduler.get_job(DAILY_DIGEST_JOB_ID)
        if existing_job:
            self._scheduler.remove_job(DAILY_DIGEST_JOB_ID)

        self._enabled = False

        logger.info(
            "Daily digest unscheduled",
            extra={"event_type": "digest_job_unscheduled"}
        )

    async def _run_scheduled_digest_wrapper(self) -> None:
        """Wrapper to run scheduled digest with error handling."""
        try:
            await self.run_scheduled_digest()
        except Exception as e:
            # Log but don't propagate - scheduler should continue running
            logger.error(
                f"Scheduled digest failed: {e}",
                extra={"event_type": "digest_scheduled_error", "error": str(e)},
                exc_info=True
            )
            self._last_status = "error"
            self._last_error = str(e)

    async def run_scheduled_digest(self, target_date: Optional[date] = None) -> Optional[SummaryResult]:
        """
        Run digest generation for a specific date (defaults to yesterday).

        This method is called by the scheduler but can also be invoked manually.
        It is idempotent - will skip if a digest already exists for the target date.

        Args:
            target_date: Date to generate digest for. Defaults to yesterday.

        Returns:
            SummaryResult if digest was generated, None if skipped or failed.
        """
        self._last_run = datetime.now(timezone.utc)

        # Calculate target date (yesterday by default)
        if target_date is None:
            target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        logger.info(
            f"Starting digest generation for {target_date}",
            extra={
                "event_type": "digest_generation_start",
                "target_date": target_date.isoformat()
            }
        )

        # Get database session with context manager for automatic cleanup
        with get_db_session() as db:
            try:
                # Check if digest already exists (idempotent)
                if self._digest_exists_for_date(db, target_date):
                    logger.info(
                        f"Digest already exists for {target_date}, skipping",
                        extra={
                            "event_type": "digest_skipped_exists",
                            "target_date": target_date.isoformat()
                        }
                    )
                    self._last_status = "skipped"
                    return None

                # Calculate midnight-to-midnight range in UTC
                start_time = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                end_time = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)

                # Call SummaryService to generate summary
                summary_service = get_summary_service()
                result = await summary_service.generate_summary(
                    db=db,
                    start_time=start_time,
                    end_time=end_time,
                    camera_ids=None  # All cameras
                )

                if not result.success:
                    logger.error(
                        f"Digest generation failed: {result.error}",
                        extra={
                            "event_type": "digest_generation_failed",
                            "error": result.error
                        }
                    )
                    self._last_status = "error"
                    self._last_error = result.error
                    return None

                # Store the result with digest_type='daily'
                digest = self._save_digest(db, result, target_date)

                # Deliver the digest via configured channels (Story P4-4.3)
                await self._deliver_digest(db, digest)

                self._last_status = "success"
                self._last_error = None

                logger.info(
                    f"Digest generated and delivered for {target_date}",
                    extra={
                        "event_type": "digest_generation_success",
                        "target_date": target_date.isoformat(),
                        "event_count": result.event_count,
                        "ai_cost": float(result.ai_cost)
                    }
                )

                return result

            except Exception as e:
                logger.error(
                    f"Digest generation error: {e}",
                    extra={
                        "event_type": "digest_generation_error",
                        "error": str(e)
                    },
                    exc_info=True
                )
                self._last_status = "error"
                self._last_error = str(e)
                raise

    def _digest_exists_for_date(self, db: Session, target_date: date) -> bool:
        """
        Check if a daily digest already exists for the target date.

        Args:
            db: Database session
            target_date: Date to check

        Returns:
            True if digest exists, False otherwise
        """
        # Query for daily digest matching the target date
        existing = db.query(ActivitySummary).filter(
            ActivitySummary.digest_type == 'daily',
            func.date(ActivitySummary.period_start) == target_date
        ).first()

        return existing is not None

    def _save_digest(self, db: Session, result: SummaryResult, target_date: date) -> ActivitySummary:
        """
        Save the generated digest to database with digest_type marker.

        Args:
            db: Database session
            result: SummaryResult from SummaryService
            target_date: Date the digest covers

        Returns:
            Created ActivitySummary record
        """
        summary = ActivitySummary(
            summary_text=result.summary_text,
            period_start=result.period_start,
            period_end=result.period_end,
            event_count=result.event_count,
            camera_ids=None,  # Daily digest covers all cameras
            generated_at=result.generated_at,
            ai_cost=float(result.ai_cost),
            provider_used=result.provider_used,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            digest_type='daily',  # Mark as daily digest
        )

        db.add(summary)
        db.commit()
        db.refresh(summary)

        logger.debug(
            f"Saved daily digest: {summary.id}",
            extra={
                "event_type": "digest_saved",
                "summary_id": summary.id,
                "target_date": target_date.isoformat()
            }
        )

        return summary

    async def _deliver_digest(self, db: Session, digest: ActivitySummary) -> None:
        """
        Deliver digest via configured channels (Story P4-4.3).

        Calls DeliveryService to send digest via email, push, and/or in-app.
        Updates digest with delivery_status. Failures are logged but do not
        propagate - scheduler continues regardless.

        Args:
            db: Database session
            digest: ActivitySummary to deliver
        """
        import json

        try:
            delivery_service = get_delivery_service(db)
            result = await delivery_service.deliver_digest(digest)

            # Update digest with delivery status
            digest.delivery_status = json.dumps(result.to_dict())
            db.commit()

            logger.info(
                f"Digest delivery complete: {len(result.channels_succeeded)}/{len(result.channels_attempted)} channels",
                extra={
                    "event_type": "digest_delivery_complete",
                    "digest_id": digest.id,
                    "success": result.success,
                    "channels_succeeded": result.channels_succeeded,
                    "delivery_time_ms": result.delivery_time_ms
                }
            )

        except Exception as e:
            # Log but don't propagate - scheduler should continue
            logger.error(
                f"Digest delivery failed: {e}",
                extra={
                    "event_type": "digest_delivery_error",
                    "digest_id": digest.id,
                    "error": str(e)
                },
                exc_info=True
            )

            # Still update delivery_status to record the failure
            try:
                digest.delivery_status = json.dumps({
                    "success": False,
                    "channels_attempted": [],
                    "channels_succeeded": [],
                    "errors": {"delivery": str(e)},
                    "delivery_time_ms": 0
                })
                db.commit()
            except Exception:
                pass  # Don't fail if status update fails

    def get_status(self) -> DigestStatus:
        """
        Get current scheduler status.

        Returns:
            DigestStatus with current state information
        """
        next_run = None
        job = self._scheduler.get_job(DAILY_DIGEST_JOB_ID)
        if job and job.next_run_time:
            next_run = job.next_run_time

        return DigestStatus(
            enabled=self._enabled,
            schedule_time=self._schedule_time,
            last_run=self._last_run,
            last_status=self._last_status,
            last_error=self._last_error,
            next_run=next_run
        )

    def is_running(self) -> bool:
        """Check if scheduler is currently running."""
        return self._running


# Singleton instance
_digest_scheduler: Optional[DigestScheduler] = None


def get_digest_scheduler() -> DigestScheduler:
    """
    Get the singleton DigestScheduler instance.

    Returns:
        The global DigestScheduler instance
    """
    global _digest_scheduler
    if _digest_scheduler is None:
        _digest_scheduler = DigestScheduler()
    return _digest_scheduler


def reset_digest_scheduler() -> None:
    """Reset the singleton instance (useful for testing)."""
    global _digest_scheduler
    if _digest_scheduler is not None:
        _digest_scheduler.stop()
    _digest_scheduler = None


async def initialize_digest_scheduler() -> None:
    """
    Initialize digest scheduler from settings.

    Called at application startup. Reads settings from database
    and starts scheduler if enabled.
    """
    scheduler = get_digest_scheduler()

    # Read settings from database with context manager for automatic cleanup
    with get_db_session() as db:
        enabled_setting = db.query(SystemSetting).filter(
            SystemSetting.key == "digest_schedule_enabled"
        ).first()

        time_setting = db.query(SystemSetting).filter(
            SystemSetting.key == "digest_schedule_time"
        ).first()

        enabled = enabled_setting and enabled_setting.value.lower() in ('true', '1', 'yes')
        schedule_time = time_setting.value if time_setting else DEFAULT_DIGEST_TIME

        if enabled:
            scheduler.start()
            scheduler.schedule_daily_digest(schedule_time)
            logger.info(
                f"Digest scheduler initialized and started (time: {schedule_time})",
                extra={
                    "event_type": "digest_scheduler_initialized",
                    "enabled": True,
                    "schedule_time": schedule_time
                }
            )
        else:
            logger.info(
                "Digest scheduler disabled in settings",
                extra={
                    "event_type": "digest_scheduler_initialized",
                    "enabled": False
                }
            )


async def shutdown_digest_scheduler() -> None:
    """
    Shutdown digest scheduler cleanly.

    Called at application shutdown.
    """
    scheduler = get_digest_scheduler()
    scheduler.stop()
    logger.info("Digest scheduler shutdown complete")
