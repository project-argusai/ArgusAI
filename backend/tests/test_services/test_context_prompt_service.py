"""
Unit tests for ContextEnhancedPromptService (Story P4-3.4: Context-Enhanced AI Prompts)

Tests:
- AC1: Service retrieves context from EntityService and SimilarityService
- AC2: Entity context formatted naturally (name, occurrence count, dates)
- AC3: Similar events context formatted (count, similarity %, recency)
- AC4: Time pattern context included when relevant
- AC5: Settings control context enhancement (enable/disable)
- AC6: A/B test logic skips context at configured percentage
- AC7: Graceful degradation when context retrieval fails
- AC8: Context appended to base prompt in consistent format
- AC9: Performance: Context building <100ms (AC10 via graceful fallback)
"""
import json
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.context_prompt_service import (
    ContextEnhancedPromptService,
    ContextEnhancedPromptResult,
    get_context_prompt_service,
    reset_context_prompt_service,
)
from app.services.entity_service import EntityMatchResult
from app.services.similarity_service import SimilarEvent


class TestContextEnhancedPromptResult:
    """Tests for ContextEnhancedPromptResult dataclass."""

    def test_create_result_with_context(self):
        """Test creating result with context included."""
        result = ContextEnhancedPromptResult(
            prompt="Enhanced prompt with context",
            context_included=True,
            entity_context_included=True,
            similar_events_count=5,
            time_pattern_included=True,
            context_gather_time_ms=45.5,
            entity_name="John",
            entity_occurrence_count=10,
            similarity_scores=[0.95, 0.88, 0.82],
        )

        assert result.context_included is True
        assert result.entity_context_included is True
        assert result.similar_events_count == 5
        assert result.time_pattern_included is True
        assert result.entity_name == "John"
        assert result.entity_occurrence_count == 10
        assert len(result.similarity_scores) == 3

    def test_create_result_without_context(self):
        """Test creating result without context."""
        result = ContextEnhancedPromptResult(
            prompt="Base prompt only",
            context_included=False,
        )

        assert result.context_included is False
        assert result.ab_test_skip is False
        assert result.entity_context_included is False
        assert result.similar_events_count == 0
        assert result.time_pattern_included is False

    def test_ab_test_skip_flag(self):
        """Test A/B test skip flag."""
        result = ContextEnhancedPromptResult(
            prompt="Base prompt",
            context_included=False,
            ab_test_skip=True,
        )

        assert result.ab_test_skip is True
        assert result.context_included is False


class TestContextEnhancedPromptServiceInit:
    """Tests for service initialization."""

    def test_init_with_default_services(self):
        """Test initialization creates default services."""
        with patch('app.services.context_prompt_service.get_entity_service') as mock_entity:
            with patch('app.services.context_prompt_service.get_similarity_service') as mock_sim:
                mock_entity.return_value = MagicMock()
                mock_sim.return_value = MagicMock()

                service = ContextEnhancedPromptService()

                assert service._entity_service is not None
                assert service._similarity_service is not None

    def test_init_with_custom_services(self):
        """Test initialization with custom services."""
        mock_entity = MagicMock()
        mock_similarity = MagicMock()

        service = ContextEnhancedPromptService(
            entity_service=mock_entity,
            similarity_service=mock_similarity,
        )

        assert service._entity_service == mock_entity
        assert service._similarity_service == mock_similarity

    def test_default_constants(self):
        """Test default constants are set correctly."""
        assert ContextEnhancedPromptService.DEFAULT_SIMILARITY_THRESHOLD == 0.7
        assert ContextEnhancedPromptService.DEFAULT_TIME_WINDOW_DAYS == 30


class TestContextEnhancedPromptServiceSingleton:
    """Tests for singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_context_prompt_service()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_context_prompt_service()

    def test_get_context_prompt_service_creates_singleton(self):
        """Test singleton creation."""
        with patch('app.services.context_prompt_service.get_entity_service'):
            with patch('app.services.context_prompt_service.get_similarity_service'):
                service1 = get_context_prompt_service()
                service2 = get_context_prompt_service()

                assert service1 is service2

    def test_reset_clears_singleton(self):
        """Test reset clears singleton."""
        with patch('app.services.context_prompt_service.get_entity_service'):
            with patch('app.services.context_prompt_service.get_similarity_service'):
                service1 = get_context_prompt_service()
                reset_context_prompt_service()
                service2 = get_context_prompt_service()

                assert service1 is not service2


class TestEntityContextFormatting:
    """Tests for entity context formatting (AC2)."""

    def setup_method(self):
        """Setup test service."""
        self.service = ContextEnhancedPromptService(
            entity_service=MagicMock(),
            similarity_service=MagicMock(),
        )

    def test_format_entity_with_name(self):
        """Test formatting entity with a user-assigned name."""
        now = datetime.now(timezone.utc)
        entity = EntityMatchResult(
            entity_id="test-id",
            entity_type="person",
            name="John",
            first_seen_at=now - timedelta(days=30),
            last_seen_at=now - timedelta(days=1),
            occurrence_count=15,
            similarity_score=0.92,
            is_new=False,
        )

        result = self.service._format_entity_context(entity)

        assert 'Known visitor: "John"' in result
        assert "(named by user)" in result
        assert "15 times total" in result

    def test_format_entity_without_name(self):
        """Test formatting entity without a name."""
        now = datetime.now(timezone.utc)
        entity = EntityMatchResult(
            entity_id="test-id",
            entity_type="person",
            name=None,
            first_seen_at=now - timedelta(days=7),
            last_seen_at=now - timedelta(hours=2),
            occurrence_count=5,
            similarity_score=0.85,
            is_new=False,
        )

        result = self.service._format_entity_context(entity)

        # Unnamed matches must not be injected as prompt names
        assert result is None

    def test_format_entity_first_visit(self):
        """Test formatting entity on first visit."""
        now = datetime.now(timezone.utc)
        entity = EntityMatchResult(
            entity_id="test-id",
            entity_type="person",
            name="Isaac",
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            similarity_score=1.0,
            is_new=True,
        )

        result = self.service._format_entity_context(entity)

        assert "first recorded visit" in result

    def test_format_entity_second_visit(self):
        """Test formatting entity on second visit."""
        now = datetime.now(timezone.utc)
        entity = EntityMatchResult(
            entity_id="test-id",
            entity_type="vehicle",
            name="Red BMW",
            first_seen_at=now - timedelta(days=3),
            last_seen_at=now,
            occurrence_count=2,
            similarity_score=0.88,
            is_new=False,
        )

        result = self.service._format_entity_context(entity)

        assert "Seen once before" in result

    def test_format_entity_returns_none_for_none_input(self):
        """Test that None input returns None."""
        result = self.service._format_entity_context(None)
        assert result is None


class TestSimilarityContextFormatting:
    """Tests for similar events context formatting (AC3)."""

    def setup_method(self):
        """Setup test service."""
        self.service = ContextEnhancedPromptService(
            entity_service=MagicMock(),
            similarity_service=MagicMock(),
        )

    def test_format_similarity_with_high_match(self):
        """Test formatting with very high similarity (>90%)."""
        now = datetime.now(timezone.utc)
        similar_events = [
            SimilarEvent(
                event_id="e1",
                similarity_score=0.95,
                timestamp=now - timedelta(hours=2),
                description="Delivery person at door",
                camera_id="cam1",
                thumbnail_url=None,
                camera_name="Front Door",
            ),
            SimilarEvent(
                event_id="e2",
                similarity_score=0.88,
                timestamp=now - timedelta(days=1),
                description="Package delivery",
                camera_id="cam1",
                thumbnail_url=None,
                camera_name="Front Door",
            ),
        ]

        result = self.service._format_similarity_context(similar_events, 30)

        assert "2 occurrences" in result
        assert "95%" in result
        assert "very similar" in result

    def test_format_similarity_with_moderate_match(self):
        """Test formatting with moderate similarity (80-90%)."""
        now = datetime.now(timezone.utc)
        similar_events = [
            SimilarEvent(
                event_id="e1",
                similarity_score=0.85,
                timestamp=now - timedelta(days=3),
                description="Person walking",
                camera_id="cam1",
                thumbnail_url=None,
                camera_name="Front Door",
            ),
        ]

        result = self.service._format_similarity_context(similar_events, 30)

        assert "1 occurrences" in result
        assert "85%" in result
        assert "quite similar" in result

    def test_format_similarity_returns_none_for_empty_list(self):
        """Test that empty list returns None."""
        result = self.service._format_similarity_context([], 30)
        assert result is None

    def test_format_similarity_includes_type_summary(self):
        """Test that event type summary is included when applicable."""
        now = datetime.now(timezone.utc)
        similar_events = [
            SimilarEvent(
                event_id=f"e{i}",
                similarity_score=0.8,
                timestamp=now - timedelta(hours=i),
                description=f"Package delivery {i}",
                camera_id="cam1",
                thumbnail_url=None,
                camera_name="Front Door",
            )
            for i in range(5)
        ]

        result = self.service._format_similarity_context(similar_events, 30)

        assert "delivery" in result.lower() or "Mostly" in result


class TestTimePatternContext:
    """Tests for time pattern context (AC4)."""

    def setup_method(self):
        """Setup test service."""
        self.service = ContextEnhancedPromptService(
            entity_service=MagicMock(),
            similarity_service=MagicMock(),
        )

    def test_format_relative_date_just_now(self):
        """Test 'just now' formatting."""
        now = datetime.now(timezone.utc)
        result = self.service._format_relative_date(now - timedelta(minutes=5))
        assert "just now" in result

    def test_format_relative_date_hours_ago(self):
        """Test 'X hours ago' formatting."""
        now = datetime.now(timezone.utc)
        result = self.service._format_relative_date(now - timedelta(hours=3))
        assert "3 hours ago" in result

    def test_format_relative_date_yesterday(self):
        """Test 'yesterday' formatting."""
        now = datetime.now(timezone.utc)
        result = self.service._format_relative_date(now - timedelta(days=1))
        assert "yesterday" in result

    def test_format_relative_date_days_ago(self):
        """Test 'X days ago' formatting."""
        now = datetime.now(timezone.utc)
        result = self.service._format_relative_date(now - timedelta(days=5))
        assert "5 days ago" in result

    def test_format_relative_date_weeks_ago(self):
        """Test 'X weeks ago' formatting."""
        now = datetime.now(timezone.utc)
        result = self.service._format_relative_date(now - timedelta(days=14))
        assert "2 weeks ago" in result

    def test_format_relative_date_months_ago(self):
        """Test 'X months ago' formatting."""
        now = datetime.now(timezone.utc)
        result = self.service._format_relative_date(now - timedelta(days=60))
        assert "2 months ago" in result

    def test_format_time_range_morning(self):
        """Test morning time range."""
        result = self.service._format_time_range(9)
        assert "morning" in result.lower()

    def test_format_time_range_afternoon(self):
        """Test afternoon time range."""
        result = self.service._format_time_range(15)
        assert "afternoon" in result.lower()

    def test_format_time_range_evening(self):
        """Test evening time range."""
        result = self.service._format_time_range(19)
        assert "evening" in result.lower()


class TestSettingsRetrieval:
    """Tests for settings retrieval (AC5, AC6)."""

    def setup_method(self):
        """Setup test service."""
        self.service = ContextEnhancedPromptService(
            entity_service=MagicMock(),
            similarity_service=MagicMock(),
        )

    def test_context_enabled_by_default(self):
        """Test that context is enabled by default."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = self.service._is_context_enabled(mock_db)
        assert result is True

    def test_context_disabled_when_setting_false(self):
        """Test context disabled when setting is 'false'."""
        mock_db = MagicMock()
        mock_setting = MagicMock()
        mock_setting.value = "false"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        result = self.service._is_context_enabled(mock_db)
        assert result is False

    def test_context_disabled_when_setting_disabled(self):
        """Test context disabled when setting is 'disabled'."""
        mock_db = MagicMock()
        mock_setting = MagicMock()
        mock_setting.value = "disabled"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        result = self.service._is_context_enabled(mock_db)
        assert result is False

    def test_ab_test_percentage_default_zero(self):
        """Test A/B test percentage defaults to 0."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = self.service._get_ab_test_percentage(mock_db)
        assert result == 0

    def test_ab_test_percentage_from_setting(self):
        """Test A/B test percentage from setting."""
        mock_db = MagicMock()
        mock_setting = MagicMock()
        mock_setting.value = "20"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        result = self.service._get_ab_test_percentage(mock_db)
        assert result == 20

    def test_ab_test_percentage_clamped_to_100(self):
        """Test A/B test percentage clamped to max 100."""
        mock_db = MagicMock()
        mock_setting = MagicMock()
        mock_setting.value = "150"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        result = self.service._get_ab_test_percentage(mock_db)
        assert result == 100

    def test_similarity_threshold_default(self):
        """Test similarity threshold defaults to 0.7."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = self.service._get_similarity_threshold(mock_db)
        assert result == 0.7

    def test_similarity_threshold_from_setting(self):
        """Test similarity threshold from setting."""
        mock_db = MagicMock()
        mock_setting = MagicMock()
        mock_setting.value = "0.85"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        result = self.service._get_similarity_threshold(mock_db)
        assert result == 0.85

    def test_time_window_days_default(self):
        """Test time window defaults to 30 days."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = self.service._get_time_window_days(mock_db)
        assert result == 30


class TestBuildContextEnhancedPrompt:
    """Tests for the main build_context_enhanced_prompt method."""

    def setup_method(self):
        """Setup test service with mocked dependencies."""
        self.mock_entity_service = MagicMock()
        self.mock_similarity_service = MagicMock()
        self.mock_similarity_service.find_similar_events = AsyncMock(return_value=[])

        self.service = ContextEnhancedPromptService(
            entity_service=self.mock_entity_service,
            similarity_service=self.mock_similarity_service,
        )

    @pytest.mark.asyncio
    async def test_returns_base_prompt_when_disabled(self):
        """Test returns base prompt when context is disabled (AC5)."""
        mock_db = MagicMock()
        mock_setting = MagicMock()
        mock_setting.value = "false"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_setting

        base_prompt = "Describe the image"

        result = await self.service.build_context_enhanced_prompt(
            db=mock_db,
            event_id=str(uuid.uuid4()),
            base_prompt=base_prompt,
            camera_id=str(uuid.uuid4()),
            event_time=datetime.now(timezone.utc),
        )

        assert result.prompt == base_prompt
        assert result.context_included is False
        assert result.ab_test_skip is False

    @pytest.mark.asyncio
    async def test_ab_test_skip(self):
        """Test A/B test skip behavior (AC6)."""
        mock_db = MagicMock()

        # Configure settings: enabled with 100% skip rate
        def setting_side_effect(*args, **kwargs):
            mock_setting = MagicMock()
            # Check which key is being queried
            filter_call = mock_db.query.return_value.filter.call_args
            if filter_call:
                # Return different values based on key
                if "enable_context" in str(filter_call):
                    return None  # Default to enabled
                elif "ab_test" in str(filter_call):
                    mock_setting.value = "100"  # 100% skip
                    return mock_setting
            return None

        mock_db.query.return_value.filter.return_value.first.side_effect = setting_side_effect

        base_prompt = "Describe the image"

        # With 100% skip rate, should always skip
        with patch.object(self.service, '_get_ab_test_percentage', return_value=100):
            with patch.object(self.service, '_is_context_enabled', return_value=True):
                result = await self.service.build_context_enhanced_prompt(
                    db=mock_db,
                    event_id=str(uuid.uuid4()),
                    base_prompt=base_prompt,
                    camera_id=str(uuid.uuid4()),
                    event_time=datetime.now(timezone.utc),
                )

        assert result.ab_test_skip is True
        assert result.context_included is False

    @pytest.mark.asyncio
    async def test_includes_entity_context_when_matched(self):
        """Test entity context is included when entity is matched (AC2)."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0

        now = datetime.now(timezone.utc)
        matched_entity = EntityMatchResult(
            entity_id="entity-1",
            entity_type="person",
            name="Delivery Driver",
            first_seen_at=now - timedelta(days=30),
            last_seen_at=now - timedelta(days=1),
            occurrence_count=10,
            similarity_score=0.92,
            is_new=False,
        )

        base_prompt = "Describe the image"

        result = await self.service.build_context_enhanced_prompt(
            db=mock_db,
            event_id=str(uuid.uuid4()),
            base_prompt=base_prompt,
            camera_id=str(uuid.uuid4()),
            event_time=now,
            matched_entity=matched_entity,
        )

        assert result.context_included is True
        assert result.entity_context_included is True
        assert result.entity_name == "Delivery Driver"
        assert "Delivery Driver" in result.prompt
        assert "HISTORICAL CONTEXT:" in result.prompt

    @pytest.mark.asyncio
    async def test_includes_similar_events_context(self):
        """Test similar events context is included (AC3)."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0

        now = datetime.now(timezone.utc)
        similar_events = [
            SimilarEvent(
                event_id="e1",
                similarity_score=0.88,
                timestamp=now - timedelta(hours=5),
                description="Person at door",
                camera_id="cam1",
                thumbnail_url=None,
                camera_name="Front Door",
            ),
            SimilarEvent(
                event_id="e2",
                similarity_score=0.82,
                timestamp=now - timedelta(days=2),
                description="Visitor arriving",
                camera_id="cam1",
                thumbnail_url=None,
                camera_name="Front Door",
            ),
        ]

        self.mock_similarity_service.find_similar_events = AsyncMock(return_value=similar_events)

        base_prompt = "Describe the image"

        result = await self.service.build_context_enhanced_prompt(
            db=mock_db,
            event_id=str(uuid.uuid4()),
            base_prompt=base_prompt,
            camera_id=str(uuid.uuid4()),
            event_time=now,
        )

        assert result.context_included is True
        assert result.similar_events_count == 2
        assert len(result.similarity_scores) == 2
        assert "HISTORICAL CONTEXT:" in result.prompt

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_similarity_error(self):
        """Test graceful degradation when similarity service fails (AC7)."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0

        # Make similarity service raise an error
        self.mock_similarity_service.find_similar_events = AsyncMock(
            side_effect=Exception("Similarity service unavailable")
        )

        base_prompt = "Describe the image"

        # Should not raise, should return without similarity context
        result = await self.service.build_context_enhanced_prompt(
            db=mock_db,
            event_id=str(uuid.uuid4()),
            base_prompt=base_prompt,
            camera_id=str(uuid.uuid4()),
            event_time=datetime.now(timezone.utc),
        )

        # Should still work, just without similarity context
        assert result.similar_events_count == 0
        assert result.prompt  # Should have some prompt

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_no_embedding(self):
        """Test graceful degradation when no embedding exists (AC7)."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0

        # Make similarity service raise ValueError (no embedding)
        self.mock_similarity_service.find_similar_events = AsyncMock(
            side_effect=ValueError("No embedding for event")
        )

        base_prompt = "Describe the image"

        result = await self.service.build_context_enhanced_prompt(
            db=mock_db,
            event_id=str(uuid.uuid4()),
            base_prompt=base_prompt,
            camera_id=str(uuid.uuid4()),
            event_time=datetime.now(timezone.utc),
        )

        # Should still work without error
        assert result.similar_events_count == 0

    @pytest.mark.asyncio
    async def test_context_format_consistent(self):
        """Test context is appended in consistent format (AC8)."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.scalar.return_value = 0

        now = datetime.now(timezone.utc)
        matched_entity = EntityMatchResult(
            entity_id="entity-1",
            entity_type="person",
            name="Test Person",
            first_seen_at=now - timedelta(days=7),
            last_seen_at=now - timedelta(days=1),
            occurrence_count=5,
            similarity_score=0.9,
            is_new=False,
        )

        base_prompt = "Describe the image"

        result = await self.service.build_context_enhanced_prompt(
            db=mock_db,
            event_id=str(uuid.uuid4()),
            base_prompt=base_prompt,
            camera_id=str(uuid.uuid4()),
            event_time=now,
            matched_entity=matched_entity,
        )

        # Check format structure
        assert "HISTORICAL CONTEXT:" in result.prompt
        assert "- " in result.prompt  # Bullet points
        assert "Use HISTORICAL CONTEXT names" in result.prompt
        assert "name the carrier" in result.prompt
        # Base prompt should come first
        assert result.prompt.index(base_prompt) < result.prompt.index("HISTORICAL CONTEXT:")
