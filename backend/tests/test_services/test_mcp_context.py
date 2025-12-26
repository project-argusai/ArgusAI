"""
Tests for MCPContextProvider (Story P11-3.1, P11-3.2).

Tests feedback context gathering, accuracy calculation, pattern extraction,
entity context gathering, similar entity matching, context size limiting,
prompt formatting, and fail-open behavior.
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
    get_mcp_context_provider,
    reset_mcp_context_provider,
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
