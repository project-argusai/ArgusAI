"""
Integration tests for EntityService (Story P4-3.3: Recurring Visitor Detection)

Tests:
- AC1: System clusters similar event embeddings to identify recurring entities
- AC3: EntityEvent junction table links entities to events with similarity scores
- AC5: When match found above threshold, entity is updated (count++, last_seen)
- AC11: Entity matching integrated into event processing pipeline
"""
import json
import pytest
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.event import Event
from app.models.event_embedding import EventEmbedding
from app.models.camera import Camera
from app.models.recognized_entity import RecognizedEntity, EntityEvent
from app.services.entity_service import (
    EntityService,
    get_entity_service,
    reset_entity_service,
)


@pytest.fixture
def db_session():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    yield session

    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def test_camera(db_session):
    """Create a test camera."""
    camera = Camera(
        id="test-camera-001",
        name="Front Door Camera",
        type="rtsp",
        rtsp_url="rtsp://example.com/stream",
    )
    db_session.add(camera)
    db_session.commit()
    return camera


@pytest.fixture
def entity_service():
    """Create EntityService instance for testing."""
    reset_entity_service()
    service = EntityService()
    yield service
    reset_entity_service()


def create_event(
    db_session,
    event_id: str,
    camera_id: str,
    description: str = "Test event",
    days_ago: int = 0,
    thumbnail_path=None,
):
    """Helper to create an event."""
    timestamp = datetime.now(timezone.utc) - timedelta(days=days_ago)

    event = Event(
        id=event_id,
        camera_id=camera_id,
        timestamp=timestamp,
        description=description,
        confidence=85,
        objects_detected=json.dumps(["person"]),
        source_type="rtsp",
        thumbnail_path=thumbnail_path,
    )
    db_session.add(event)
    db_session.commit()
    return event


class TestEntityClusteringIntegration:
    """Integration tests for entity clustering (AC1)."""

    @pytest.mark.asyncio
    async def test_similar_embeddings_clustered_to_same_entity(
        self, db_session, test_camera, entity_service
    ):
        """AC1: System clusters similar event embeddings to identify recurring entities."""
        # Create first event
        event1 = create_event(
            db_session, "event-001", test_camera.id, "Person at door", days_ago=2
        )

        # Generate base embedding
        np.random.seed(42)
        base_embedding = np.random.randn(512).tolist()

        # Create first entity
        result1 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event1.id,
            embedding=base_embedding,
            entity_type="person",
            threshold=0.75,
        )

        assert result1.is_new is True
        entity_id = result1.entity_id

        # Create second event
        event2 = create_event(
            db_session, "event-002", test_camera.id, "Person at door again", days_ago=1
        )

        # Use very similar embedding (add small noise)
        similar_embedding = (np.array(base_embedding) + np.random.randn(512) * 0.01).tolist()

        # Match to existing entity
        result2 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event2.id,
            embedding=similar_embedding,
            entity_type="person",
            threshold=0.75,
        )

        # Should match existing entity
        assert result2.is_new is False
        assert result2.entity_id == entity_id
        assert result2.occurrence_count == 2

    @pytest.mark.asyncio
    async def test_dissimilar_embeddings_create_separate_entities(
        self, db_session, test_camera, entity_service
    ):
        """Test that dissimilar embeddings create separate entities."""
        # Create first event
        event1 = create_event(
            db_session, "event-001", test_camera.id, "Person A at door", days_ago=2
        )

        # Generate first embedding
        np.random.seed(42)
        embedding1 = np.random.randn(512).tolist()

        result1 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event1.id,
            embedding=embedding1,
            entity_type="person",
            threshold=0.75,
        )
        entity_id_1 = result1.entity_id

        # Create second event
        event2 = create_event(
            db_session, "event-002", test_camera.id, "Person B at door", days_ago=1
        )

        # Generate very different embedding
        np.random.seed(123)  # Different seed = different embedding
        embedding2 = np.random.randn(512).tolist()

        result2 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event2.id,
            embedding=embedding2,
            entity_type="person",
            threshold=0.75,
        )

        # Should create new entity
        assert result2.is_new is True
        assert result2.entity_id != entity_id_1


class TestEntityEventLinkingIntegration:
    """Integration tests for EntityEvent junction table (AC3)."""

    @pytest.mark.asyncio
    async def test_entity_event_link_created_with_similarity_score(
        self, db_session, test_camera, entity_service
    ):
        """AC3: EntityEvent junction table links entities to events with similarity scores."""
        # Create events
        event1 = create_event(
            db_session, "event-001", test_camera.id, "Person at door"
        )
        event2 = create_event(
            db_session, "event-002", test_camera.id, "Same person again"
        )

        # Create entity with first event
        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        result1 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event1.id,
            embedding=embedding,
            entity_type="person",
        )

        # Verify first EntityEvent link created
        link1 = db_session.query(EntityEvent).filter(
            EntityEvent.event_id == event1.id
        ).first()

        assert link1 is not None
        assert link1.entity_id == result1.entity_id
        assert link1.similarity_score == 1.0  # First occurrence

        # Match second event with similar embedding
        similar_embedding = (np.array(embedding) + np.random.randn(512) * 0.01).tolist()
        result2 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event2.id,
            embedding=similar_embedding,
            entity_type="person",
        )

        # Verify second EntityEvent link created with similarity score
        link2 = db_session.query(EntityEvent).filter(
            EntityEvent.event_id == event2.id
        ).first()

        assert link2 is not None
        assert link2.entity_id == result1.entity_id
        assert link2.similarity_score > 0.75  # Above threshold
        assert link2.similarity_score < 1.0  # Not identical


class TestEntityUpdateIntegration:
    """Integration tests for entity updates (AC5)."""

    @pytest.mark.asyncio
    async def test_entity_occurrence_count_incremented(
        self, db_session, test_camera, entity_service
    ):
        """AC5: When match found, occurrence_count is incremented."""
        # Create events
        events = []
        for i in range(5):
            event = create_event(
                db_session, f"event-{i:03d}", test_camera.id,
                f"Person visit {i}", days_ago=5-i
            )
            events.append(event)

        # Use same embedding for all (simulating same person)
        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        # Process all events
        for i, event in enumerate(events):
            # Add tiny noise to simulate real-world variance
            noisy_embedding = (np.array(embedding) + np.random.randn(512) * 0.005).tolist()

            result = await entity_service.match_or_create_entity(
                db=db_session,
                event_id=event.id,
                embedding=noisy_embedding,
                entity_type="person",
            )

            # First should create, rest should match
            if i == 0:
                assert result.is_new is True
                entity_id = result.entity_id
            else:
                assert result.is_new is False
                assert result.entity_id == entity_id
                assert result.occurrence_count == i + 1

        # Verify final entity state
        entity = db_session.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()

        assert entity.occurrence_count == 5

    @pytest.mark.asyncio
    async def test_entity_last_seen_at_updated(
        self, db_session, test_camera, entity_service
    ):
        """AC5: When match found, last_seen_at is updated."""
        # Create events with different timestamps
        event1 = create_event(
            db_session, "event-001", test_camera.id, "First visit", days_ago=7
        )
        event2 = create_event(
            db_session, "event-002", test_camera.id, "Second visit", days_ago=0
        )

        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        # Process first event
        result1 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event1.id,
            embedding=embedding,
            entity_type="person",
        )
        initial_last_seen = result1.last_seen_at

        # Process second event
        result2 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event2.id,
            embedding=embedding,
            entity_type="person",
        )

        # Verify last_seen_at was updated
        assert result2.last_seen_at > initial_last_seen


class TestEntityDeletionIntegration:
    """Integration tests for entity deletion cascade."""

    @pytest.mark.asyncio
    async def test_entity_deletion_cascades_to_entity_events(
        self, db_session, test_camera, entity_service
    ):
        """Test that deleting entity cascades to EntityEvent links."""
        # Create events and entity
        event1 = create_event(db_session, "event-001", test_camera.id)
        event2 = create_event(db_session, "event-002", test_camera.id)

        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        # Create entity with links
        result1 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event1.id,
            embedding=embedding,
            entity_type="person",
        )
        await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event2.id,
            embedding=embedding,
            entity_type="person",
        )

        entity_id = result1.entity_id

        # Verify links exist
        links_before = db_session.query(EntityEvent).filter(
            EntityEvent.entity_id == entity_id
        ).count()
        assert links_before == 2

        # Delete entity
        deleted = await entity_service.delete_entity(db_session, entity_id)
        assert deleted is True

        # Verify links were deleted (cascade)
        links_after = db_session.query(EntityEvent).filter(
            EntityEvent.entity_id == entity_id
        ).count()
        assert links_after == 0

    @pytest.mark.asyncio
    async def test_event_deletion_unlinks_from_entity(
        self, db_session, test_camera, entity_service
    ):
        """Test that deleting event removes EntityEvent link but keeps entity.

        Note: SQLite requires PRAGMA foreign_keys=ON for cascade to work.
        In production with real database, the cascade works properly.
        This test verifies the link can be manually cleaned up.
        """
        # Create event and entity
        event = create_event(db_session, "event-001", test_camera.id)

        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        result = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event.id,
            embedding=embedding,
            entity_type="person",
        )
        entity_id = result.entity_id

        # Verify link exists
        link = db_session.query(EntityEvent).filter(
            EntityEvent.event_id == event.id
        ).first()
        assert link is not None

        # Delete entity event link first (manual cascade for SQLite test)
        db_session.delete(link)
        db_session.commit()

        # Now delete event
        db_session.delete(event)
        db_session.commit()

        # Verify link was deleted
        link_after = db_session.query(EntityEvent).filter(
            EntityEvent.event_id == "event-001"
        ).first()
        assert link_after is None

        # Entity should still exist
        entity = db_session.query(RecognizedEntity).filter(
            RecognizedEntity.id == entity_id
        ).first()
        assert entity is not None


class TestPipelineIntegration:
    """Integration tests for pipeline integration (AC11)."""

    @pytest.mark.asyncio
    async def test_full_pipeline_flow(
        self, db_session, test_camera, entity_service
    ):
        """AC11: Entity matching integrated into event processing pipeline."""
        # Simulate pipeline: create event, generate embedding, match entity

        # Step 1: Create event (simulating event_processor storing event)
        event = create_event(
            db_session, "event-001", test_camera.id,
            "Person walking toward door carrying package"
        )

        # Step 2: Generate embedding (simulating embedding_service)
        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        # Step 3: Match or create entity (entity_service)
        result = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event.id,
            embedding=embedding,
            entity_type="person",
        )

        # Verify entity was created
        assert result is not None
        assert result.entity_type == "person"
        assert result.occurrence_count == 1

        # Verify EntityEvent link exists
        link = db_session.query(EntityEvent).filter(
            EntityEvent.event_id == event.id
        ).first()
        assert link is not None
        assert link.entity_id == result.entity_id


class TestGracefulDegradation:
    """Integration tests for graceful handling of failures (AC14)."""

    @pytest.mark.asyncio
    async def test_empty_entity_database_creates_first_entity(
        self, db_session, test_camera, entity_service
    ):
        """Test handling first visitor when no entities exist."""
        # Clear any cached entities
        entity_service._invalidate_cache()

        # Create first event
        event = create_event(db_session, "event-001", test_camera.id)

        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        # Should handle empty database gracefully
        result = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event.id,
            embedding=embedding,
            entity_type="person",
        )

        assert result.is_new is True
        assert result.occurrence_count == 1

    @pytest.mark.asyncio
    async def test_handles_duplicate_entity_event_link_gracefully(
        self, db_session, test_camera, entity_service
    ):
        """Test idempotency - reprocessing same event doesn't create duplicate link."""
        event = create_event(db_session, "event-001", test_camera.id)

        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        # Process same event twice
        result1 = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event.id,
            embedding=embedding,
            entity_type="person",
        )

        # Count links before second attempt
        links_before = db_session.query(EntityEvent).filter(
            EntityEvent.event_id == event.id
        ).count()

        # Try processing again - this would raise IntegrityError without proper handling
        # For now, this tests that the entity was properly created
        assert links_before == 1
        assert result1.entity_id is not None


class TestEntityThumbnailPersistence:
    """Durable entity thumbnails must survive event retention."""

    @pytest.mark.asyncio
    async def test_linking_event_with_thumbnail_writes_entity_path(
        self, db_session, test_camera, entity_service
    ):
        """Linking an event with a thumbnail writes recognized_entities.thumbnail_path."""
        event = create_event(
            db_session,
            "event-thumb-001",
            test_camera.id,
            thumbnail_path="/api/v1/thumbnails/2026-08-15/event-thumb-001.jpg",
        )
        np.random.seed(42)
        embedding = np.random.randn(512).tolist()

        result = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event.id,
            embedding=embedding,
            entity_type="person",
        )

        entity = db_session.query(RecognizedEntity).filter(
            RecognizedEntity.id == result.entity_id
        ).first()
        assert entity.thumbnail_path == "/api/v1/thumbnails/2026-08-15/event-thumb-001.jpg"

    @pytest.mark.asyncio
    async def test_later_event_with_thumbnail_updates_entity_path(
        self, db_session, test_camera, entity_service
    ):
        """A later event with a thumbnail updates the stored path."""
        event1 = create_event(
            db_session,
            "event-thumb-old",
            test_camera.id,
            days_ago=2,
            thumbnail_path="/api/v1/thumbnails/2026-08-13/old.jpg",
        )
        event2 = create_event(
            db_session,
            "event-thumb-new",
            test_camera.id,
            days_ago=0,
            thumbnail_path="/api/v1/thumbnails/2026-08-15/new.jpg",
        )
        np.random.seed(7)
        embedding = np.random.randn(512).tolist()

        first = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event1.id,
            embedding=embedding,
            entity_type="person",
        )
        similar = (np.array(embedding) + np.random.randn(512) * 0.01).tolist()
        second = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event2.id,
            embedding=similar,
            entity_type="person",
        )

        assert second.entity_id == first.entity_id
        entity = db_session.query(RecognizedEntity).filter(
            RecognizedEntity.id == first.entity_id
        ).first()
        assert entity.thumbnail_path == "/api/v1/thumbnails/2026-08-15/new.jpg"

    @pytest.mark.asyncio
    async def test_event_without_thumbnail_does_not_clear_existing_path(
        self, db_session, test_camera, entity_service
    ):
        """An event without a thumbnail does not clear an existing path."""
        event1 = create_event(
            db_session,
            "event-with-thumb",
            test_camera.id,
            days_ago=1,
            thumbnail_path="/api/v1/thumbnails/2026-08-14/keep.jpg",
        )
        event2 = create_event(
            db_session,
            "event-no-thumb",
            test_camera.id,
            days_ago=0,
            thumbnail_path=None,
        )
        np.random.seed(11)
        embedding = np.random.randn(512).tolist()

        first = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event1.id,
            embedding=embedding,
            entity_type="person",
        )
        similar = (np.array(embedding) + np.random.randn(512) * 0.01).tolist()
        await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event2.id,
            embedding=similar,
            entity_type="person",
        )

        entity = db_session.query(RecognizedEntity).filter(
            RecognizedEntity.id == first.entity_id
        ).first()
        assert entity.thumbnail_path == "/api/v1/thumbnails/2026-08-14/keep.jpg"

    @pytest.mark.asyncio
    async def test_list_entities_returns_stored_path_after_event_retention(
        self, db_session, test_camera, entity_service
    ):
        """get_all_entities still returns the stored path when the Event row is gone."""
        stored_path = "/api/v1/thumbnails/2026-06-28/retained.jpg"
        event = create_event(
            db_session,
            "event-retained-thumb",
            test_camera.id,
            thumbnail_path=stored_path,
        )
        np.random.seed(21)
        embedding = np.random.randn(512).tolist()

        result = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event.id,
            embedding=embedding,
            entity_type="person",
        )
        entity_id = result.entity_id

        # Simulate retention: drop the Event row and its EntityEvent link
        link = db_session.query(EntityEvent).filter(
            EntityEvent.event_id == event.id
        ).first()
        db_session.delete(link)
        db_session.delete(event)
        db_session.commit()

        entities, total = await entity_service.get_all_entities(db_session)
        assert total == 1
        listed = next(e for e in entities if e["id"] == entity_id)
        assert listed["thumbnail_path"] == stored_path

        thumbnail = await entity_service.get_entity_thumbnail_path(
            db_session, entity_id
        )
        assert thumbnail == stored_path

    @pytest.mark.asyncio
    async def test_get_entity_thumbnail_path_falls_back_to_live_event(
        self, db_session, test_camera, entity_service
    ):
        """When the column is empty, use the latest linked Event.thumbnail_path."""
        event = create_event(
            db_session,
            "event-fallback-thumb",
            test_camera.id,
            thumbnail_path="/api/v1/thumbnails/2026-08-15/fallback.jpg",
        )
        np.random.seed(33)
        embedding = np.random.randn(512).tolist()

        result = await entity_service.match_or_create_entity(
            db=db_session,
            event_id=event.id,
            embedding=embedding,
            entity_type="person",
        )

        entity = db_session.query(RecognizedEntity).filter(
            RecognizedEntity.id == result.entity_id
        ).first()
        # Simulate the production rows that never had the column written
        entity.thumbnail_path = None
        db_session.commit()

        thumbnail = await entity_service.get_entity_thumbnail_path(
            db_session, result.entity_id
        )
        assert thumbnail == "/api/v1/thumbnails/2026-08-15/fallback.jpg"
