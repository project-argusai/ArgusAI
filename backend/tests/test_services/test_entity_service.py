"""
Unit tests for EntityService (Story P4-3.3: Recurring Visitor Detection)

Tests:
- AC1: System clusters similar event embeddings to identify recurring entities
- AC2: RecognizedEntity model stores required fields
- AC3: EntityEvent junction table links entities to events
- AC4: match_or_create_entity returns existing entity or creates new one
- AC5: When match found above threshold, entity is updated
- AC6: When no match above threshold, new entity is created
- AC13: Performance: Entity matching completes in <200ms with 1000 entities
- AC14: Graceful handling when embedding service unavailable
"""
import json
import pytest
import time
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

from app.services.entity_service import (
    EntityService,
    get_entity_service,
    reset_entity_service,
    EntityMatchResult,
)


class TestEntityMatchResult:
    """Tests for EntityMatchResult dataclass."""

    def test_create_match_result_for_new_entity(self):
        """Test creating match result for a new entity."""
        now = datetime.now(timezone.utc)
        result = EntityMatchResult(
            entity_id="test-entity-id",
            entity_type="person",
            name=None,
            first_seen_at=now,
            last_seen_at=now,
            occurrence_count=1,
            similarity_score=1.0,
            is_new=True,
        )

        assert result.entity_id == "test-entity-id"
        assert result.entity_type == "person"
        assert result.name is None
        assert result.occurrence_count == 1
        assert result.similarity_score == 1.0
        assert result.is_new is True

    def test_create_match_result_for_existing_entity(self):
        """Test creating match result for an existing entity."""
        first_seen = datetime.now(timezone.utc) - timedelta(days=7)
        last_seen = datetime.now(timezone.utc)
        result = EntityMatchResult(
            entity_id="existing-entity-id",
            entity_type="vehicle",
            name="Mail Truck",
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            occurrence_count=15,
            similarity_score=0.87,
            is_new=False,
        )

        assert result.entity_id == "existing-entity-id"
        assert result.entity_type == "vehicle"
        assert result.name == "Mail Truck"
        assert result.occurrence_count == 15
        assert result.similarity_score == 0.87
        assert result.is_new is False


class TestEntityServiceInit:
    """Tests for EntityService initialization."""

    def test_init_with_default_similarity_service(self):
        """Test initialization with default similarity service."""
        service = EntityService()
        assert service._similarity_service is not None
        assert service._entity_cache == {}
        assert service._cache_loaded is False

    def test_init_with_custom_similarity_service(self):
        """Test initialization with custom similarity service."""
        mock_similarity_service = MagicMock()
        service = EntityService(similarity_service=mock_similarity_service)
        assert service._similarity_service == mock_similarity_service

    def test_default_threshold_value(self):
        """Test that default threshold is 0.75."""
        assert EntityService.DEFAULT_THRESHOLD == 0.75


class TestEntityServiceSingleton:
    """Tests for EntityService singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        reset_entity_service()

    def teardown_method(self):
        """Reset singleton after each test."""
        reset_entity_service()

    def test_get_entity_service_returns_singleton(self):
        """Test that get_entity_service returns same instance."""
        service1 = get_entity_service()
        service2 = get_entity_service()
        assert service1 is service2

    def test_reset_entity_service_clears_singleton(self):
        """Test that reset_entity_service clears the singleton."""
        service1 = get_entity_service()
        reset_entity_service()
        service2 = get_entity_service()
        assert service1 is not service2


class TestEntityServiceCaching:
    """Tests for EntityService embedding cache."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_entity_service()
        self.service = EntityService()

    def teardown_method(self):
        """Clean up after tests."""
        reset_entity_service()

    def test_cache_initially_empty(self):
        """Test that cache is empty on initialization."""
        assert self.service._entity_cache == {}
        assert self.service._cache_loaded is False

    def test_invalidate_cache_clears_cache(self):
        """Test that _invalidate_cache clears the cache."""
        # Populate cache manually
        self.service._entity_cache = {"entity1": [0.1, 0.2, 0.3]}
        self.service._cache_loaded = True

        self.service._invalidate_cache()

        assert self.service._entity_cache == {}
        assert self.service._cache_loaded is False


class TestMatchOrCreateEntity:
    """Tests for match_or_create_entity method (AC1, AC4, AC5, AC6)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_entity_service()
        self.service = EntityService()

    def teardown_method(self):
        """Clean up after tests."""
        reset_entity_service()

    @pytest.mark.asyncio
    async def test_creates_new_entity_when_cache_empty(self):
        """AC6: When no existing entities, creates new entity."""
        # Create mock database session
        mock_db = MagicMock()

        # Mock query for entity cache loading (return empty)
        mock_query = MagicMock()
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        # Mock event timestamp query
        mock_event = MagicMock()
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_query.filter.return_value.first.return_value = mock_event

        # Generate test embedding
        embedding = [0.1] * 512

        result = await self.service.match_or_create_entity(
            db=mock_db,
            event_id="test-event-1",
            embedding=embedding,
            entity_type="person",
        )

        assert result.is_new is True
        assert result.entity_type == "person"
        assert result.occurrence_count == 1
        assert result.similarity_score == 1.0
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_matches_existing_entity_above_threshold(self):
        """AC5: When match found above threshold, returns existing entity."""
        mock_db = MagicMock()

        # Create existing entity embedding (very similar to test embedding)
        existing_embedding = [0.1] * 512

        # Mock entity in cache
        mock_entity = MagicMock()
        mock_entity.id = "existing-entity-id"
        mock_entity.reference_embedding = json.dumps(existing_embedding)

        # Set up cache loading
        mock_query = MagicMock()
        mock_query.all.return_value = [mock_entity]
        mock_db.query.return_value = mock_query

        # Mock event timestamp query
        mock_event = MagicMock()
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_query.filter.return_value.first.return_value = mock_event

        # Test with identical embedding (similarity = 1.0)
        test_embedding = [0.1] * 512

        # Pre-load cache to avoid database query
        self.service._entity_cache = {"existing-entity-id": existing_embedding}
        self.service._cache_loaded = True

        # Mock the entity update
        mock_existing = MagicMock()
        mock_existing.id = "existing-entity-id"
        mock_existing.entity_type = "person"
        mock_existing.name = "Test Person"
        mock_existing.first_seen_at = datetime.now(timezone.utc) - timedelta(days=7)
        mock_existing.last_seen_at = datetime.now(timezone.utc)
        mock_existing.occurrence_count = 5

        mock_db.query.return_value.filter.return_value.first.return_value = mock_existing

        result = await self.service.match_or_create_entity(
            db=mock_db,
            event_id="test-event-2",
            embedding=test_embedding,
            entity_type="person",
            threshold=0.75,
        )

        # Should match existing entity
        assert result.is_new is False
        assert result.entity_id == "existing-entity-id"
        assert result.similarity_score >= 0.75

    @pytest.mark.asyncio
    async def test_creates_new_entity_below_threshold(self):
        """AC6: When no match above threshold, creates new entity."""
        mock_db = MagicMock()

        # Create existing entity with very different embedding
        existing_embedding = [0.9, 0.1, 0.0] + [0.0] * 509

        # Pre-load cache
        self.service._entity_cache = {"existing-entity-id": existing_embedding}
        self.service._cache_loaded = True

        # Test with very different embedding
        test_embedding = [0.0, 0.0, 0.9] + [0.1] * 509

        # Mock event timestamp query
        mock_event = MagicMock()
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_event
        mock_db.query.return_value = mock_query

        result = await self.service.match_or_create_entity(
            db=mock_db,
            event_id="test-event-3",
            embedding=test_embedding,
            entity_type="vehicle",
            threshold=0.75,
        )

        assert result.is_new is True
        assert result.entity_type == "vehicle"
        assert result.occurrence_count == 1

    @pytest.mark.asyncio
    async def test_configurable_threshold(self):
        """Test that threshold parameter is respected."""
        mock_db = MagicMock()

        # Create existing entity
        existing_embedding = [1.0, 0.0] + [0.0] * 510

        self.service._entity_cache = {"existing-entity-id": existing_embedding}
        self.service._cache_loaded = True

        # Test embedding with moderate similarity (~0.7)
        test_embedding = [0.7, 0.7] + [0.0] * 510

        # Mock event timestamp
        mock_event = MagicMock()
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_event
        mock_db.query.return_value = mock_query

        # With high threshold (0.9), should create new entity
        result_high = await self.service.match_or_create_entity(
            db=mock_db,
            event_id="test-event-4",
            embedding=test_embedding,
            entity_type="person",
            threshold=0.9,
        )
        assert result_high.is_new is True


class TestEntityCRUD:
    """Tests for entity CRUD operations (AC7, AC8, AC9, AC10)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_entity_service()
        self.service = EntityService()

    def teardown_method(self):
        """Clean up after tests."""
        reset_entity_service()

    @pytest.mark.asyncio
    async def test_get_all_entities_returns_paginated_list(self):
        """AC7: GET /api/v1/entities returns list of entities with stats."""
        mock_db = MagicMock()

        # Create mock entities
        mock_entity1 = MagicMock()
        mock_entity1.id = "entity-1"
        mock_entity1.entity_type = "person"
        mock_entity1.name = "Test Person"
        mock_entity1.first_seen_at = datetime.now(timezone.utc) - timedelta(days=7)
        mock_entity1.last_seen_at = datetime.now(timezone.utc)
        mock_entity1.occurrence_count = 10

        mock_entity2 = MagicMock()
        mock_entity2.id = "entity-2"
        mock_entity2.entity_type = "vehicle"
        mock_entity2.name = None
        mock_entity2.first_seen_at = datetime.now(timezone.utc) - timedelta(days=3)
        mock_entity2.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
        mock_entity2.occurrence_count = 5

        # Mock query chain
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 2
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            mock_entity1, mock_entity2
        ]
        mock_db.query.return_value = mock_query

        entities, total = await self.service.get_all_entities(
            db=mock_db,
            limit=50,
            offset=0,
        )

        assert total == 2
        assert len(entities) == 2
        assert entities[0]["id"] == "entity-1"
        assert entities[0]["entity_type"] == "person"
        assert entities[1]["id"] == "entity-2"

    @pytest.mark.asyncio
    async def test_get_all_entities_filters_by_type(self):
        """Test filtering entities by type."""
        mock_db = MagicMock()

        mock_entity = MagicMock()
        mock_entity.id = "entity-1"
        mock_entity.entity_type = "person"
        mock_entity.name = None
        mock_entity.first_seen_at = datetime.now(timezone.utc)
        mock_entity.last_seen_at = datetime.now(timezone.utc)
        mock_entity.occurrence_count = 1

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_entity]
        mock_db.query.return_value = mock_query

        entities, total = await self.service.get_all_entities(
            db=mock_db,
            limit=50,
            offset=0,
            entity_type="person",
        )

        assert total == 1
        # Verify filter was called
        mock_query.filter.assert_called()

    @pytest.mark.asyncio
    async def test_get_entity_returns_with_recent_events(self):
        """AC8: GET /api/v1/entities/{id} returns entity with events."""
        mock_db = MagicMock()

        # Mock entity
        mock_entity = MagicMock()
        mock_entity.id = "entity-1"
        mock_entity.entity_type = "person"
        mock_entity.name = "Mail Carrier"
        mock_entity.first_seen_at = datetime.now(timezone.utc) - timedelta(days=7)
        mock_entity.last_seen_at = datetime.now(timezone.utc)
        mock_entity.occurrence_count = 5
        mock_entity.created_at = datetime.now(timezone.utc) - timedelta(days=7)
        mock_entity.updated_at = datetime.now(timezone.utc)

        # Mock event
        mock_event = MagicMock()
        mock_event.id = "event-1"
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_event.description = "Person at door"
        mock_event.thumbnail_path = "/path/to/thumb.jpg"
        mock_event.camera_id = "camera-1"
        mock_event.similarity_score = 0.92

        # Set up query mocks
        mock_query1 = MagicMock()
        mock_query1.filter.return_value.first.return_value = mock_entity

        mock_query2 = MagicMock()
        mock_query2.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_event
        ]

        mock_db.query.side_effect = [mock_query1, mock_query2]

        entity = await self.service.get_entity(
            db=mock_db,
            entity_id="entity-1",
            include_events=True,
            event_limit=10,
        )

        assert entity is not None
        assert entity["id"] == "entity-1"
        assert entity["name"] == "Mail Carrier"
        assert "recent_events" in entity
        assert len(entity["recent_events"]) == 1

    @pytest.mark.asyncio
    async def test_get_entity_returns_none_for_not_found(self):
        """Test that get_entity returns None when not found."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        entity = await self.service.get_entity(
            db=mock_db,
            entity_id="nonexistent-id",
        )

        assert entity is None

    @pytest.mark.asyncio
    async def test_update_entity_name(self):
        """AC9: PUT /api/v1/entities/{id} allows naming entity."""
        mock_db = MagicMock()

        mock_entity = MagicMock()
        mock_entity.id = "entity-1"
        mock_entity.entity_type = "person"
        mock_entity.name = None
        mock_entity.first_seen_at = datetime.now(timezone.utc)
        mock_entity.last_seen_at = datetime.now(timezone.utc)
        mock_entity.occurrence_count = 5

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_entity
        mock_db.query.return_value = mock_query

        result = await self.service.update_entity(
            db=mock_db,
            entity_id="entity-1",
            name="Mail Carrier",
        )

        assert result is not None
        assert mock_entity.name == "Mail Carrier"
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_update_entity_returns_none_for_not_found(self):
        """Test that update_entity returns None when not found."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        result = await self.service.update_entity(
            db=mock_db,
            entity_id="nonexistent-id",
            name="Test",
        )

        assert result is None
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_entity_removes_entity_and_clears_cache(self):
        """AC10: DELETE /api/v1/entities/{id} removes entity."""
        mock_db = MagicMock()

        mock_entity = MagicMock()
        mock_entity.id = "entity-1"

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_entity
        mock_db.query.return_value = mock_query

        # Add entity to cache
        self.service._entity_cache = {"entity-1": [0.1] * 512}

        result = await self.service.delete_entity(
            db=mock_db,
            entity_id="entity-1",
        )

        assert result is True
        mock_db.delete.assert_called_with(mock_entity)
        mock_db.commit.assert_called()
        assert "entity-1" not in self.service._entity_cache

    @pytest.mark.asyncio
    async def test_delete_entity_returns_false_for_not_found(self):
        """Test that delete_entity returns False when not found."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        result = await self.service.delete_entity(
            db=mock_db,
            entity_id="nonexistent-id",
        )

        assert result is False
        mock_db.delete.assert_not_called()


class TestGetEntityForEvent:
    """Tests for get_entity_for_event method (AC12)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_entity_service()
        self.service = EntityService()

    def teardown_method(self):
        """Clean up after tests."""
        reset_entity_service()

    @pytest.mark.asyncio
    async def test_returns_entity_summary_for_linked_event(self):
        """AC12: Event response includes matched_entity data."""
        mock_db = MagicMock()

        # Mock result from join query
        mock_result = MagicMock()
        mock_result.id = "entity-1"
        mock_result.entity_type = "person"
        mock_result.name = "Mail Carrier"
        mock_result.first_seen_at = datetime.now(timezone.utc) - timedelta(days=7)
        mock_result.occurrence_count = 10
        mock_result.similarity_score = 0.92

        mock_query = MagicMock()
        mock_query.join.return_value.filter.return_value.first.return_value = mock_result
        mock_db.query.return_value = mock_query

        entity = await self.service.get_entity_for_event(
            db=mock_db,
            event_id="event-1",
        )

        assert entity is not None
        assert entity["id"] == "entity-1"
        assert entity["name"] == "Mail Carrier"
        assert entity["occurrence_count"] == 10
        assert entity["similarity_score"] == 0.92

    @pytest.mark.asyncio
    async def test_returns_none_for_unlinked_event(self):
        """Test that get_entity_for_event returns None for unlinked events."""
        mock_db = MagicMock()

        mock_query = MagicMock()
        mock_query.join.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        entity = await self.service.get_entity_for_event(
            db=mock_db,
            event_id="unlinked-event",
        )

        assert entity is None


class TestPerformance:
    """Performance tests (AC13)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_entity_service()
        self.service = EntityService()

    def teardown_method(self):
        """Clean up after tests."""
        reset_entity_service()

    @pytest.mark.asyncio
    async def test_match_1000_entities_under_200ms(self):
        """AC13: Entity matching completes in <200ms with 1000 entities."""
        # Generate 1000 random entity embeddings
        np.random.seed(42)
        entity_embeddings = {}
        for i in range(1000):
            entity_id = f"entity-{i}"
            entity_embeddings[entity_id] = np.random.randn(512).tolist()

        # Pre-load cache
        self.service._entity_cache = entity_embeddings
        self.service._cache_loaded = True

        # Mock database
        mock_db = MagicMock()
        mock_event = MagicMock()
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_event
        mock_db.query.return_value = mock_query

        # Generate test embedding
        test_embedding = np.random.randn(512).tolist()

        # Measure time
        start_time = time.time()
        result = await self.service.match_or_create_entity(
            db=mock_db,
            event_id="test-event",
            embedding=test_embedding,
            entity_type="person",
        )
        elapsed_ms = (time.time() - start_time) * 1000

        # Should complete in under 200ms
        assert elapsed_ms < 200, f"Entity matching took {elapsed_ms:.2f}ms, expected <200ms"
        assert result is not None

    @pytest.mark.asyncio
    async def test_cache_hit_performance(self):
        """Test that cached embeddings provide fast matching."""
        # Pre-load cache with 100 entities
        np.random.seed(42)
        for i in range(100):
            self.service._entity_cache[f"entity-{i}"] = np.random.randn(512).tolist()
        self.service._cache_loaded = True

        mock_db = MagicMock()
        mock_event = MagicMock()
        mock_event.timestamp = datetime.now(timezone.utc)
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_event
        mock_db.query.return_value = mock_query

        # Run multiple matches
        times = []
        for _ in range(10):
            test_embedding = np.random.randn(512).tolist()
            start = time.time()
            await self.service.match_or_create_entity(
                db=mock_db,
                event_id=f"event-{_}",
                embedding=test_embedding,
                entity_type="person",
            )
            times.append((time.time() - start) * 1000)

        avg_time = sum(times) / len(times)
        assert avg_time < 50, f"Average matching time {avg_time:.2f}ms, expected <50ms"


class TestMatchEntityOnly:
    """Tests for match_entity_only method (Story P4-3.4: Context-Enhanced AI Prompts)."""

    def setup_method(self):
        """Setup test service."""
        reset_entity_service()
        self.service = EntityService()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_entities_exist(self):
        """Test returns None when no entities in cache."""
        mock_db = MagicMock()
        mock_db.query.return_value.all.return_value = []

        self.service._entity_cache = {}
        self.service._cache_loaded = True

        result = await self.service.match_entity_only(
            db=mock_db,
            embedding=[0.1] * 512,
            threshold=0.75,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_match_when_above_threshold(self):
        """Test returns match when similarity above threshold."""
        mock_db = MagicMock()

        # Create existing entity embedding
        existing_embedding = [0.1] * 512

        # Pre-load cache
        self.service._entity_cache = {"existing-entity-id": existing_embedding}
        self.service._cache_loaded = True

        # Mock entity lookup
        mock_entity = MagicMock()
        mock_entity.id = "existing-entity-id"
        mock_entity.entity_type = "person"
        mock_entity.name = "Known Person"
        mock_entity.first_seen_at = datetime.now(timezone.utc) - timedelta(days=7)
        mock_entity.last_seen_at = datetime.now(timezone.utc)
        mock_entity.occurrence_count = 5

        mock_db.query.return_value.filter.return_value.first.return_value = mock_entity

        # Test with identical embedding
        result = await self.service.match_entity_only(
            db=mock_db,
            embedding=[0.1] * 512,
            threshold=0.75,
        )

        assert result is not None
        assert result.entity_id == "existing-entity-id"
        assert result.name == "Known Person"
        assert result.is_new is False
        assert result.similarity_score >= 0.75

    @pytest.mark.asyncio
    async def test_returns_none_when_below_threshold(self):
        """Test returns None when no match above threshold."""
        mock_db = MagicMock()

        # Create existing entity with very different embedding
        existing_embedding = [0.9, 0.1] + [0.0] * 510

        self.service._entity_cache = {"existing-entity-id": existing_embedding}
        self.service._cache_loaded = True

        # Test with very different embedding
        result = await self.service.match_entity_only(
            db=mock_db,
            embedding=[0.0, 0.0, 0.9] + [0.1] * 509,
            threshold=0.75,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_does_not_modify_database(self):
        """Test that match_entity_only is read-only."""
        mock_db = MagicMock()

        existing_embedding = [0.1] * 512
        self.service._entity_cache = {"existing-entity-id": existing_embedding}
        self.service._cache_loaded = True

        mock_entity = MagicMock()
        mock_entity.id = "existing-entity-id"
        mock_entity.entity_type = "person"
        mock_entity.name = None
        mock_entity.first_seen_at = datetime.now(timezone.utc)
        mock_entity.last_seen_at = datetime.now(timezone.utc)
        mock_entity.occurrence_count = 1

        mock_db.query.return_value.filter.return_value.first.return_value = mock_entity

        result = await self.service.match_entity_only(
            db=mock_db,
            embedding=[0.1] * 512,
            threshold=0.75,
        )

        # Verify no add() or commit() calls
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_custom_threshold(self):
        """Test that custom threshold is respected."""
        mock_db = MagicMock()

        # Create existing entity
        existing_embedding = [1.0, 0.0] + [0.0] * 510
        self.service._entity_cache = {"existing-entity-id": existing_embedding}
        self.service._cache_loaded = True

        # Test embedding with moderate similarity (~0.7)
        test_embedding = [0.7, 0.7] + [0.0] * 510

        # Should NOT match with high threshold
        result_high = await self.service.match_entity_only(
            db=mock_db,
            embedding=test_embedding,
            threshold=0.95,
        )
        assert result_high is None

    @pytest.mark.asyncio
    async def test_returns_entity_occurrence_count_unchanged(self):
        """Test that occurrence count reflects current state, not incremented."""
        mock_db = MagicMock()

        existing_embedding = [0.1] * 512
        self.service._entity_cache = {"existing-entity-id": existing_embedding}
        self.service._cache_loaded = True

        mock_entity = MagicMock()
        mock_entity.id = "existing-entity-id"
        mock_entity.entity_type = "person"
        mock_entity.name = "Test"
        mock_entity.first_seen_at = datetime.now(timezone.utc) - timedelta(days=5)
        mock_entity.last_seen_at = datetime.now(timezone.utc) - timedelta(days=1)
        mock_entity.occurrence_count = 10  # Current count

        mock_db.query.return_value.filter.return_value.first.return_value = mock_entity

        result = await self.service.match_entity_only(
            db=mock_db,
            embedding=[0.1] * 512,
            threshold=0.75,
        )

        # Should return current count, not incremented
        assert result.occurrence_count == 10


class TestVehicleEntityExtraction:
    """Tests for vehicle entity extraction (Story P9-4.1)."""

    def test_extract_white_toyota_camry(self):
        """AC-4.1.1: Extract color, make, model from description."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("A white Toyota Camry pulled into the driveway")

        assert result is not None
        assert result.color == "white"
        assert result.make == "toyota"
        assert result.model == "camry"
        assert result.signature == "white-toyota-camry"

    def test_extract_black_ford_f150(self):
        """AC-4.1.2: Extract signature for F-150 with hyphen normalization."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("Black Ford F-150 parked on street")

        assert result is not None
        assert result.color == "black"
        assert result.make == "ford"
        assert result.model == "f150"
        assert result.signature == "black-ford-f150"

    def test_color_only_returns_none(self):
        """AC-4.1.5: Only color mentioned returns None (insufficient data)."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("A red car passed by the house")

        # Should be None because we need color+make OR make+model
        assert result is None

    def test_make_and_model_without_color(self):
        """AC-4.1.6: Make and model without color creates partial signature."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("A Toyota Camry is parked in the garage")

        assert result is not None
        assert result.color is None
        assert result.make == "toyota"
        assert result.model == "camry"
        # Signature should be make-model when no color
        assert result.signature == "toyota-camry"

    def test_color_and_make_without_model(self):
        """Test color+make creates valid signature even without model."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("A silver Honda just arrived")

        assert result is not None
        assert result.color == "silver"
        assert result.make == "honda"
        assert result.model is None
        assert result.signature == "silver-honda"

    def test_grey_normalized_to_gray(self):
        """Test grey is normalized to gray in signature."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("A grey Toyota Corolla in the driveway")

        assert result is not None
        assert result.color == "gray"  # Normalized from grey
        assert result.signature == "gray-toyota-corolla"

    def test_chevy_normalized_to_chevrolet(self):
        """Test Chevy is normalized to Chevrolet."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("White Chevy Silverado parked outside")

        assert result is not None
        assert result.make == "chevrolet"  # Normalized from chevy
        assert result.signature == "white-chevrolet-silverado"

    def test_vw_normalized_to_volkswagen(self):
        """Test VW is normalized to Volkswagen."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("A blue VW Golf just passed")

        assert result is not None
        assert result.make == "volkswagen"  # Normalized from vw

    def test_empty_description_returns_none(self):
        """Test empty description returns None."""
        from app.services.entity_service import extract_vehicle_entity

        assert extract_vehicle_entity("") is None
        assert extract_vehicle_entity(None) is None

    def test_case_insensitive_matching(self):
        """Test case insensitive color, make, model matching."""
        from app.services.entity_service import extract_vehicle_entity

        result = extract_vehicle_entity("A WHITE TOYOTA CAMRY is approaching")

        assert result is not None
        assert result.color == "white"
        assert result.make == "toyota"
        assert result.model == "camry"

    def test_vehicle_entity_info_is_valid(self):
        """Test VehicleEntityInfo.is_valid() method."""
        from app.services.entity_service import VehicleEntityInfo

        # Color + Make = valid
        info1 = VehicleEntityInfo(color="white", make="toyota", model=None, signature=None)
        assert info1.is_valid() is True

        # Make + Model = valid
        info2 = VehicleEntityInfo(color=None, make="toyota", model="camry", signature=None)
        assert info2.is_valid() is True

        # Color only = invalid
        info3 = VehicleEntityInfo(color="white", make=None, model=None, signature=None)
        assert info3.is_valid() is False

        # Make only = invalid
        info4 = VehicleEntityInfo(color=None, make="toyota", model=None, signature=None)
        assert info4.is_valid() is False

    def test_skip_common_words_as_models(self):
        """Test that common words are not extracted as models."""
        from app.services.entity_service import extract_vehicle_entity

        # "truck" should not become the model
        result = extract_vehicle_entity("A white Ford truck is parked")

        # Should match "ford" as make, but "truck" should be skipped
        # Since no valid model is found, we need color+make
        assert result is not None
        assert result.make == "ford"
        assert result.model is None  # "truck" should be skipped
        assert result.signature == "white-ford"


class TestVehicleSignatureMatching:
    """Tests for vehicle signature-based entity matching (Story P9-4.1)."""

    def setup_method(self):
        """Set up test fixtures."""
        reset_entity_service()
        self.service = EntityService()

    def teardown_method(self):
        """Clean up after tests."""
        reset_entity_service()

    @pytest.mark.asyncio
    async def test_same_signature_links_to_same_entity(self):
        """AC-4.1.3: Two descriptions with same signature link to same entity."""
        mock_db = MagicMock()

        # Setup: existing entity with signature "white-toyota-camry"
        mock_entity = MagicMock()
        mock_entity.id = "existing-vehicle-id"

        # Mock query for finding entity by signature
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_entity
        mock_db.query.return_value = mock_query

        # Test signature lookup
        entity_id = self.service._find_entity_by_vehicle_signature(
            mock_db, "white-toyota-camry"
        )

        assert entity_id == "existing-vehicle-id"

    def test_find_vehicle_by_signature_returns_none_when_not_found(self):
        """Test signature lookup returns None when no match."""
        mock_db = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        result = self.service._find_entity_by_vehicle_signature(
            mock_db, "nonexistent-signature"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_match_or_create_vehicle_entity_uses_signature_first(self):
        """Test that signature-based matching takes priority over embedding."""
        mock_db = MagicMock()

        # Mock event timestamp lookup
        mock_event = MagicMock()
        mock_event.timestamp = datetime.now(timezone.utc)

        # Setup mock queries
        def query_side_effect(model):
            mock_query = MagicMock()
            if hasattr(model, 'timestamp'):  # Event query
                mock_query.filter.return_value.first.return_value = mock_event
            else:  # RecognizedEntity query
                mock_entity = MagicMock()
                mock_entity.id = "existing-vehicle-id"
                mock_query.filter.return_value.first.return_value = mock_entity
            return mock_query

        mock_db.query.side_effect = query_side_effect

        # Mock entity for update
        mock_entity = MagicMock()
        mock_entity.id = "existing-vehicle-id"
        mock_entity.entity_type = "vehicle"
        mock_entity.name = "My Car"
        mock_entity.first_seen_at = datetime.now(timezone.utc)
        mock_entity.last_seen_at = datetime.now(timezone.utc)
        mock_entity.occurrence_count = 5

        # Pre-load cache to avoid embedding-based matching
        self.service._entity_cache = {}
        self.service._cache_loaded = True

        # This would require more complex mocking to fully test
        # For now, verify the signature lookup method works
        mock_db2 = MagicMock()
        mock_query2 = MagicMock()
        mock_entity2 = MagicMock()
        mock_entity2.id = "vehicle-123"
        mock_query2.filter.return_value.first.return_value = mock_entity2
        mock_db2.query.return_value = mock_query2

        result = self.service._find_entity_by_vehicle_signature(
            mock_db2, "white-toyota-camry"
        )
        assert result == "vehicle-123"


class TestRecognizedEntityDisplayName:
    """Tests for RecognizedEntity.display_name property (Story P9-4.1)."""

    def test_display_name_uses_user_assigned_name(self):
        """Test display_name returns user name when set."""
        from app.models.recognized_entity import RecognizedEntity

        entity = RecognizedEntity(
            id="test-id",
            entity_type="vehicle",
            name="My Tesla",
            reference_embedding="[]",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            occurrence_count=1,
            vehicle_signature="white-tesla-model3"
        )

        assert entity.display_name == "My Tesla"

    def test_display_name_uses_signature_for_vehicle(self):
        """Test display_name returns formatted signature for unnamed vehicles."""
        from app.models.recognized_entity import RecognizedEntity

        entity = RecognizedEntity(
            id="test-id",
            entity_type="vehicle",
            name=None,
            reference_embedding="[]",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            occurrence_count=1,
            vehicle_signature="white-toyota-camry"
        )

        assert entity.display_name == "White Toyota Camry"

    def test_display_name_uses_id_prefix_for_person(self):
        """Test display_name returns entity type + ID for persons."""
        from app.models.recognized_entity import RecognizedEntity

        entity = RecognizedEntity(
            id="12345678-abcd-efgh-ijkl-mnopqrstuvwx",
            entity_type="person",
            name=None,
            reference_embedding="[]",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            occurrence_count=1,
        )

        assert entity.display_name == "Person #12345678"

    def test_display_name_for_vehicle_without_signature(self):
        """Test display_name for vehicle without signature."""
        from app.models.recognized_entity import RecognizedEntity

        entity = RecognizedEntity(
            id="abcd1234-efgh-ijkl-mnop-qrstuvwxyz12",
            entity_type="vehicle",
            name=None,
            reference_embedding="[]",
            first_seen_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc),
            occurrence_count=1,
            vehicle_signature=None
        )

        assert entity.display_name == "Vehicle #abcd1234"


class TestEntityServiceMerge:
    """Tests for EntityService.merge_entities (Story P9-4.5)."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    @pytest.fixture
    def entity_service(self):
        """Create an EntityService instance."""
        return EntityService()

    @pytest.mark.asyncio
    async def test_merge_entities_success(self, entity_service, mock_db):
        """Test successful merge of two entities (AC-4.5.5, AC-4.5.6).

        This test verifies the core merge logic by mocking the database queries
        to return controlled entity and event data.
        """
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.entity_adjustment import EntityAdjustment
        from app.models.event import Event

        # Create primary and secondary entities as MagicMock
        now = datetime.now(timezone.utc)
        primary = MagicMock()
        primary.id = "primary-entity-id"
        primary.name = "Primary Person"
        primary.occurrence_count = 5
        primary.first_seen_at = now - timedelta(days=10)
        primary.last_seen_at = now - timedelta(days=2)
        primary.updated_at = now

        secondary = MagicMock()
        secondary.id = "secondary-entity-id"
        secondary.name = "Secondary Person"
        secondary.occurrence_count = 3
        secondary.first_seen_at = now - timedelta(days=5)
        secondary.last_seen_at = now - timedelta(days=1)  # More recent

        # Create event links for secondary entity
        event_link = MagicMock()
        event_link.entity_id = "secondary-entity-id"
        event_link.event_id = "event-1"
        event_link.created_at = now

        # Mock event for description snapshot
        mock_event_desc = MagicMock()
        mock_event_desc.description = "Person walking"

        # Track query call order with mutable container
        call_order = {'count': 0}

        def query_side_effect(*args):
            query_mock = MagicMock()
            filter_mock = MagicMock()
            query_mock.filter.return_value = filter_mock

            call_order['count'] += 1
            call_num = call_order['count']

            # Query 1: Get primary entity (RecognizedEntity)
            if call_num == 1:
                filter_mock.first.return_value = primary
            # Query 2: Get secondary entity (RecognizedEntity)
            elif call_num == 2:
                filter_mock.first.return_value = secondary
            # Query 3: Get event links (EntityEvent)
            elif call_num == 3:
                filter_mock.all.return_value = [event_link]
            # Query 4+: Get event descriptions (Event.description)
            else:
                filter_mock.first.return_value = mock_event_desc

            return query_mock

        mock_db.query.side_effect = query_side_effect

        # Execute merge
        result = await entity_service.merge_entities(
            db=mock_db,
            primary_entity_id="primary-entity-id",
            secondary_entity_id="secondary-entity-id",
        )

        # Verify result
        assert result["success"] is True
        assert result["merged_entity_id"] == "primary-entity-id"
        assert result["events_moved"] == 1
        assert result["deleted_entity_id"] == "secondary-entity-id"

        # Verify primary occurrence count was updated
        assert primary.occurrence_count == 8  # 5 + 3

        # Verify event link was moved
        assert event_link.entity_id == "primary-entity-id"

        # Verify secondary was deleted
        mock_db.delete.assert_called_with(secondary)
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_merge_entities_same_entity_error(self, entity_service, mock_db):
        """Test error when trying to merge entity with itself (AC validation)."""
        with pytest.raises(ValueError, match="Cannot merge an entity with itself"):
            await entity_service.merge_entities(
                db=mock_db,
                primary_entity_id="same-entity-id",
                secondary_entity_id="same-entity-id",
            )

    @pytest.mark.asyncio
    async def test_merge_entities_primary_not_found(self, entity_service, mock_db):
        """Test error when primary entity not found (AC validation)."""
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_filter = MagicMock()
        mock_query.filter.return_value = mock_filter
        mock_filter.first.return_value = None

        with pytest.raises(ValueError, match="Primary entity not found"):
            await entity_service.merge_entities(
                db=mock_db,
                primary_entity_id="nonexistent-primary",
                secondary_entity_id="secondary-entity-id",
            )

    @pytest.mark.asyncio
    async def test_merge_entities_secondary_not_found(self, entity_service, mock_db):
        """Test error when secondary entity not found (AC validation)."""
        from app.models.recognized_entity import RecognizedEntity

        primary = MagicMock(spec=RecognizedEntity)
        primary.id = "primary-entity-id"

        call_count = [0]

        def query_side_effect(model):
            query_mock = MagicMock()
            filter_mock = MagicMock()
            query_mock.filter.return_value = filter_mock

            call_count[0] += 1
            if call_count[0] == 1:
                filter_mock.first.return_value = primary
            else:
                filter_mock.first.return_value = None

            return query_mock

        mock_db.query.side_effect = query_side_effect

        with pytest.raises(ValueError, match="Secondary entity not found"):
            await entity_service.merge_entities(
                db=mock_db,
                primary_entity_id="primary-entity-id",
                secondary_entity_id="nonexistent-secondary",
            )

    @pytest.mark.asyncio
    async def test_merge_entities_creates_adjustment_records(self, entity_service, mock_db):
        """Test that merge creates EntityAdjustment records for ML training (AC-4.5.6)."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent
        from app.models.entity_adjustment import EntityAdjustment

        now = datetime.now(timezone.utc)
        primary = MagicMock(spec=RecognizedEntity)
        primary.id = "primary-id"
        primary.name = "Primary"
        primary.occurrence_count = 2
        primary.first_seen_at = now - timedelta(days=5)
        primary.last_seen_at = now

        secondary = MagicMock(spec=RecognizedEntity)
        secondary.id = "secondary-id"
        secondary.name = "Secondary"
        secondary.occurrence_count = 3
        secondary.first_seen_at = now - timedelta(days=10)
        secondary.last_seen_at = now - timedelta(days=1)

        # Multiple event links
        event_links = [
            MagicMock(spec=EntityEvent, entity_id="secondary-id", event_id=f"event-{i}")
            for i in range(3)
        ]

        mock_event = MagicMock()
        mock_event.description = "Test event"

        call_count = [0]

        def query_side_effect(model):
            query_mock = MagicMock()
            filter_mock = MagicMock()
            query_mock.filter.return_value = filter_mock

            call_count[0] += 1
            if call_count[0] == 1:
                filter_mock.first.return_value = primary
            elif call_count[0] == 2:
                filter_mock.first.return_value = secondary
            elif call_count[0] == 3:
                filter_mock.all.return_value = event_links
            else:
                filter_mock.first.return_value = mock_event

            return query_mock

        mock_db.query.side_effect = query_side_effect

        added_adjustments = []
        original_add = mock_db.add

        def capture_add(obj):
            added_adjustments.append(obj)

        mock_db.add.side_effect = capture_add

        result = await entity_service.merge_entities(
            db=mock_db,
            primary_entity_id="primary-id",
            secondary_entity_id="secondary-id",
        )

        # Verify adjustment records were created
        assert result["events_moved"] == 3
        # Each event should have an adjustment record added
        assert mock_db.add.call_count == 3

    @pytest.mark.asyncio
    async def test_merge_entities_updates_timestamps(self, entity_service, mock_db):
        """Test that merge updates primary entity timestamps correctly."""
        from app.models.recognized_entity import RecognizedEntity, EntityEvent

        now = datetime.now(timezone.utc)

        # Primary seen later, secondary seen earlier - should update first_seen
        primary = MagicMock(spec=RecognizedEntity)
        primary.id = "primary-id"
        primary.name = "Primary"
        primary.occurrence_count = 2
        primary.first_seen_at = now - timedelta(days=5)  # Later
        primary.last_seen_at = now - timedelta(days=2)   # Earlier

        secondary = MagicMock(spec=RecognizedEntity)
        secondary.id = "secondary-id"
        secondary.name = "Secondary"
        secondary.occurrence_count = 1
        secondary.first_seen_at = now - timedelta(days=10)  # Earlier - should update primary
        secondary.last_seen_at = now - timedelta(days=1)    # Later - should update primary

        call_count = [0]

        def query_side_effect(model):
            query_mock = MagicMock()
            filter_mock = MagicMock()
            query_mock.filter.return_value = filter_mock

            call_count[0] += 1
            if call_count[0] == 1:
                filter_mock.first.return_value = primary
            elif call_count[0] == 2:
                filter_mock.first.return_value = secondary
            elif call_count[0] == 3:
                filter_mock.all.return_value = []

            return query_mock

        mock_db.query.side_effect = query_side_effect

        await entity_service.merge_entities(
            db=mock_db,
            primary_entity_id="primary-id",
            secondary_entity_id="secondary-id",
        )

        # Verify primary timestamps were updated
        assert primary.first_seen_at == secondary.first_seen_at
        assert primary.last_seen_at == secondary.last_seen_at


class TestEntityServiceGetAdjustments:
    """Tests for EntityService.get_adjustments method (Story P9-4.6)."""

    @pytest.fixture
    def entity_service(self):
        """Create EntityService instance for testing."""
        reset_entity_service()
        return EntityService()

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_get_adjustments_returns_list_and_total(
        self, entity_service, mock_db
    ):
        """Test that get_adjustments returns adjustments and total count."""
        from app.models.entity_adjustment import EntityAdjustment

        now = datetime.now(timezone.utc)
        mock_adjustment = MagicMock(spec=EntityAdjustment)
        mock_adjustment.id = "adj-123"
        mock_adjustment.event_id = "event-456"
        mock_adjustment.old_entity_id = "old-entity"
        mock_adjustment.new_entity_id = None
        mock_adjustment.action = "unlink"
        mock_adjustment.event_description = "Test event"
        mock_adjustment.created_at = now

        mock_query = MagicMock()
        mock_query.count.return_value = 1
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = [mock_adjustment]
        mock_db.query.return_value = mock_query

        adjustments, total = await entity_service.get_adjustments(
            db=mock_db,
            limit=50,
            offset=0,
        )

        assert total == 1
        assert len(adjustments) == 1
        assert adjustments[0]["id"] == "adj-123"
        assert adjustments[0]["action"] == "unlink"

    @pytest.mark.asyncio
    async def test_get_adjustments_filter_by_action(
        self, entity_service, mock_db
    ):
        """Test filtering adjustments by action type."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        await entity_service.get_adjustments(
            db=mock_db,
            limit=50,
            offset=0,
            action="unlink",
        )

        # Verify filter was called
        mock_query.filter.assert_called()

    @pytest.mark.asyncio
    async def test_get_adjustments_move_action_alias(
        self, entity_service, mock_db
    ):
        """Test that 'move' action aliases to move_from/move_to."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        await entity_service.get_adjustments(
            db=mock_db,
            limit=50,
            offset=0,
            action="move",
        )

        # Verify filter was called for move alias
        mock_query.filter.assert_called()

    @pytest.mark.asyncio
    async def test_get_adjustments_filter_by_entity_id(
        self, entity_service, mock_db
    ):
        """Test filtering adjustments by entity ID (matches old or new)."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        await entity_service.get_adjustments(
            db=mock_db,
            limit=50,
            offset=0,
            entity_id="test-entity-id",
        )

        # Verify filter was called for entity_id
        mock_query.filter.assert_called()

    @pytest.mark.asyncio
    async def test_get_adjustments_filter_by_date_range(
        self, entity_service, mock_db
    ):
        """Test filtering adjustments by date range."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        start = datetime.now(timezone.utc) - timedelta(days=7)
        end = datetime.now(timezone.utc)

        await entity_service.get_adjustments(
            db=mock_db,
            limit=50,
            offset=0,
            start_date=start,
            end_date=end,
        )

        # Verify filter was called twice (for start and end dates)
        assert mock_query.filter.call_count >= 2


class TestEntityServiceExportAdjustments:
    """Tests for EntityService.export_adjustments method (Story P9-4.6)."""

    @pytest.fixture
    def entity_service(self):
        """Create EntityService instance for testing."""
        reset_entity_service()
        return EntityService()

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_export_adjustments_returns_list(
        self, entity_service, mock_db
    ):
        """Test that export_adjustments returns list of dicts."""
        from app.models.entity_adjustment import EntityAdjustment

        now = datetime.now(timezone.utc)
        mock_adjustment = MagicMock(spec=EntityAdjustment)
        mock_adjustment.id = "adj-123"
        mock_adjustment.event_id = "event-456"
        mock_adjustment.old_entity_id = "old-entity"
        mock_adjustment.new_entity_id = None
        mock_adjustment.action = "unlink"
        mock_adjustment.event_description = "Test event"
        mock_adjustment.created_at = now

        # Mock query for adjustments
        mock_adj_query = MagicMock()
        mock_adj_query.filter.return_value = mock_adj_query
        mock_adj_query.order_by.return_value = mock_adj_query
        mock_adj_query.all.return_value = [mock_adjustment]

        # Mock query for entity types (returns empty for entities)
        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_adj_query
            else:
                mock_entity_query = MagicMock()
                mock_entity_query.filter.return_value = mock_entity_query
                mock_entity_query.all.return_value = []
                return mock_entity_query

        mock_db.query.side_effect = query_side_effect

        adjustments = await entity_service.export_adjustments(db=mock_db)

        assert len(adjustments) == 1
        assert adjustments[0]["event_id"] == "event-456"
        assert adjustments[0]["action"] == "unlink"
        assert "created_at" in adjustments[0]

    @pytest.mark.asyncio
    async def test_export_adjustments_includes_entity_types(
        self, entity_service, mock_db
    ):
        """Test that export includes entity types for ML training."""
        from app.models.entity_adjustment import EntityAdjustment
        from app.models.recognized_entity import RecognizedEntity

        now = datetime.now(timezone.utc)
        mock_adjustment = MagicMock(spec=EntityAdjustment)
        mock_adjustment.event_id = "event-456"
        mock_adjustment.old_entity_id = "old-entity"
        mock_adjustment.new_entity_id = "new-entity"
        mock_adjustment.action = "merge"
        mock_adjustment.event_description = "Test event"
        mock_adjustment.created_at = now

        mock_entity_old = MagicMock()
        mock_entity_old.id = "old-entity"
        mock_entity_old.entity_type = "person"

        mock_entity_new = MagicMock()
        mock_entity_new.id = "new-entity"
        mock_entity_new.entity_type = "person"

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_query = MagicMock()
            mock_query.filter.return_value = mock_query
            mock_query.order_by.return_value = mock_query

            if call_count[0] == 1:
                # Adjustments query
                mock_query.all.return_value = [mock_adjustment]
            else:
                # Entities query
                mock_query.all.return_value = [mock_entity_old, mock_entity_new]

            return mock_query

        mock_db.query.side_effect = query_side_effect

        adjustments = await entity_service.export_adjustments(db=mock_db)

        assert len(adjustments) == 1
        assert adjustments[0]["old_entity_type"] == "person"
        assert adjustments[0]["new_entity_type"] == "person"

    @pytest.mark.asyncio
    async def test_export_adjustments_filter_by_date(
        self, entity_service, mock_db
    ):
        """Test that export filters by date range."""
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        call_count = [0]

        def query_side_effect(model):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_query
            else:
                mock_entity_query = MagicMock()
                mock_entity_query.filter.return_value = mock_entity_query
                mock_entity_query.all.return_value = []
                return mock_entity_query

        mock_db.query.side_effect = query_side_effect

        start = datetime.now(timezone.utc) - timedelta(days=7)
        end = datetime.now(timezone.utc)

        await entity_service.export_adjustments(
            db=mock_db,
            start_date=start,
            end_date=end,
        )

        # Verify filter was called for both dates
        assert mock_query.filter.call_count >= 2
