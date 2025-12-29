"""
Unit tests for DigestScheduler Service (Story P4-4.2)

Tests:
- AC1: DigestScheduler service instantiation and method signatures
- AC2: APScheduler integration with configurable time
- AC3: Calls SummaryService.generate_summary() with correct date range
- AC4: Stores digests with digest_type='daily' marker
- AC7: Graceful error handling
- AC8: Idempotent behavior (skip if exists)
"""
import pytest
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from app.services.digest_scheduler import (
    DigestScheduler,
    get_digest_scheduler,
    reset_digest_scheduler,
    initialize_digest_scheduler,
    shutdown_digest_scheduler,
    DigestStatus,
    DEFAULT_DIGEST_TIME,
    DAILY_DIGEST_JOB_ID,
)
from app.services.summary_service import SummaryResult, SummaryStats


@pytest.fixture(autouse=True)
def reset_scheduler():
    """Reset scheduler singleton before each test."""
    reset_digest_scheduler()
    yield
    reset_digest_scheduler()


class TestDigestSchedulerInitialization:
    """Tests for DigestScheduler instantiation (AC1)."""

    def test_scheduler_instantiation(self):
        """Test DigestScheduler can be instantiated."""
        scheduler = DigestScheduler()
        assert scheduler is not None
        assert scheduler._enabled is False
        assert scheduler._schedule_time == DEFAULT_DIGEST_TIME
        assert scheduler._running is False

    def test_get_digest_scheduler_singleton(self):
        """Test get_digest_scheduler returns singleton."""
        scheduler1 = get_digest_scheduler()
        scheduler2 = get_digest_scheduler()
        assert scheduler1 is scheduler2

    def test_reset_digest_scheduler(self):
        """Test reset_digest_scheduler creates new instance."""
        scheduler1 = get_digest_scheduler()
        reset_digest_scheduler()
        scheduler2 = get_digest_scheduler()
        assert scheduler1 is not scheduler2

    def test_scheduler_has_required_methods(self):
        """Test scheduler has required methods (AC1)."""
        scheduler = DigestScheduler()
        assert hasattr(scheduler, 'schedule_daily_digest')
        assert hasattr(scheduler, 'run_scheduled_digest')
        assert hasattr(scheduler, 'start')
        assert hasattr(scheduler, 'stop')
        assert hasattr(scheduler, 'get_status')
        assert callable(scheduler.schedule_daily_digest)
        assert callable(scheduler.run_scheduled_digest)


class TestSchedulerLifecycle:
    """Tests for scheduler start/stop lifecycle."""

    def test_start_scheduler(self):
        """Test scheduler start."""
        scheduler = DigestScheduler()
        with patch.object(scheduler._scheduler, 'start') as mock_start:
            scheduler.start()
            mock_start.assert_called_once()
            assert scheduler._running is True

    def test_stop_scheduler(self):
        """Test scheduler stop."""
        scheduler = DigestScheduler()
        scheduler._running = True
        with patch.object(scheduler._scheduler, 'shutdown') as mock_shutdown:
            scheduler.stop()
            mock_shutdown.assert_called_once_with(wait=False)
            assert scheduler._running is False

    def test_stop_scheduler_not_running(self):
        """Test stop does nothing if not running."""
        scheduler = DigestScheduler()
        scheduler._running = False
        with patch.object(scheduler._scheduler, 'shutdown') as mock_shutdown:
            scheduler.stop()
            mock_shutdown.assert_not_called()


class TestScheduleDailyDigest:
    """Tests for schedule_daily_digest (AC2)."""

    def test_schedule_daily_digest_default_time(self):
        """Test scheduling with default time."""
        scheduler = DigestScheduler()
        with patch.object(scheduler._scheduler, 'add_job') as mock_add_job:
            with patch.object(scheduler._scheduler, 'get_job', return_value=None):
                scheduler.schedule_daily_digest()

                mock_add_job.assert_called_once()
                call_kwargs = mock_add_job.call_args[1]
                assert call_kwargs['id'] == DAILY_DIGEST_JOB_ID
                assert scheduler._enabled is True
                assert scheduler._schedule_time == DEFAULT_DIGEST_TIME

    def test_schedule_daily_digest_custom_time(self):
        """Test scheduling with custom time (AC2)."""
        scheduler = DigestScheduler()
        custom_time = "08:30"

        with patch.object(scheduler._scheduler, 'add_job') as mock_add_job:
            with patch.object(scheduler._scheduler, 'get_job', return_value=None):
                scheduler.schedule_daily_digest(custom_time)

                mock_add_job.assert_called_once()
                assert scheduler._schedule_time == custom_time

    def test_schedule_replaces_existing_job(self):
        """Test scheduling replaces existing job."""
        scheduler = DigestScheduler()
        mock_job = MagicMock()

        with patch.object(scheduler._scheduler, 'get_job', return_value=mock_job):
            with patch.object(scheduler._scheduler, 'remove_job') as mock_remove:
                with patch.object(scheduler._scheduler, 'add_job'):
                    scheduler.schedule_daily_digest("07:00")

                    mock_remove.assert_called_once_with(DAILY_DIGEST_JOB_ID)

    def test_unschedule_daily_digest(self):
        """Test unscheduling removes job."""
        scheduler = DigestScheduler()
        scheduler._enabled = True
        mock_job = MagicMock()

        with patch.object(scheduler._scheduler, 'get_job', return_value=mock_job):
            with patch.object(scheduler._scheduler, 'remove_job') as mock_remove:
                scheduler.unschedule_daily_digest()

                mock_remove.assert_called_once_with(DAILY_DIGEST_JOB_ID)
                assert scheduler._enabled is False


class TestRunScheduledDigest:
    """Tests for run_scheduled_digest (AC3, AC4, AC7, AC8)."""

    @pytest.mark.asyncio
    async def test_run_scheduled_digest_success(self):
        """Test successful digest generation (AC3, AC4)."""
        scheduler = DigestScheduler()
        target_date = date(2025, 12, 11)

        mock_result = SummaryResult(
            summary_text="Test summary",
            period_start=datetime(2025, 12, 11, 0, 0, 0, tzinfo=timezone.utc),
            period_end=datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc),
            event_count=5,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=5),
            ai_cost=Decimal("0.001"),
            provider_used="openai",
            success=True
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None  # No existing digest

        with patch('app.services.digest_scheduler.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(mock_db, '__enter__', return_value=mock_db), \
                 patch.object(mock_db, '__exit__', return_value=False):
            with patch('app.services.digest_scheduler.get_summary_service') as mock_get_service:
                mock_service = MagicMock()
                mock_service.generate_summary = AsyncMock(return_value=mock_result)
                mock_get_service.return_value = mock_service

                result = await scheduler.run_scheduled_digest(target_date=target_date)

                # Verify generate_summary was called with correct date range
                mock_service.generate_summary.assert_called_once()
                call_kwargs = mock_service.generate_summary.call_args[1]
                assert call_kwargs['start_time'].date() == target_date
                assert call_kwargs['end_time'].date() == target_date

                # Verify result was saved with digest_type
                mock_db.add.assert_called_once()
                saved_summary = mock_db.add.call_args[0][0]
                assert saved_summary.digest_type == 'daily'

                assert result == mock_result

    @pytest.mark.asyncio
    async def test_run_scheduled_digest_defaults_to_yesterday(self):
        """Test digest defaults to yesterday when no date specified."""
        scheduler = DigestScheduler()
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        mock_result = SummaryResult(
            summary_text="Test",
            period_start=datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc),
            period_end=datetime.combine(yesterday, datetime.max.time()).replace(tzinfo=timezone.utc),
            event_count=0,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=0),
            success=True
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch('app.services.digest_scheduler.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(mock_db, '__enter__', return_value=mock_db), \
                 patch.object(mock_db, '__exit__', return_value=False):
            with patch('app.services.digest_scheduler.get_summary_service') as mock_get_service:
                mock_service = MagicMock()
                mock_service.generate_summary = AsyncMock(return_value=mock_result)
                mock_get_service.return_value = mock_service

                await scheduler.run_scheduled_digest()

                # Verify yesterday's date was used
                call_kwargs = mock_service.generate_summary.call_args[1]
                assert call_kwargs['start_time'].date() == yesterday

    @pytest.mark.asyncio
    async def test_run_scheduled_digest_idempotent(self):
        """Test digest is skipped if already exists (AC8)."""
        scheduler = DigestScheduler()
        target_date = date(2025, 12, 11)

        # Mock existing digest
        existing_digest = MagicMock()
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = existing_digest

        with patch('app.services.digest_scheduler.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(mock_db, '__enter__', return_value=mock_db), \
                 patch.object(mock_db, '__exit__', return_value=False):
            with patch('app.services.digest_scheduler.get_summary_service') as mock_get_service:
                mock_service = MagicMock()
                mock_get_service.return_value = mock_service

                result = await scheduler.run_scheduled_digest(target_date=target_date)

                # Verify generate_summary was NOT called
                mock_service.generate_summary.assert_not_called()
                assert result is None
                assert scheduler._last_status == "skipped"

    @pytest.mark.asyncio
    async def test_run_scheduled_digest_error_handling(self):
        """Test error handling doesn't propagate (AC7)."""
        scheduler = DigestScheduler()
        target_date = date(2025, 12, 11)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch('app.services.digest_scheduler.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(mock_db, '__enter__', return_value=mock_db), \
                 patch.object(mock_db, '__exit__', return_value=False):
            with patch('app.services.digest_scheduler.get_summary_service') as mock_get_service:
                mock_service = MagicMock()
                mock_service.generate_summary = AsyncMock(side_effect=Exception("AI service failed"))
                mock_get_service.return_value = mock_service

                # Should raise exception (but wrapper catches it)
                with pytest.raises(Exception):
                    await scheduler.run_scheduled_digest(target_date=target_date)

                assert scheduler._last_status == "error"
                assert "AI service failed" in scheduler._last_error

    @pytest.mark.asyncio
    async def test_run_scheduled_digest_wrapper_catches_exception(self):
        """Test wrapper catches exceptions (AC7)."""
        scheduler = DigestScheduler()

        with patch.object(scheduler, 'run_scheduled_digest', side_effect=Exception("Test error")):
            # Should not propagate exception
            await scheduler._run_scheduled_digest_wrapper()

            assert scheduler._last_status == "error"
            assert "Test error" in scheduler._last_error

    @pytest.mark.asyncio
    async def test_run_scheduled_digest_generation_failure(self):
        """Test handling of generation failure from SummaryService."""
        scheduler = DigestScheduler()
        target_date = date(2025, 12, 11)

        mock_result = SummaryResult(
            summary_text="",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc),
            event_count=0,
            generated_at=datetime.now(timezone.utc),
            stats=SummaryStats(total_events=0),
            success=False,
            error="AI provider unavailable"
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch('app.services.digest_scheduler.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(mock_db, '__enter__', return_value=mock_db), \
                 patch.object(mock_db, '__exit__', return_value=False):
            with patch('app.services.digest_scheduler.get_summary_service') as mock_get_service:
                mock_service = MagicMock()
                mock_service.generate_summary = AsyncMock(return_value=mock_result)
                mock_get_service.return_value = mock_service

                result = await scheduler.run_scheduled_digest(target_date=target_date)

                assert result is None
                assert scheduler._last_status == "error"


class TestGetStatus:
    """Tests for get_status method."""

    def test_get_status_initial(self):
        """Test initial status."""
        scheduler = DigestScheduler()
        status = scheduler.get_status()

        assert isinstance(status, DigestStatus)
        assert status.enabled is False
        assert status.schedule_time == DEFAULT_DIGEST_TIME
        assert status.last_run is None
        assert status.last_status == "never_run"
        assert status.next_run is None

    def test_get_status_with_scheduled_job(self):
        """Test status includes next run time from scheduled job."""
        scheduler = DigestScheduler()
        next_run_time = datetime.now(timezone.utc) + timedelta(hours=12)

        mock_job = MagicMock()
        mock_job.next_run_time = next_run_time

        with patch.object(scheduler._scheduler, 'get_job', return_value=mock_job):
            scheduler._enabled = True
            scheduler._schedule_time = "08:00"
            status = scheduler.get_status()

            assert status.enabled is True
            assert status.schedule_time == "08:00"
            assert status.next_run == next_run_time


class TestDateRangeCalculation:
    """Tests for date range calculation (AC3)."""

    @pytest.mark.asyncio
    async def test_midnight_to_midnight_range(self):
        """Test midnight to midnight UTC calculation."""
        scheduler = DigestScheduler()
        target_date = date(2025, 12, 11)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch('app.services.digest_scheduler.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(mock_db, '__enter__', return_value=mock_db), \
                 patch.object(mock_db, '__exit__', return_value=False):
            with patch('app.services.digest_scheduler.get_summary_service') as mock_get_service:
                mock_service = MagicMock()
                mock_service.generate_summary = AsyncMock(return_value=SummaryResult(
                    summary_text="Test",
                    period_start=datetime(2025, 12, 11, 0, 0, 0, tzinfo=timezone.utc),
                    period_end=datetime(2025, 12, 11, 23, 59, 59, tzinfo=timezone.utc),
                    event_count=0,
                    generated_at=datetime.now(timezone.utc),
                    stats=SummaryStats(total_events=0),
                    success=True
                ))
                mock_get_service.return_value = mock_service

                await scheduler.run_scheduled_digest(target_date=target_date)

                call_kwargs = mock_service.generate_summary.call_args[1]
                start_time = call_kwargs['start_time']
                end_time = call_kwargs['end_time']

                # Verify midnight to midnight
                assert start_time.hour == 0
                assert start_time.minute == 0
                assert start_time.second == 0
                assert end_time.hour == 23
                assert end_time.minute == 59
                assert end_time.second == 59
                assert end_time.microsecond == 999999


class TestDigestExistsCheck:
    """Tests for idempotent digest check (AC8)."""

    def test_digest_exists_for_date_true(self):
        """Test digest_exists returns True when digest exists."""
        scheduler = DigestScheduler()
        target_date = date(2025, 12, 11)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()

        result = scheduler._digest_exists_for_date(mock_db, target_date)
        assert result is True

    def test_digest_exists_for_date_false(self):
        """Test digest_exists returns False when no digest."""
        scheduler = DigestScheduler()
        target_date = date(2025, 12, 11)

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = scheduler._digest_exists_for_date(mock_db, target_date)
        assert result is False


class TestInitializeDigestScheduler:
    """Tests for initialize_digest_scheduler (AC9)."""

    @pytest.mark.asyncio
    async def test_initialize_when_enabled(self):
        """Test initialization starts scheduler when enabled."""
        mock_db = MagicMock()

        # Mock settings
        enabled_setting = MagicMock()
        enabled_setting.value = "true"
        time_setting = MagicMock()
        time_setting.value = "07:30"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            enabled_setting,  # digest_schedule_enabled
            time_setting,     # digest_schedule_time
        ]

        with patch('app.services.digest_scheduler.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(mock_db, '__enter__', return_value=mock_db), \
                 patch.object(mock_db, '__exit__', return_value=False):
            with patch('app.services.digest_scheduler.get_digest_scheduler') as mock_get:
                mock_scheduler = MagicMock()
                mock_get.return_value = mock_scheduler

                await initialize_digest_scheduler()

                mock_scheduler.start.assert_called_once()
                mock_scheduler.schedule_daily_digest.assert_called_once_with("07:30")

    @pytest.mark.asyncio
    async def test_initialize_when_disabled(self):
        """Test initialization does not start when disabled."""
        mock_db = MagicMock()

        # Mock settings - disabled
        enabled_setting = MagicMock()
        enabled_setting.value = "false"

        mock_db.query.return_value.filter.return_value.first.side_effect = [
            enabled_setting,  # digest_schedule_enabled
            None,             # digest_schedule_time
        ]

        with patch('app.services.digest_scheduler.get_db_session') as mock_get_db:
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=False)
            with patch.object(mock_db, '__enter__', return_value=mock_db), \
                 patch.object(mock_db, '__exit__', return_value=False):
            with patch('app.services.digest_scheduler.get_digest_scheduler') as mock_get:
                mock_scheduler = MagicMock()
                mock_get.return_value = mock_scheduler

                await initialize_digest_scheduler()

                mock_scheduler.start.assert_not_called()
                mock_scheduler.schedule_daily_digest.assert_not_called()

    @pytest.mark.asyncio
    async def test_shutdown_digest_scheduler(self):
        """Test shutdown stops scheduler."""
        with patch('app.services.digest_scheduler.get_digest_scheduler') as mock_get:
            mock_scheduler = MagicMock()
            mock_get.return_value = mock_scheduler

            await shutdown_digest_scheduler()

            mock_scheduler.stop.assert_called_once()
