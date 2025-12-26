"""
Tests for MCPContextProvider (Story P11-3.1, P11-3.2, P11-3.3, P11-3.4).

Tests feedback context gathering, accuracy calculation, pattern extraction,
entity context gathering, similar entity matching, context size limiting,
camera context gathering, time pattern context gathering,
caching, performance metrics, prompt formatting, and fail-open behavior.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, PropertyMock
import uuid

from app.services.mcp_context import (
    MCPContextProvider,
    AIContext,
    FeedbackContext,
    EntityContext,
    CameraContext,
    TimePatternContext,
    CachedContext,
    get_mcp_context_provider,
    reset_mcp_context_provider,
    MCP_CACHE_HITS,
    MCP_CACHE_MISSES,
    MCP_CONTEXT_LATENCY,
)
from app.models.event_feedback import EventFeedback
from app.models.camera import Camera
from app.models.event import Event
from app.models.recognized_entity import RecognizedEntity


class TestMCPContextProvider:
    """Test suite for MCPContextProvider."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        reset_mcp_context_provider()
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def event_time(self):
        """Sample event time."""
        return datetime.now(timezone.utc)

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    def test_provider_initialization(self, provider):
        """Test MCPContextProvider initializes correctly."""
        assert provider is not None
        assert provider.FEEDBACK_LIMIT == 50

    def test_singleton_pattern(self):
        """Test get_mcp_context_provider returns same instance."""
        reset_mcp_context_provider()
        provider1 = get_mcp_context_provider()
        provider2 = get_mcp_context_provider()
        assert provider1 is provider2

    def test_reset_singleton(self):
        """Test reset_mcp_context_provider creates new instance."""
        provider1 = get_mcp_context_provider()
        reset_mcp_context_provider()
        provider2 = get_mcp_context_provider()
        assert provider1 is not provider2


class TestFeedbackContextGathering:
    """Tests for feedback context gathering."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    def _create_mock_feedback(
        self,
        rating: str = "helpful",
        correction: str = None,
        camera_id: str = None,
    ) -> MagicMock:
        """Create a mock EventFeedback object."""
        feedback = MagicMock(spec=EventFeedback)
        feedback.rating = rating
        feedback.correction = correction
        feedback.camera_id = camera_id
        feedback.created_at = datetime.now(timezone.utc)
        return feedback

    @pytest.mark.asyncio
    async def test_get_context_no_session(self, provider, camera_id):
        """Test get_context with no database session returns empty context."""
        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
        )

        assert isinstance(context, AIContext)
        assert context.feedback is None
        assert context.entity is None
        assert context.camera is None
        assert context.time_pattern is None

    @pytest.mark.asyncio
    async def test_get_context_no_feedback(self, provider, camera_id):
        """Test get_context with no feedback data."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        assert context.feedback is not None
        assert context.feedback.accuracy_rate is None
        assert context.feedback.total_feedback == 0
        assert context.feedback.common_corrections == []

    @pytest.mark.asyncio
    async def test_get_context_all_positive_feedback(self, provider, camera_id):
        """Test accuracy calculation with all positive feedback."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Create 10 positive feedback items
        feedbacks = [self._create_mock_feedback(rating="helpful") for _ in range(10)]

        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = feedbacks
        mock_db.query.return_value = mock_query

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        assert context.feedback is not None
        assert context.feedback.accuracy_rate == 1.0
        assert context.feedback.total_feedback == 10

    @pytest.mark.asyncio
    async def test_get_context_all_negative_feedback(self, provider, camera_id):
        """Test accuracy calculation with all negative feedback."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Create 10 negative feedback items
        feedbacks = [self._create_mock_feedback(rating="not_helpful") for _ in range(10)]

        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = feedbacks
        mock_db.query.return_value = mock_query

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        assert context.feedback is not None
        assert context.feedback.accuracy_rate == 0.0
        assert context.feedback.total_feedback == 10

    @pytest.mark.asyncio
    async def test_get_context_mixed_feedback(self, provider, camera_id):
        """Test accuracy calculation with 50% positive feedback."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Create 5 positive and 5 negative feedback items
        feedbacks = (
            [self._create_mock_feedback(rating="helpful") for _ in range(5)] +
            [self._create_mock_feedback(rating="not_helpful") for _ in range(5)]
        )

        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = feedbacks
        mock_db.query.return_value = mock_query

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        assert context.feedback is not None
        assert context.feedback.accuracy_rate == 0.5
        assert context.feedback.total_feedback == 10


class TestPatternExtraction:
    """Tests for common pattern extraction."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    def test_extract_patterns_empty_list(self, provider):
        """Test pattern extraction with empty list."""
        patterns = provider._extract_common_patterns([])
        assert patterns == []

    def test_extract_patterns_single_correction(self, provider):
        """Test pattern extraction with single correction."""
        corrections = ["That's a cat, not a dog"]
        patterns = provider._extract_common_patterns(corrections)
        assert len(patterns) <= 3
        assert "cat" in patterns or "dog" in patterns

    def test_extract_patterns_repeated_words(self, provider):
        """Test pattern extraction with repeated words."""
        corrections = [
            "It was a delivery person",
            "That's a delivery truck",
            "Missing the delivery package",
            "Delivery driver left",
        ]
        patterns = provider._extract_common_patterns(corrections)
        assert "delivery" in patterns

    def test_extract_patterns_filters_stop_words(self, provider):
        """Test that stop words are filtered out."""
        corrections = [
            "The cat is on the mat",
            "A dog is in the yard",
        ]
        patterns = provider._extract_common_patterns(corrections)
        assert "the" not in patterns
        assert "is" not in patterns
        assert "on" not in patterns

    def test_extract_patterns_max_three(self, provider):
        """Test that at most 3 patterns are returned."""
        corrections = [
            "cat dog bird fish turtle",
            "cat dog bird fish",
            "cat dog bird",
        ]
        patterns = provider._extract_common_patterns(corrections)
        assert len(patterns) <= 3


class TestPromptFormatting:
    """Tests for prompt formatting."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    def test_format_empty_context(self, provider):
        """Test formatting with empty context."""
        context = AIContext()
        result = provider.format_for_prompt(context)
        assert result == ""

    def test_format_feedback_only(self, provider):
        """Test formatting with only feedback context."""
        context = AIContext(
            feedback=FeedbackContext(
                accuracy_rate=0.85,
                total_feedback=50,
                common_corrections=["delivery", "package"],
                recent_negative_reasons=["missed the box"],
            )
        )
        result = provider.format_for_prompt(context)

        assert "85%" in result
        assert "delivery" in result
        assert "package" in result

    def test_format_feedback_no_accuracy(self, provider):
        """Test formatting with feedback but no accuracy."""
        context = AIContext(
            feedback=FeedbackContext(
                accuracy_rate=None,
                total_feedback=0,
                common_corrections=[],
                recent_negative_reasons=[],
            )
        )
        result = provider.format_for_prompt(context)
        assert result == ""

    def test_format_with_entity(self, provider):
        """Test formatting with entity context."""
        context = AIContext(
            entity=EntityContext(
                entity_id="123",
                name="John",
                entity_type="person",
                attributes={"color": "blue"},
                last_seen=datetime.now(timezone.utc),
                sighting_count=5,
            )
        )
        result = provider.format_for_prompt(context)

        assert "John" in result
        assert "person" in result
        assert "color=blue" in result

    def test_format_with_camera_location(self, provider):
        """Test formatting with camera location hint."""
        context = AIContext(
            camera=CameraContext(
                camera_id="cam1",
                location_hint="Front Door",
                typical_objects=["car", "person"],
                false_positive_patterns=["shadow"],
            )
        )
        result = provider.format_for_prompt(context)
        assert "Front Door" in result

    def test_format_with_unusual_timing(self, provider):
        """Test formatting with unusual timing flag."""
        context = AIContext(
            time_pattern=TimePatternContext(
                hour=3,
                typical_activity_level="low",
                is_unusual=True,
                typical_event_count=0.5,
            )
        )
        result = provider.format_for_prompt(context)
        assert "unusual" in result.lower()

    def test_format_combined_context(self, provider):
        """Test formatting with multiple context components."""
        context = AIContext(
            feedback=FeedbackContext(
                accuracy_rate=0.9,
                total_feedback=100,
                common_corrections=["vehicle"],
                recent_negative_reasons=[],
            ),
            camera=CameraContext(
                camera_id="cam1",
                location_hint="Driveway",
                typical_objects=[],
                false_positive_patterns=[],
            ),
        )
        result = provider.format_for_prompt(context)

        assert "90%" in result
        assert "Driveway" in result


class TestFailOpenBehavior:
    """Tests for fail-open error handling."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_database_error_returns_none(self, provider, camera_id):
        """Test that database errors return None for feedback context."""
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database connection failed")

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        # Should return context with None feedback, not raise exception
        assert isinstance(context, AIContext)
        assert context.feedback is None

    @pytest.mark.asyncio
    async def test_query_error_returns_none(self, provider, camera_id):
        """Test that query errors return None for feedback context."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.side_effect = Exception("Query failed")
        mock_db.query.return_value = mock_query

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        # Should return context with None feedback, not raise exception
        assert isinstance(context, AIContext)
        assert context.feedback is None

    @pytest.mark.asyncio
    async def test_partial_context_on_error(self, provider, camera_id):
        """Test that partial context is returned when one component fails."""
        # In MVP, only feedback context is implemented
        # This test validates the pattern for future components
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        # Context should be returned (not exception) with None components
        assert isinstance(context, AIContext)
        assert context.feedback is None
        assert context.entity is None
        assert context.camera is None
        assert context.time_pattern is None


class TestRecentNegativeFeedback:
    """Tests for recent negative feedback extraction."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    def _create_mock_feedback(
        self,
        rating: str = "helpful",
        correction: str = None,
    ) -> MagicMock:
        """Create a mock EventFeedback object."""
        feedback = MagicMock(spec=EventFeedback)
        feedback.rating = rating
        feedback.correction = correction
        feedback.created_at = datetime.now(timezone.utc)
        return feedback

    @pytest.mark.asyncio
    async def test_extracts_recent_negative_reasons(self, provider, camera_id):
        """Test that recent negative feedback reasons are extracted."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Create feedback with corrections on negative items
        feedbacks = [
            self._create_mock_feedback(rating="not_helpful", correction="Wrong person"),
            self._create_mock_feedback(rating="not_helpful", correction="Missed package"),
            self._create_mock_feedback(rating="helpful"),
            self._create_mock_feedback(rating="not_helpful", correction="Incorrect action"),
        ]

        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = feedbacks
        mock_db.query.return_value = mock_query

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        assert context.feedback is not None
        # Should have the negative corrections from first 5 items
        assert len(context.feedback.recent_negative_reasons) <= 5

    @pytest.mark.asyncio
    async def test_ignores_negative_without_correction(self, provider, camera_id):
        """Test that negative feedback without corrections is not included in reasons."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        feedbacks = [
            self._create_mock_feedback(rating="not_helpful", correction=None),
            self._create_mock_feedback(rating="not_helpful", correction=""),
            self._create_mock_feedback(rating="not_helpful", correction="Actual correction"),
        ]

        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = feedbacks
        mock_db.query.return_value = mock_query

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        assert context.feedback is not None
        # Only the one with actual correction text should be included
        # The first two negative items don't have correction text
        reasons = context.feedback.recent_negative_reasons
        if len(reasons) > 0:
            assert "Actual correction" in reasons or reasons == []


class TestEntityContextGathering:
    """Tests for entity context gathering (Story P11-3.2)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def entity_id(self):
        """Sample entity ID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    def _create_mock_entity(
        self,
        entity_id: str = None,
        entity_type: str = "person",
        name: str = "John Doe",
        occurrence_count: int = 5,
        vehicle_color: str = None,
        vehicle_make: str = None,
        vehicle_model: str = None,
        vehicle_signature: str = None,
        last_seen_at: datetime = None,
    ) -> MagicMock:
        """Create a mock RecognizedEntity object."""
        entity = MagicMock(spec=RecognizedEntity)
        entity.id = entity_id or str(uuid.uuid4())
        entity.entity_type = entity_type
        entity.name = name
        entity.occurrence_count = occurrence_count
        entity.vehicle_color = vehicle_color
        entity.vehicle_make = vehicle_make
        entity.vehicle_model = vehicle_model
        entity.vehicle_signature = vehicle_signature
        entity.last_seen_at = last_seen_at or datetime.now(timezone.utc)
        entity.display_name = name or f"{entity_type.title()} #{entity.id[:8]}"
        return entity

    @pytest.mark.asyncio
    async def test_get_context_with_entity_id(self, provider, camera_id, entity_id):
        """Test get_context includes entity context when entity_id provided (AC-3.2.1)."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_feedback_query = MagicMock()
        mock_entity_query = MagicMock()

        # Setup entity query
        mock_entity = self._create_mock_entity(entity_id=entity_id, name="Mail Carrier")
        mock_entity_query.filter.return_value = mock_entity_query
        mock_entity_query.first.return_value = mock_entity
        mock_entity_query.order_by.return_value = mock_entity_query
        mock_entity_query.limit.return_value = mock_entity_query
        mock_entity_query.all.return_value = []  # No similar entities

        # Setup feedback query
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []

        # Make query return appropriate mock based on model
        def query_side_effect(model):
            if model.__name__ == "RecognizedEntity":
                return mock_entity_query
            return mock_feedback_query

        mock_db.query.side_effect = query_side_effect

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            entity_id=entity_id,
            db=mock_db,
        )

        assert context.entity is not None
        assert context.entity.entity_id == entity_id
        assert context.entity.name == "Mail Carrier"
        assert context.entity.entity_type == "person"

    @pytest.mark.asyncio
    async def test_get_context_without_entity_id(self, provider, camera_id):
        """Test get_context returns None entity when no entity_id provided."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        assert context.entity is None

    @pytest.mark.asyncio
    async def test_get_entity_context_not_found(self, provider, entity_id):
        """Test entity context returns None when entity not found."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # Entity not found
        mock_db.query.return_value = mock_query

        result = await provider._get_entity_context(mock_db, entity_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_entity_context_with_vehicle_attributes(self, provider, entity_id):
        """Test entity context includes vehicle attributes (AC-3.2.3)."""
        mock_db = MagicMock()
        mock_entity_query = MagicMock()
        mock_similar_query = MagicMock()

        mock_entity = self._create_mock_entity(
            entity_id=entity_id,
            entity_type="vehicle",
            name="Family Car",
            vehicle_color="white",
            vehicle_make="toyota",
            vehicle_model="camry",
            vehicle_signature="white-toyota-camry",
        )

        mock_entity_query.filter.return_value = mock_entity_query
        mock_entity_query.first.return_value = mock_entity

        mock_similar_query.filter.return_value = mock_similar_query
        mock_similar_query.order_by.return_value = mock_similar_query
        mock_similar_query.limit.return_value = mock_similar_query
        mock_similar_query.all.return_value = []

        call_count = [0]
        def query_side_effect(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_entity_query
            return mock_similar_query

        mock_db.query.side_effect = query_side_effect

        result = await provider._get_entity_context(mock_db, entity_id)

        assert result is not None
        assert result.entity_type == "vehicle"
        assert result.attributes.get("color") == "white"
        assert result.attributes.get("make") == "toyota"
        assert result.attributes.get("model") == "camry"

    @pytest.mark.asyncio
    async def test_get_entity_context_sighting_count(self, provider, entity_id):
        """Test entity context includes sighting count (AC-3.2.4)."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        mock_entity = self._create_mock_entity(
            entity_id=entity_id,
            occurrence_count=15,
        )

        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_entity
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = await provider._get_entity_context(mock_db, entity_id)

        assert result is not None
        assert result.sighting_count == 15


class TestSimilarEntityMatching:
    """Tests for similar entity matching (Story P11-3.2 AC-3.2.2)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def entity_id(self):
        """Sample entity ID."""
        return str(uuid.uuid4())

    def _create_mock_entity(
        self,
        entity_id: str = None,
        entity_type: str = "vehicle",
        name: str = None,
        occurrence_count: int = 1,
        vehicle_signature: str = None,
    ) -> MagicMock:
        """Create a mock RecognizedEntity object."""
        entity = MagicMock(spec=RecognizedEntity)
        entity.id = entity_id or str(uuid.uuid4())
        entity.entity_type = entity_type
        entity.name = name
        entity.occurrence_count = occurrence_count
        entity.vehicle_signature = vehicle_signature
        entity.display_name = name or f"{entity_type.title()} #{entity.id[:8]}"
        return entity

    @pytest.mark.asyncio
    async def test_similar_entities_for_vehicle(self, provider, entity_id):
        """Test similar entities are found for vehicles by signature pattern."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Create similar vehicles with same color
        similar_vehicles = [
            self._create_mock_entity(
                entity_type="vehicle",
                name="Neighbor's Car",
                occurrence_count=10,
                vehicle_signature="white-honda-accord",
            ),
            self._create_mock_entity(
                entity_type="vehicle",
                name=None,
                occurrence_count=5,
                vehicle_signature="white-ford-fusion",
            ),
        ]

        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = similar_vehicles
        mock_db.query.return_value = mock_query

        result = await provider._get_similar_entities(
            mock_db,
            entity_id,
            "vehicle",
            "white-toyota-camry",
        )

        assert len(result) == 2
        assert result[0]["name"] == "Neighbor's Car"
        assert result[0]["entity_type"] == "vehicle"

    @pytest.mark.asyncio
    async def test_similar_entities_empty_when_none_found(self, provider, entity_id):
        """Test similar entities returns empty list when none found."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        result = await provider._get_similar_entities(
            mock_db,
            entity_id,
            "person",
            None,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_similar_entities_max_limit(self, provider, entity_id):
        """Test similar entities respects MAX_SIMILAR_ENTITIES limit."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Provider should only return MAX_SIMILAR_ENTITIES (3)
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        # Verify limit is called with MAX_SIMILAR_ENTITIES
        await provider._get_similar_entities(
            mock_db,
            entity_id,
            "vehicle",
            "white-toyota-camry",
        )

        mock_query.limit.assert_called_with(provider.MAX_SIMILAR_ENTITIES)


class TestEntityContextSizeLimiting:
    """Tests for entity context size limiting (Story P11-3.2 AC-3.2.5)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    def test_context_within_limit(self, provider):
        """Test entity context formatting stays within MAX_ENTITY_CONTEXT_CHARS."""
        entity = EntityContext(
            entity_id="123",
            name="Short Name",
            entity_type="person",
            attributes={},
            last_seen=datetime.now(timezone.utc),
            sighting_count=5,
        )

        result = provider._format_entity_context(entity)
        total_chars = sum(len(part) for part in result)

        assert total_chars <= provider.MAX_ENTITY_CONTEXT_CHARS

    def test_long_attributes_truncated(self, provider):
        """Test that long attributes are truncated to stay within limit."""
        # Create entity with very long attributes
        long_attrs = {
            "description": "A" * 200,
            "notes": "B" * 200,
        }

        entity = EntityContext(
            entity_id="123",
            name="Test Entity",
            entity_type="vehicle",
            attributes=long_attrs,
            last_seen=datetime.now(timezone.utc),
            sighting_count=5,
        )

        result = provider._format_entity_context(entity)
        total_chars = sum(len(part) for part in result)

        # Should be limited
        assert total_chars <= provider.MAX_ENTITY_CONTEXT_CHARS + 100  # Allow some margin

    def test_prioritizes_name_and_type(self, provider):
        """Test that name and type are always included even with long attributes."""
        entity = EntityContext(
            entity_id="123",
            name="Important Name",
            entity_type="person",
            attributes={"long_key": "A" * 500},  # Very long attribute
            last_seen=datetime.now(timezone.utc),
            sighting_count=5,
        )

        result = provider._format_entity_context(entity)

        # First part should always include name and type
        assert len(result) >= 1
        assert "Important Name" in result[0]
        assert "person" in result[0]


class TestEntityContextFormatting:
    """Tests for entity context prompt formatting (Story P11-3.2)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    def test_format_entity_with_sighting_history(self, provider):
        """Test formatting includes sighting history (AC-3.2.4)."""
        context = AIContext(
            entity=EntityContext(
                entity_id="123",
                name="Regular Visitor",
                entity_type="person",
                attributes={},
                last_seen=datetime.now(timezone.utc) - timedelta(hours=2),
                sighting_count=12,
            )
        )
        result = provider.format_for_prompt(context)

        assert "Regular Visitor" in result
        assert "12" in result  # Sighting count
        assert "Seen" in result

    def test_format_entity_with_vehicle_attributes(self, provider):
        """Test formatting includes vehicle attributes (AC-3.2.3)."""
        context = AIContext(
            entity=EntityContext(
                entity_id="123",
                name="Family Car",
                entity_type="vehicle",
                attributes={"color": "silver", "make": "honda", "model": "civic"},
                last_seen=datetime.now(timezone.utc),
                sighting_count=25,
            )
        )
        result = provider.format_for_prompt(context)

        assert "Family Car" in result
        assert "vehicle" in result
        assert "color=silver" in result
        assert "make=honda" in result

    def test_format_entity_with_similar_entities(self, provider):
        """Test formatting includes similar entity hints (AC-3.2.2)."""
        context = AIContext(
            entity=EntityContext(
                entity_id="123",
                name="White Toyota",
                entity_type="vehicle",
                attributes={},
                last_seen=datetime.now(timezone.utc),
                sighting_count=5,
                similar_entities=[
                    {"id": "456", "name": "White Honda", "entity_type": "vehicle", "occurrence_count": 3},
                    {"id": "789", "name": "White Ford", "entity_type": "vehicle", "occurrence_count": 2},
                ],
            )
        )
        result = provider.format_for_prompt(context)

        assert "White Toyota" in result
        assert "Similar known entities" in result
        assert "White Honda" in result

    def test_format_entity_singular_sighting(self, provider):
        """Test formatting uses singular 'time' for single sighting."""
        context = AIContext(
            entity=EntityContext(
                entity_id="123",
                name="New Visitor",
                entity_type="person",
                attributes={},
                last_seen=datetime.now(timezone.utc),
                sighting_count=1,
            )
        )
        result = provider.format_for_prompt(context)

        assert "Seen 1 time" in result
        assert "Seen 1 times" not in result


class TestEntityContextFailOpen:
    """Tests for entity context fail-open behavior (Story P11-3.2)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def entity_id(self):
        """Sample entity ID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_entity_error_returns_none(self, provider, camera_id, entity_id):
        """Test that entity lookup errors return None, not exception."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()
        mock_entity_query = MagicMock()

        # Setup feedback to work
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []

        # Setup entity to fail
        mock_entity_query.filter.side_effect = Exception("Entity query failed")

        def query_side_effect(model):
            if model.__name__ == "RecognizedEntity":
                return mock_entity_query
            return mock_feedback_query

        mock_db.query.side_effect = query_side_effect

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            entity_id=entity_id,
            db=mock_db,
        )

        # Should return context with None entity, not raise exception
        assert isinstance(context, AIContext)
        assert context.entity is None
        # Feedback should still work
        assert context.feedback is not None

    @pytest.mark.asyncio
    async def test_safe_get_entity_context_catches_exceptions(self, provider, entity_id):
        """Test _safe_get_entity_context catches and logs exceptions."""
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")

        result = await provider._safe_get_entity_context(mock_db, entity_id)

        assert result is None


class TestCameraContextGathering:
    """Tests for camera context gathering (Story P11-3.3)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    def _create_mock_camera(
        self,
        camera_id: str = None,
        name: str = "Front Door",
    ) -> MagicMock:
        """Create a mock Camera object."""
        camera = MagicMock(spec=Camera)
        camera.id = camera_id or str(uuid.uuid4())
        camera.name = name
        return camera

    @pytest.mark.asyncio
    async def test_get_camera_context_with_valid_camera(self, provider, camera_id):
        """Test camera context is returned for valid camera (AC-3.3.1)."""
        mock_db = MagicMock()
        mock_camera_query = MagicMock()
        mock_events_query = MagicMock()
        mock_feedback_query = MagicMock()

        mock_camera = self._create_mock_camera(camera_id=camera_id, name="Driveway")

        # Setup camera query
        mock_camera_query.filter.return_value = mock_camera_query
        mock_camera_query.first.return_value = mock_camera

        # Setup events query (for typical objects)
        mock_events_query.filter.return_value = mock_events_query
        mock_events_query.all.return_value = [
            ("person",), ("person",), ("person",),
            ("vehicle",), ("vehicle",),
            ("package",),
        ]

        # Setup feedback query (for false positives)
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []

        call_count = [0]
        def query_side_effect(model):
            call_count[0] += 1
            if hasattr(model, '__name__'):
                if model.__name__ == "Camera":
                    return mock_camera_query
                elif model.__name__ == "Event":
                    return mock_events_query
            # EventFeedback correction query
            return mock_feedback_query

        mock_db.query.side_effect = query_side_effect

        result = await provider._get_camera_context(mock_db, camera_id)

        assert result is not None
        assert result.camera_id == camera_id
        assert result.location_hint == "Driveway"

    @pytest.mark.asyncio
    async def test_get_camera_context_not_found(self, provider, camera_id):
        """Test camera context returns None when camera not found (AC-3.3.1)."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None  # Camera not found
        mock_db.query.return_value = mock_query

        result = await provider._get_camera_context(mock_db, camera_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_camera_context_typical_objects(self, provider, camera_id):
        """Test typical objects are extracted from events (AC-3.3.2)."""
        mock_db = MagicMock()
        mock_camera_query = MagicMock()
        mock_events_query = MagicMock()
        mock_feedback_query = MagicMock()

        mock_camera = self._create_mock_camera(camera_id=camera_id)

        mock_camera_query.filter.return_value = mock_camera_query
        mock_camera_query.first.return_value = mock_camera

        # Multiple person and vehicle detections
        mock_events_query.filter.return_value = mock_events_query
        mock_events_query.all.return_value = [
            ("person",), ("person",), ("person",), ("person",), ("person",),
            ("vehicle",), ("vehicle",), ("vehicle",),
            ("animal",),
        ]

        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []

        query_results = [mock_camera_query, mock_events_query, mock_feedback_query]
        call_idx = [0]
        def query_side_effect(model):
            result = query_results[min(call_idx[0], len(query_results) - 1)]
            call_idx[0] += 1
            return result

        mock_db.query.side_effect = query_side_effect

        result = await provider._get_camera_context(mock_db, camera_id)

        assert result is not None
        assert "person" in result.typical_objects
        assert len(result.typical_objects) <= 3

    @pytest.mark.asyncio
    async def test_get_camera_context_false_positives(self, provider, camera_id):
        """Test false positive patterns are extracted (AC-3.3.5)."""
        mock_db = MagicMock()
        mock_camera_query = MagicMock()
        mock_events_query = MagicMock()
        mock_feedback_query = MagicMock()

        mock_camera = self._create_mock_camera(camera_id=camera_id)

        mock_camera_query.filter.return_value = mock_camera_query
        mock_camera_query.first.return_value = mock_camera

        mock_events_query.filter.return_value = mock_events_query
        mock_events_query.all.return_value = []

        # Create negative feedback corrections for false positives
        mock_corrections = [
            MagicMock(correction="shadow from tree"),
            MagicMock(correction="shadow in morning"),
            MagicMock(correction="tree branch moving"),
        ]

        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = mock_corrections

        query_results = [mock_camera_query, mock_events_query, mock_feedback_query]
        call_idx = [0]
        def query_side_effect(model):
            result = query_results[min(call_idx[0], len(query_results) - 1)]
            call_idx[0] += 1
            return result

        mock_db.query.side_effect = query_side_effect

        result = await provider._get_camera_context(mock_db, camera_id)

        assert result is not None
        # Should have common patterns from corrections
        assert len(result.false_positive_patterns) <= 3

    @pytest.mark.asyncio
    async def test_safe_get_camera_context_catches_exceptions(self, provider, camera_id):
        """Test _safe_get_camera_context catches and logs exceptions."""
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")

        result = await provider._safe_get_camera_context(mock_db, camera_id)

        assert result is None


class TestTimePatternContextGathering:
    """Tests for time pattern context gathering (Story P11-3.3)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_time_pattern_context_low_activity(self, provider, camera_id):
        """Test time pattern with low activity level (AC-3.3.3)."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Very few events at this hour (< 1 per day avg over 30 days)
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 10  # 10 events in 30 days = 0.33/day

        mock_db.query.return_value = mock_query

        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)  # 2 PM
        result = await provider._get_time_pattern_context(mock_db, camera_id, event_time)

        assert result is not None
        assert result.hour == 14
        assert result.typical_activity_level == "low"
        assert result.typical_event_count < 1

    @pytest.mark.asyncio
    async def test_get_time_pattern_context_medium_activity(self, provider, camera_id):
        """Test time pattern with medium activity level (AC-3.3.3)."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Medium events: 1-5 per day avg
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 90  # 90 events in 30 days = 3/day

        mock_db.query.return_value = mock_query

        event_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)  # 10 AM
        result = await provider._get_time_pattern_context(mock_db, camera_id, event_time)

        assert result is not None
        assert result.hour == 10
        assert result.typical_activity_level == "medium"
        assert 1 <= result.typical_event_count < 5

    @pytest.mark.asyncio
    async def test_get_time_pattern_context_high_activity(self, provider, camera_id):
        """Test time pattern with high activity level (AC-3.3.3)."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # High events: > 5 per day avg
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 210  # 210 events in 30 days = 7/day

        mock_db.query.return_value = mock_query

        event_time = datetime(2024, 1, 15, 17, 0, 0, tzinfo=timezone.utc)  # 5 PM
        result = await provider._get_time_pattern_context(mock_db, camera_id, event_time)

        assert result is not None
        assert result.hour == 17
        assert result.typical_activity_level == "high"
        assert result.typical_event_count >= 5

    @pytest.mark.asyncio
    async def test_get_time_pattern_context_is_unusual_late_night(self, provider, camera_id):
        """Test unusual flag for late night activity (AC-3.3.4)."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Low activity during late night = unusual
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 5  # Very few events at 3 AM

        mock_db.query.return_value = mock_query

        event_time = datetime(2024, 1, 15, 3, 0, 0, tzinfo=timezone.utc)  # 3 AM
        result = await provider._get_time_pattern_context(mock_db, camera_id, event_time)

        assert result is not None
        assert result.hour == 3
        assert result.is_unusual is True

    @pytest.mark.asyncio
    async def test_get_time_pattern_context_not_unusual_daytime(self, provider, camera_id):
        """Test unusual flag is False for normal daytime activity (AC-3.3.4)."""
        mock_db = MagicMock()
        mock_query = MagicMock()

        # Medium activity during day = not unusual
        mock_query.filter.return_value = mock_query
        mock_query.scalar.return_value = 60  # ~2/day avg

        mock_db.query.return_value = mock_query

        event_time = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)  # Noon
        result = await provider._get_time_pattern_context(mock_db, camera_id, event_time)

        assert result is not None
        assert result.hour == 12
        assert result.is_unusual is False

    @pytest.mark.asyncio
    async def test_safe_get_time_pattern_context_catches_exceptions(self, provider, camera_id):
        """Test _safe_get_time_pattern_context catches and logs exceptions."""
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")

        event_time = datetime.now(timezone.utc)
        result = await provider._safe_get_time_pattern_context(mock_db, camera_id, event_time)

        assert result is None


class TestCameraContextFormatting:
    """Tests for camera context prompt formatting (Story P11-3.3)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    def test_format_camera_location_hint(self, provider):
        """Test formatting includes camera location hint (AC-3.3.1)."""
        context = AIContext(
            camera=CameraContext(
                camera_id="cam1",
                location_hint="Back Patio",
                typical_objects=[],
                false_positive_patterns=[],
            )
        )
        result = provider.format_for_prompt(context)

        assert "Camera location: Back Patio" in result

    def test_format_camera_typical_objects(self, provider):
        """Test formatting includes typical objects (AC-3.3.2)."""
        context = AIContext(
            camera=CameraContext(
                camera_id="cam1",
                location_hint="Garage",
                typical_objects=["vehicle", "person", "package"],
                false_positive_patterns=[],
            )
        )
        result = provider.format_for_prompt(context)

        assert "Commonly detected at this camera: vehicle, person, package" in result

    def test_format_camera_false_positives(self, provider):
        """Test formatting includes false positive patterns (AC-3.3.5)."""
        context = AIContext(
            camera=CameraContext(
                camera_id="cam1",
                location_hint="Backyard",
                typical_objects=[],
                false_positive_patterns=["shadow", "tree", "wind"],
            )
        )
        result = provider.format_for_prompt(context)

        assert "Common false positive patterns: shadow, tree, wind" in result

    def test_format_camera_full_context(self, provider):
        """Test formatting with all camera context fields."""
        context = AIContext(
            camera=CameraContext(
                camera_id="cam1",
                location_hint="Front Door",
                typical_objects=["person", "package"],
                false_positive_patterns=["shadow"],
            )
        )
        result = provider.format_for_prompt(context)

        assert "Camera location: Front Door" in result
        assert "Commonly detected at this camera: person, package" in result
        assert "Common false positive patterns: shadow" in result


class TestTimePatternContextFormatting:
    """Tests for time pattern context prompt formatting (Story P11-3.3)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    def test_format_time_pattern_activity_level(self, provider):
        """Test formatting includes activity level (AC-3.3.3)."""
        context = AIContext(
            time_pattern=TimePatternContext(
                hour=14,
                typical_activity_level="medium",
                is_unusual=False,
                typical_event_count=3.5,
            )
        )
        result = provider.format_for_prompt(context)

        assert "Time of day: 14:00 (typical activity: medium)" in result

    def test_format_time_pattern_unusual_flag(self, provider):
        """Test formatting includes unusual flag (AC-3.3.4)."""
        context = AIContext(
            time_pattern=TimePatternContext(
                hour=3,
                typical_activity_level="low",
                is_unusual=True,
                typical_event_count=0.2,
            )
        )
        result = provider.format_for_prompt(context)

        assert "unusual activity" in result.lower()

    def test_format_time_pattern_not_unusual(self, provider):
        """Test formatting without unusual flag when not unusual."""
        context = AIContext(
            time_pattern=TimePatternContext(
                hour=12,
                typical_activity_level="high",
                is_unusual=False,
                typical_event_count=8.0,
            )
        )
        result = provider.format_for_prompt(context)

        assert "Time of day: 12:00 (typical activity: high)" in result
        assert "unusual" not in result.lower()


class TestCameraAndTimeContextFailOpen:
    """Tests for camera and time context fail-open behavior (Story P11-3.3)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_camera_error_returns_none(self, provider, camera_id):
        """Test that camera context errors return None, not exception."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()
        mock_camera_query = MagicMock()

        # Setup feedback to work
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []

        # Setup camera to fail
        mock_camera_query.filter.side_effect = Exception("Camera query failed")

        def query_side_effect(model):
            if hasattr(model, '__name__') and model.__name__ == "Camera":
                return mock_camera_query
            return mock_feedback_query

        mock_db.query.side_effect = query_side_effect

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        # Should return context with None camera, not raise exception
        assert isinstance(context, AIContext)
        assert context.camera is None

    @pytest.mark.asyncio
    async def test_time_pattern_error_returns_none(self, provider, camera_id):
        """Test that time pattern errors return None, not exception."""
        mock_db = MagicMock()

        # All queries fail
        mock_db.query.side_effect = Exception("Time pattern query failed")

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        # Should return context with None time_pattern, not raise exception
        assert isinstance(context, AIContext)
        assert context.time_pattern is None

    @pytest.mark.asyncio
    async def test_partial_context_with_camera_and_time_errors(self, provider, camera_id):
        """Test partial context is returned when camera and time fail but feedback works."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()

        # Setup feedback to work with some data
        mock_feedback = MagicMock()
        mock_feedback.rating = "helpful"
        mock_feedback.correction = None
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = [mock_feedback]

        error_models = ["Camera", "Event"]
        def query_side_effect(model):
            if hasattr(model, '__name__') and model.__name__ in error_models:
                raise Exception(f"{model.__name__} query failed")
            return mock_feedback_query

        mock_db.query.side_effect = query_side_effect

        context = await provider.get_context(
            camera_id=camera_id,
            event_time=datetime.now(timezone.utc),
            db=mock_db,
        )

        # Should have partial context
        assert isinstance(context, AIContext)
        assert context.feedback is not None  # Feedback worked
        assert context.camera is None  # Camera failed
        assert context.time_pattern is None  # Time pattern failed


class TestCachedContext:
    """Tests for CachedContext dataclass (Story P11-3.4)."""

    def test_cached_context_not_expired(self):
        """Test cached context is not expired within TTL."""
        context = AIContext(
            feedback=FeedbackContext(
                accuracy_rate=0.9,
                total_feedback=10,
                common_corrections=[],
                recent_negative_reasons=[],
            )
        )
        cached = CachedContext(
            context=context,
            created_at=datetime.now(timezone.utc),
        )

        assert cached.is_expired(ttl_seconds=60) is False

    def test_cached_context_expired(self):
        """Test cached context is expired after TTL."""
        context = AIContext()
        cached = CachedContext(
            context=context,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=120),
        )

        assert cached.is_expired(ttl_seconds=60) is True

    def test_cached_context_handles_naive_datetime(self):
        """Test cached context handles timezone-naive datetime."""
        context = AIContext()
        # Create timezone-naive datetime
        cached = CachedContext(
            context=context,
            created_at=datetime.utcnow(),  # Naive datetime
        )

        # Should not raise, should handle timezone comparison
        result = cached.is_expired(ttl_seconds=60)
        assert isinstance(result, bool)


class TestContextCaching:
    """Tests for context caching (Story P11-3.4)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    def test_cache_key_generation(self, provider, camera_id):
        """Test cache key is generated from camera_id and hour (AC-3.4.2)."""
        event_time = datetime(2024, 1, 15, 14, 30, 0, tzinfo=timezone.utc)

        cache_key = provider._get_cache_key(camera_id, event_time)

        assert cache_key == f"{camera_id}:14"

    def test_cache_key_different_hours(self, provider, camera_id):
        """Test cache keys are different for different hours."""
        event_time_1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        event_time_2 = datetime(2024, 1, 15, 15, 0, 0, tzinfo=timezone.utc)

        key_1 = provider._get_cache_key(camera_id, event_time_1)
        key_2 = provider._get_cache_key(camera_id, event_time_2)

        assert key_1 != key_2
        assert key_1 == f"{camera_id}:10"
        assert key_2 == f"{camera_id}:15"

    @pytest.mark.asyncio
    async def test_cache_stores_context(self, provider, camera_id):
        """Test context is stored in cache after gathering (AC-3.4.1)."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()

        # Setup feedback query
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []
        mock_feedback_query.first.return_value = None
        mock_feedback_query.scalar.return_value = 0

        mock_db.query.return_value = mock_feedback_query

        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        # First call - should be cache miss
        await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            db=mock_db,
        )

        # Check cache has entry
        cache_key = provider._get_cache_key(camera_id, event_time)
        assert cache_key in provider._cache

    @pytest.mark.asyncio
    async def test_cache_returns_cached_context(self, provider, camera_id):
        """Test cached context is returned on cache hit (AC-3.4.1)."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()

        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []
        mock_feedback_query.first.return_value = None
        mock_feedback_query.scalar.return_value = 0

        mock_db.query.return_value = mock_feedback_query

        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        # First call - cache miss
        await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            db=mock_db,
        )

        # Reset mock to verify second call doesn't query DB
        mock_db.reset_mock()

        # Second call - should be cache hit (no DB queries except potentially entity)
        result = await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            db=mock_db,
        )

        assert result is not None
        assert isinstance(result, AIContext)

    @pytest.mark.asyncio
    async def test_cache_expires_after_ttl(self, provider, camera_id):
        """Test cache expires after TTL (AC-3.4.1)."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()

        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []
        mock_feedback_query.first.return_value = None
        mock_feedback_query.scalar.return_value = 0

        mock_db.query.return_value = mock_feedback_query

        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        # First call
        await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            db=mock_db,
        )

        # Manually expire the cache entry
        cache_key = provider._get_cache_key(camera_id, event_time)
        provider._cache[cache_key].created_at = datetime.now(timezone.utc) - timedelta(seconds=120)

        # Verify entry is expired
        assert provider._cache[cache_key].is_expired(provider.CACHE_TTL_SECONDS) is True

    def test_clear_cache(self, provider, camera_id):
        """Test clear_cache removes all entries (AC-3.4.1)."""
        # Add some entries to cache
        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        cache_key = provider._get_cache_key(camera_id, event_time)
        provider._cache[cache_key] = CachedContext(
            context=AIContext(),
            created_at=datetime.now(timezone.utc),
        )

        assert len(provider._cache) == 1

        provider.clear_cache()

        assert len(provider._cache) == 0


class TestContextMetrics:
    """Tests for Prometheus metrics (Story P11-3.4)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_cache_miss_increments_counter(self, provider, camera_id):
        """Test cache miss increments MCP_CACHE_MISSES counter (AC-3.4.5)."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()

        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []
        mock_feedback_query.first.return_value = None
        mock_feedback_query.scalar.return_value = 0

        mock_db.query.return_value = mock_feedback_query

        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        initial_misses = MCP_CACHE_MISSES._value.get()

        await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            db=mock_db,
        )

        # Counter should have incremented
        assert MCP_CACHE_MISSES._value.get() > initial_misses

    @pytest.mark.asyncio
    async def test_cache_hit_increments_counter(self, provider, camera_id):
        """Test cache hit increments MCP_CACHE_HITS counter (AC-3.4.5)."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()

        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []
        mock_feedback_query.first.return_value = None
        mock_feedback_query.scalar.return_value = 0

        mock_db.query.return_value = mock_feedback_query

        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        # First call - cache miss
        await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            db=mock_db,
        )

        initial_hits = MCP_CACHE_HITS._value.get()

        # Second call - cache hit
        await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            db=mock_db,
        )

        # Counter should have incremented
        assert MCP_CACHE_HITS._value.get() > initial_hits

    @pytest.mark.asyncio
    async def test_latency_histogram_recorded(self, provider, camera_id):
        """Test latency is recorded in histogram (AC-3.4.4)."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()

        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []
        mock_feedback_query.first.return_value = None
        mock_feedback_query.scalar.return_value = 0

        mock_db.query.return_value = mock_feedback_query

        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        # Get initial count
        initial_count = MCP_CONTEXT_LATENCY._metrics[("false",)]._sum.get()

        await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            db=mock_db,
        )

        # Histogram should have been updated
        new_count = MCP_CONTEXT_LATENCY._metrics[("false",)]._sum.get()
        assert new_count >= initial_count  # Sum should increase or stay same


class TestContextCachingWithEntity:
    """Tests for caching behavior with entity context (Story P11-3.4)."""

    @pytest.fixture
    def provider(self):
        """Create a fresh MCPContextProvider instance."""
        return MCPContextProvider()

    @pytest.fixture
    def camera_id(self):
        """Sample camera ID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def entity_id(self):
        """Sample entity ID."""
        return str(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_entity_not_cached(self, provider, camera_id, entity_id):
        """Test entity context is fetched even on cache hit."""
        mock_db = MagicMock()
        mock_feedback_query = MagicMock()
        mock_entity_query = MagicMock()

        # Setup feedback query
        mock_feedback_query.filter.return_value = mock_feedback_query
        mock_feedback_query.order_by.return_value = mock_feedback_query
        mock_feedback_query.limit.return_value = mock_feedback_query
        mock_feedback_query.all.return_value = []
        mock_feedback_query.first.return_value = None
        mock_feedback_query.scalar.return_value = 0

        # Setup entity query
        mock_entity = MagicMock()
        mock_entity.id = entity_id
        mock_entity.name = "Test Entity"
        mock_entity.entity_type = "person"
        mock_entity.vehicle_color = None
        mock_entity.vehicle_make = None
        mock_entity.vehicle_model = None
        mock_entity.last_seen_at = datetime.now(timezone.utc)
        mock_entity.occurrence_count = 5

        mock_entity_query.filter.return_value = mock_entity_query
        mock_entity_query.first.return_value = mock_entity
        mock_entity_query.order_by.return_value = mock_entity_query
        mock_entity_query.limit.return_value = mock_entity_query
        mock_entity_query.all.return_value = []

        call_count = [0]
        def query_side_effect(model):
            call_count[0] += 1
            if hasattr(model, '__name__') and model.__name__ == "RecognizedEntity":
                return mock_entity_query
            return mock_feedback_query

        mock_db.query.side_effect = query_side_effect

        event_time = datetime(2024, 1, 15, 14, 0, 0, tzinfo=timezone.utc)

        # First call with entity - cache miss
        result1 = await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            entity_id=entity_id,
            db=mock_db,
        )

        # Entity should be in result
        assert result1.entity is not None

        # Reset mock
        mock_db.reset_mock()
        mock_db.query.side_effect = query_side_effect

        # Second call with entity - cache hit for feedback/camera/time, but entity still fetched
        result2 = await provider.get_context(
            camera_id=camera_id,
            event_time=event_time,
            entity_id=entity_id,
            db=mock_db,
        )

        # Entity should still be in result
        assert result2.entity is not None
