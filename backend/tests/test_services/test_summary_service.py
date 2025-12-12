"""
Unit tests for SummaryService (Story P4-4.1: Summary Generation Service)

Tests:
- AC1: SummaryService exists with generate_summary method
- AC3: Event date range filtering
- AC4: Event grouping by camera, type, time
- AC5: Prompt includes required elements
- AC7: Zero events handling
- AC8: Single event handling
- AC9: Large dataset sampling
- AC10: Statistics included
- AC11: Cost tracking integration
- AC15: Date validation
"""
import json
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.summary_service import (
    SummaryService,
    get_summary_service,
    reset_summary_service,
    SummaryStats,
    SummaryResult,
    MAX_EVENTS_FOR_FULL_DETAIL,
    MAX_EVENTS_FOR_SUMMARY,
)


class TestSummaryServiceInit:
    """Tests for SummaryService initialization (AC1)."""

    def test_service_instantiation(self):
        """Test SummaryService can be instantiated."""
        reset_summary_service()
        service = SummaryService()
        assert service is not None
        assert hasattr(service, 'generate_summary')
        assert hasattr(service, '_cost_tracker')

    def test_singleton_pattern(self):
        """Test get_summary_service returns singleton."""
        reset_summary_service()
        service1 = get_summary_service()
        service2 = get_summary_service()
        assert service1 is service2

    def test_reset_singleton(self):
        """Test reset_summary_service clears singleton."""
        reset_summary_service()
        service1 = get_summary_service()
        reset_summary_service()
        service2 = get_summary_service()
        assert service1 is not service2


class TestEventGrouping:
    """Tests for event grouping logic (AC4)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_summary_service()
        self.service = SummaryService()

    def _create_mock_event(
        self,
        timestamp: datetime,
        camera_id: str = "cam-1",
        objects_detected: list = None,
        alert_triggered: bool = False,
        is_doorbell_ring: bool = False,
        description: str = "Test event"
    ):
        """Create a mock Event object."""
        event = MagicMock()
        event.id = str(uuid.uuid4())
        event.timestamp = timestamp
        event.camera_id = camera_id
        event.objects_detected = json.dumps(objects_detected or ["person"])
        event.alert_triggered = alert_triggered
        event.is_doorbell_ring = is_doorbell_ring
        event.description = description
        return event

    def test_group_events_by_type(self):
        """Test events are grouped by object type."""
        events = [
            self._create_mock_event(
                datetime.now(timezone.utc),
                objects_detected=["person"]
            ),
            self._create_mock_event(
                datetime.now(timezone.utc),
                objects_detected=["person"]
            ),
            self._create_mock_event(
                datetime.now(timezone.utc),
                objects_detected=["vehicle"]
            ),
            self._create_mock_event(
                datetime.now(timezone.utc),
                objects_detected=["package"]
            ),
        ]
        camera_names = {"cam-1": "Front Door"}

        stats = self.service._group_events(events, camera_names)

        assert stats.total_events == 4
        assert stats.by_type["person"] == 2
        assert stats.by_type["vehicle"] == 1
        assert stats.by_type["package"] == 1

    def test_group_events_by_camera(self):
        """Test events are grouped by camera."""
        events = [
            self._create_mock_event(datetime.now(timezone.utc), camera_id="cam-1"),
            self._create_mock_event(datetime.now(timezone.utc), camera_id="cam-1"),
            self._create_mock_event(datetime.now(timezone.utc), camera_id="cam-2"),
        ]
        camera_names = {"cam-1": "Front Door", "cam-2": "Backyard"}

        stats = self.service._group_events(events, camera_names)

        assert stats.by_camera["Front Door"] == 2
        assert stats.by_camera["Backyard"] == 1

    def test_group_events_by_hour(self):
        """Test events are grouped by hour of day."""
        base_time = datetime(2025, 12, 12, 0, 0, 0, tzinfo=timezone.utc)
        events = [
            self._create_mock_event(base_time.replace(hour=8)),  # Morning
            self._create_mock_event(base_time.replace(hour=9)),  # Morning
            self._create_mock_event(base_time.replace(hour=14)),  # Afternoon
            self._create_mock_event(base_time.replace(hour=20)),  # Evening
        ]
        camera_names = {"cam-1": "Camera 1"}

        stats = self.service._group_events(events, camera_names)

        assert stats.by_hour[8] == 1
        assert stats.by_hour[9] == 1
        assert stats.by_hour[14] == 1
        assert stats.by_hour[20] == 1

    def test_track_notable_events(self):
        """Test alerts and doorbell rings are tracked as notable."""
        events = [
            self._create_mock_event(
                datetime.now(timezone.utc),
                alert_triggered=True
            ),
            self._create_mock_event(
                datetime.now(timezone.utc),
                is_doorbell_ring=True
            ),
            self._create_mock_event(datetime.now(timezone.utc)),
        ]
        camera_names = {"cam-1": "Front Door"}

        stats = self.service._group_events(events, camera_names)

        assert stats.alerts_triggered == 1
        assert stats.doorbell_rings == 1
        assert len(stats.notable_events) == 2


class TestEventSampling:
    """Tests for event sampling logic (AC9)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_summary_service()
        self.service = SummaryService()

    def _create_mock_event(
        self,
        timestamp: datetime,
        alert_triggered: bool = False,
        is_doorbell_ring: bool = False,
    ):
        """Create a mock Event object."""
        event = MagicMock()
        event.id = str(uuid.uuid4())
        event.timestamp = timestamp
        event.camera_id = "cam-1"
        event.objects_detected = json.dumps(["person"])
        event.alert_triggered = alert_triggered
        event.is_doorbell_ring = is_doorbell_ring
        event.description = "Test event"
        return event

    def test_no_sampling_under_limit(self):
        """Test no sampling when events under limit."""
        base_time = datetime.now(timezone.utc)
        events = [
            self._create_mock_event(base_time + timedelta(minutes=i))
            for i in range(20)
        ]

        sampled = self.service._sample_events(events, max_events=50)

        assert len(sampled) == 20
        assert sampled == events

    def test_sampling_preserves_important_events(self):
        """Test sampling keeps all alert and doorbell events."""
        base_time = datetime.now(timezone.utc)

        # Create 100 events, with 10 alerts and 5 doorbell rings
        events = []
        for i in range(100):
            is_alert = i < 10
            is_doorbell = 10 <= i < 15
            events.append(self._create_mock_event(
                base_time + timedelta(minutes=i),
                alert_triggered=is_alert,
                is_doorbell_ring=is_doorbell
            ))

        sampled = self.service._sample_events(events, max_events=30)

        # All 15 important events should be kept
        alert_count = sum(1 for e in sampled if e.alert_triggered)
        doorbell_count = sum(1 for e in sampled if e.is_doorbell_ring)

        assert alert_count == 10
        assert doorbell_count == 5

    def test_sampling_keeps_first_and_last(self):
        """Test sampling keeps first and last regular events."""
        base_time = datetime.now(timezone.utc)
        events = [
            self._create_mock_event(base_time + timedelta(minutes=i))
            for i in range(100)
        ]

        sampled = self.service._sample_events(events, max_events=20)

        # First and last should be included
        timestamps = [e.timestamp for e in sampled]
        assert events[0].timestamp in timestamps
        assert events[-1].timestamp in timestamps

    def test_sampling_respects_limit(self):
        """Test sampling doesn't exceed max_events."""
        base_time = datetime.now(timezone.utc)
        events = [
            self._create_mock_event(base_time + timedelta(minutes=i))
            for i in range(200)
        ]

        sampled = self.service._sample_events(events, max_events=50)

        assert len(sampled) <= 50


class TestPromptConstruction:
    """Tests for prompt construction (AC5)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_summary_service()
        self.service = SummaryService()

    def test_prompt_includes_time_context(self):
        """Test prompt includes time period."""
        start = datetime(2025, 12, 12, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 12, 23, 59, 59, tzinfo=timezone.utc)
        stats = SummaryStats(total_events=10, by_type={"person": 5, "vehicle": 5})
        camera_names = {"cam-1": "Front Door"}

        prompt = self.service._build_user_prompt(start, end, stats, camera_names)

        assert "December 12, 2025" in prompt
        assert "10" in prompt  # Total events

    def test_prompt_includes_categories(self):
        """Test prompt includes event categories."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=24)
        stats = SummaryStats(
            total_events=15,
            by_type={"person": 8, "vehicle": 4, "package": 3}
        )
        camera_names = {}

        prompt = self.service._build_user_prompt(start, end, stats, camera_names)

        assert "Person" in prompt
        assert "Vehicle" in prompt
        assert "Package" in prompt
        assert "8" in prompt  # person count

    def test_prompt_includes_camera_breakdown(self):
        """Test prompt includes cameras."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=24)
        stats = SummaryStats(total_events=10)
        camera_names = {"cam-1": "Front Door", "cam-2": "Backyard"}

        prompt = self.service._build_user_prompt(start, end, stats, camera_names)

        assert "Front Door" in prompt or "Backyard" in prompt

    def test_prompt_includes_notable_events(self):
        """Test prompt includes notable events."""
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=24)
        stats = SummaryStats(
            total_events=10,
            notable_events=[
                {"type": "alert", "time": "2:30 PM", "camera": "Front Door", "description": "Alert"}
            ]
        )
        camera_names = {}

        prompt = self.service._build_user_prompt(start, end, stats, camera_names)

        assert "Notable" in prompt
        assert "Alert" in prompt

    def test_system_prompt_requests_narrative(self):
        """Test system prompt instructs narrative format (AC6)."""
        prompt = self.service._build_system_prompt()

        assert "narrative" in prompt.lower() or "natural" in prompt.lower()
        assert "bullet" in prompt.lower()  # Should mention avoiding bullets


class TestEdgeCases:
    """Tests for edge cases (AC7, AC8)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_summary_service()
        self.service = SummaryService()

    def test_zero_events_returns_no_activity(self):
        """Test zero events returns appropriate message without LLM (AC7)."""
        start = datetime(2025, 12, 12, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 12, 12, 23, 59, 59, tzinfo=timezone.utc)

        summary = self.service._generate_no_activity_summary(start, end)

        assert "quiet" in summary.lower() or "no" in summary.lower()
        assert "activity" in summary.lower() or "detected" in summary.lower()

    def test_single_event_uses_event_description(self):
        """Test single event produces simple description (AC8)."""
        event = MagicMock()
        event.timestamp = datetime(2025, 12, 12, 14, 30, 0, tzinfo=timezone.utc)
        event.description = "A person walking up to the front door"
        event.objects_detected = json.dumps(["person"])

        summary = self.service._generate_single_event_summary(event, "Front Door")

        assert "one event" in summary.lower()
        assert "2:30 PM" in summary
        assert "Front Door" in summary

    def test_single_event_without_description(self):
        """Test single event falls back to objects detected."""
        event = MagicMock()
        event.timestamp = datetime.now(timezone.utc)
        event.description = None
        event.objects_detected = json.dumps(["vehicle", "person"])

        summary = self.service._generate_single_event_summary(event, "Driveway")

        assert "one event" in summary.lower()


class TestStatisticsCalculation:
    """Tests for statistics calculation (AC10)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_summary_service()
        self.service = SummaryService()

    def _create_mock_event(self, objects: list = None, alert: bool = False):
        """Create mock event."""
        event = MagicMock()
        event.id = str(uuid.uuid4())
        event.timestamp = datetime.now(timezone.utc)
        event.camera_id = "cam-1"
        event.objects_detected = json.dumps(objects or ["unknown"])
        event.alert_triggered = alert
        event.is_doorbell_ring = False
        event.description = "Test"
        return event

    def test_stats_include_total_events(self):
        """Test stats include total event count."""
        events = [self._create_mock_event() for _ in range(15)]
        camera_names = {"cam-1": "Camera"}

        stats = self.service._group_events(events, camera_names)

        assert stats.total_events == 15

    def test_stats_include_type_breakdown(self):
        """Test stats include breakdown by type."""
        events = [
            self._create_mock_event(objects=["person"]),
            self._create_mock_event(objects=["person"]),
            self._create_mock_event(objects=["vehicle"]),
        ]
        camera_names = {"cam-1": "Camera"}

        stats = self.service._group_events(events, camera_names)

        assert stats.by_type["person"] == 2
        assert stats.by_type["vehicle"] == 1


class TestCostTracking:
    """Tests for cost tracking integration (AC11)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_summary_service()
        self.service = SummaryService()

    def test_service_has_cost_tracker(self):
        """Test service initializes with cost tracker."""
        assert self.service._cost_tracker is not None

    @pytest.mark.asyncio
    async def test_cost_returned_in_result(self):
        """Test AI cost is returned in result."""
        # Mock the AI call to return a cost
        with patch.object(
            self.service,
            '_call_ai_provider',
            new_callable=AsyncMock
        ) as mock_ai:
            mock_ai.return_value = (
                "Test summary",
                "openai",
                100,  # input_tokens
                50,   # output_tokens
                Decimal("0.000045")  # cost
            )

            # Mock database query
            with patch.object(
                self.service,
                '_get_events_for_summary',
                return_value=[MagicMock(
                    id="1",
                    timestamp=datetime.now(timezone.utc),
                    camera_id="cam-1",
                    objects_detected='["person"]',
                    alert_triggered=False,
                    is_doorbell_ring=False,
                    description="Test"
                ), MagicMock(
                    id="2",
                    timestamp=datetime.now(timezone.utc),
                    camera_id="cam-1",
                    objects_detected='["person"]',
                    alert_triggered=False,
                    is_doorbell_ring=False,
                    description="Test 2"
                )]
            ):
                with patch.object(
                    self.service,
                    '_get_camera_names',
                    return_value={"cam-1": "Front Door"}
                ):
                    mock_db = MagicMock()
                    result = await self.service.generate_summary(
                        mock_db,
                        datetime.now(timezone.utc) - timedelta(hours=24),
                        datetime.now(timezone.utc)
                    )

                    assert result.ai_cost == Decimal("0.000045")
                    assert result.provider_used == "openai"


class TestGenerateSummary:
    """Integration tests for generate_summary method."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_summary_service()
        self.service = SummaryService()

    @pytest.mark.asyncio
    async def test_generate_summary_zero_events(self):
        """Test generate_summary with zero events (AC7)."""
        with patch.object(
            self.service,
            '_get_events_for_summary',
            return_value=[]
        ):
            mock_db = MagicMock()
            result = await self.service.generate_summary(
                mock_db,
                datetime.now(timezone.utc) - timedelta(hours=24),
                datetime.now(timezone.utc)
            )

            assert result.success is True
            assert result.event_count == 0
            assert "quiet" in result.summary_text.lower() or "no" in result.summary_text.lower()
            assert result.ai_cost == Decimal("0")  # No LLM call

    @pytest.mark.asyncio
    async def test_generate_summary_single_event(self):
        """Test generate_summary with single event (AC8)."""
        mock_event = MagicMock()
        mock_event.id = "evt-1"
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_event.camera_id = "cam-1"
        mock_event.objects_detected = json.dumps(["person"])
        mock_event.alert_triggered = False
        mock_event.is_doorbell_ring = False
        mock_event.description = "A person at the door"

        with patch.object(
            self.service,
            '_get_events_for_summary',
            return_value=[mock_event]
        ):
            with patch.object(
                self.service,
                '_get_camera_names',
                return_value={"cam-1": "Front Door"}
            ):
                mock_db = MagicMock()
                result = await self.service.generate_summary(
                    mock_db,
                    datetime.now(timezone.utc) - timedelta(hours=24),
                    datetime.now(timezone.utc)
                )

                assert result.success is True
                assert result.event_count == 1
                assert "one event" in result.summary_text.lower()
                assert result.ai_cost == Decimal("0")  # No LLM call

    @pytest.mark.asyncio
    async def test_generate_summary_multiple_events(self):
        """Test generate_summary with multiple events."""
        mock_events = []
        base_time = datetime.now(timezone.utc)
        for i in range(10):
            event = MagicMock()
            event.id = f"evt-{i}"
            event.timestamp = base_time - timedelta(hours=i)
            event.camera_id = "cam-1"
            event.objects_detected = json.dumps(["person"])
            event.alert_triggered = False
            event.is_doorbell_ring = False
            event.description = f"Event {i}"
            mock_events.append(event)

        with patch.object(
            self.service,
            '_get_events_for_summary',
            return_value=mock_events
        ):
            with patch.object(
                self.service,
                '_get_camera_names',
                return_value={"cam-1": "Front Door"}
            ):
                with patch.object(
                    self.service,
                    '_call_ai_provider',
                    new_callable=AsyncMock
                ) as mock_ai:
                    mock_ai.return_value = (
                        "Today was a busy day with multiple visitors.",
                        "openai",
                        200,
                        100,
                        Decimal("0.0001")
                    )

                    mock_db = MagicMock()
                    result = await self.service.generate_summary(
                        mock_db,
                        base_time - timedelta(hours=24),
                        base_time
                    )

                    assert result.success is True
                    assert result.event_count == 10
                    assert result.provider_used == "openai"
                    mock_ai.assert_called_once()


class TestMethodSignature:
    """Tests for method signature compliance (AC1)."""

    def test_generate_summary_signature(self):
        """Test generate_summary has correct signature."""
        import inspect

        reset_summary_service()
        service = SummaryService()
        sig = inspect.signature(service.generate_summary)

        params = list(sig.parameters.keys())
        assert "db" in params
        assert "start_time" in params
        assert "end_time" in params
        assert "camera_ids" in params

        # camera_ids should be optional
        assert sig.parameters["camera_ids"].default is None
