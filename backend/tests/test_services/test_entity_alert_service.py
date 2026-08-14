"""
Tests for EntityAlertService (Story P4-8.4: Named Entity Alerts)

Tests cover:
- Recognition status classification
- Description enrichment with entity names
- VIP entity detection
- Blocklist alert suppression
- Entity-based rule matching
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.entity_alert_service import (
    EntityAlertService,
    EntityAlertResult,
    get_entity_alert_service,
    reset_entity_alert_service,
)
from app.models.recognized_entity import RecognizedEntity
from app.models.event import Event


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def entity_alert_service():
    """Create a fresh EntityAlertService instance."""
    reset_entity_alert_service()
    return EntityAlertService()


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.fixture
def sample_entity_john():
    """Create a sample named person entity."""
    entity = MagicMock(spec=RecognizedEntity)
    entity.id = "entity-john-uuid"
    entity.entity_type = "person"
    entity.name = "John Smith"
    entity.is_vip = False
    entity.is_blocked = False
    entity.first_seen_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    entity.last_seen_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
    entity.occurrence_count = 10
    entity.entity_metadata = None
    entity.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    entity.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
    return entity


@pytest.fixture
def sample_entity_jane():
    """Create another sample named person entity."""
    entity = MagicMock(spec=RecognizedEntity)
    entity.id = "entity-jane-uuid"
    entity.entity_type = "person"
    entity.name = "Jane Doe"
    entity.is_vip = True
    entity.is_blocked = False
    entity.first_seen_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
    entity.last_seen_at = datetime(2024, 7, 1, tzinfo=timezone.utc)
    entity.occurrence_count = 5
    entity.entity_metadata = None
    entity.created_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
    entity.updated_at = datetime(2024, 7, 1, tzinfo=timezone.utc)
    return entity


@pytest.fixture
def sample_entity_unnamed():
    """Create a sample unnamed (stranger) entity."""
    entity = MagicMock(spec=RecognizedEntity)
    entity.id = "entity-stranger-uuid"
    entity.entity_type = "person"
    entity.name = None
    entity.is_vip = False
    entity.is_blocked = False
    entity.first_seen_at = datetime(2024, 3, 1, tzinfo=timezone.utc)
    entity.last_seen_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    entity.occurrence_count = 3
    entity.entity_metadata = None
    entity.created_at = datetime(2024, 3, 1, tzinfo=timezone.utc)
    entity.updated_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
    return entity


@pytest.fixture
def sample_entity_blocked():
    """Create a sample blocked entity."""
    entity = MagicMock(spec=RecognizedEntity)
    entity.id = "entity-blocked-uuid"
    entity.entity_type = "person"
    entity.name = "Blocked Person"
    entity.is_vip = False
    entity.is_blocked = True
    entity.first_seen_at = datetime(2024, 4, 1, tzinfo=timezone.utc)
    entity.last_seen_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
    entity.occurrence_count = 2
    entity.entity_metadata = None
    entity.created_at = datetime(2024, 4, 1, tzinfo=timezone.utc)
    entity.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
    return entity


@pytest.fixture
def sample_vehicle_entity():
    """Create a sample vehicle entity."""
    entity = MagicMock(spec=RecognizedEntity)
    entity.id = "entity-vehicle-uuid"
    entity.entity_type = "vehicle"
    entity.name = "Family Car"
    entity.is_vip = True
    entity.is_blocked = False
    entity.first_seen_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    entity.last_seen_at = datetime(2024, 8, 1, tzinfo=timezone.utc)
    entity.occurrence_count = 50
    entity.entity_metadata = json.dumps({"color": "blue", "type": "sedan"})
    entity.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    entity.updated_at = datetime(2024, 8, 1, tzinfo=timezone.utc)
    return entity


# =============================================================================
# Recognition Status Classification Tests
# =============================================================================


class TestRecognitionStatusClassification:
    """Tests for classify_recognition_status method."""

    def test_known_status_single_named_entity(self, entity_alert_service, sample_entity_john):
        """Test 'known' status with a single named entity."""
        status = entity_alert_service.classify_recognition_status([sample_entity_john])
        assert status == "known"

    def test_known_status_multiple_named_entities(
        self, entity_alert_service, sample_entity_john, sample_entity_jane
    ):
        """Test 'known' status with multiple named entities."""
        status = entity_alert_service.classify_recognition_status(
            [sample_entity_john, sample_entity_jane]
        )
        assert status == "known"

    def test_known_status_mixed_named_unnamed(
        self, entity_alert_service, sample_entity_john, sample_entity_unnamed
    ):
        """Test 'known' status when at least one entity is named."""
        status = entity_alert_service.classify_recognition_status(
            [sample_entity_john, sample_entity_unnamed]
        )
        assert status == "known"

    def test_stranger_status_unnamed_entity(self, entity_alert_service, sample_entity_unnamed):
        """Test 'stranger' status with unnamed entity (seen before but not identified)."""
        status = entity_alert_service.classify_recognition_status([sample_entity_unnamed])
        assert status == "stranger"

    def test_stranger_status_empty_name(self, entity_alert_service):
        """Test 'stranger' status with empty string name."""
        entity = MagicMock(spec=RecognizedEntity)
        entity.name = ""
        status = entity_alert_service.classify_recognition_status([entity])
        assert status == "stranger"

    def test_stranger_status_whitespace_name(self, entity_alert_service):
        """Test 'stranger' status with whitespace-only name."""
        entity = MagicMock(spec=RecognizedEntity)
        entity.name = "   "
        status = entity_alert_service.classify_recognition_status([entity])
        assert status == "stranger"

    def test_unknown_status_no_entities(self, entity_alert_service):
        """Test 'unknown' status with no matched entities (first-time visitor)."""
        status = entity_alert_service.classify_recognition_status([])
        assert status == "unknown"


# =============================================================================
# Description Enrichment Tests
# =============================================================================


class TestDescriptionEnrichment:
    """Tests for enrich_description method."""

    def test_enrich_person_description(self, entity_alert_service, sample_entity_john):
        """Test replacing 'A person' with entity name."""
        original = "A person is walking toward the front door."
        enriched = entity_alert_service.enrich_description(original, [sample_entity_john])
        assert enriched == "John Smith is walking toward the front door."

    def test_enrich_someone_description(self, entity_alert_service, sample_entity_john):
        """Test replacing 'Someone' with entity name."""
        original = "Someone is standing on the porch."
        enriched = entity_alert_service.enrich_description(original, [sample_entity_john])
        assert enriched == "John Smith is standing on the porch."

    def test_enrich_with_two_entities(
        self, entity_alert_service, sample_entity_john, sample_entity_jane
    ):
        """Test enrichment with two named entities."""
        original = "A person is walking in the driveway."
        enriched = entity_alert_service.enrich_description(
            original, [sample_entity_john, sample_entity_jane]
        )
        assert enriched == "John Smith and Jane Doe is walking in the driveway."

    def test_enrich_with_three_entities(self, entity_alert_service):
        """Test enrichment with three named entities."""
        entity1 = MagicMock(spec=RecognizedEntity)
        entity1.name = "Alice"
        entity2 = MagicMock(spec=RecognizedEntity)
        entity2.name = "Bob"
        entity3 = MagicMock(spec=RecognizedEntity)
        entity3.name = "Charlie"

        original = "A person is at the door."
        enriched = entity_alert_service.enrich_description(original, [entity1, entity2, entity3])
        assert enriched == "Alice, Bob, and Charlie is at the door."

    def test_enrich_vehicle_description(self, entity_alert_service, sample_vehicle_entity):
        """Test enriching vehicle-related description."""
        original = "A vehicle is entering the driveway."
        enriched = entity_alert_service.enrich_description(original, [sample_vehicle_entity])
        assert enriched == "Family Car's vehicle is entering the driveway."

    def test_enrich_composes_person_and_vehicle(
        self, entity_alert_service, sample_entity_john
    ):
        """Named person + vehicle should compose, not only swap the sentence start."""
        vehicle = MagicMock(spec=RecognizedEntity)
        vehicle.name = "BMW X3"
        vehicle.entity_type = "vehicle"
        vehicle.vehicle_color = "red"
        vehicle.vehicle_make = "BMW"
        vehicle.vehicle_model = "X3"

        original = "A person arrives in a vehicle at the driveway."
        enriched = entity_alert_service.enrich_description(
            original, [sample_entity_john, vehicle]
        )
        assert "John Smith" in enriched
        assert "BMW" in enriched or "X3" in enriched
        assert "a person" not in enriched.lower()
        assert "a vehicle" not in enriched.lower()

    def test_enrich_no_match_no_change(self, entity_alert_service, sample_entity_john):
        """Test that descriptions without matching patterns are unchanged."""
        original = "Motion detected in backyard."
        enriched = entity_alert_service.enrich_description(original, [sample_entity_john])
        assert enriched == original

    def test_enrich_empty_description(self, entity_alert_service, sample_entity_john):
        """Test that empty description returns unchanged."""
        enriched = entity_alert_service.enrich_description("", [sample_entity_john])
        assert enriched == ""

    def test_enrich_no_entities(self, entity_alert_service):
        """Test that description without entities returns unchanged."""
        original = "A person is at the door."
        enriched = entity_alert_service.enrich_description(original, [])
        assert enriched == original

    def test_enrich_unnamed_entities(self, entity_alert_service, sample_entity_unnamed):
        """Test that unnamed entities don't enrich description."""
        original = "A person is at the door."
        enriched = entity_alert_service.enrich_description(original, [sample_entity_unnamed])
        assert enriched == original

    def test_enrich_case_insensitive(self, entity_alert_service, sample_entity_john):
        """Test case-insensitive pattern matching."""
        original = "person detected at entrance."
        enriched = entity_alert_service.enrich_description(original, [sample_entity_john])
        assert enriched == "John Smith detected at entrance."


# =============================================================================
# VIP Detection Tests
# =============================================================================


class TestVIPDetection:
    """Tests for VIP entity detection."""

    @pytest.mark.asyncio
    async def test_has_vip_true(self, entity_alert_service, mock_db, sample_entity_jane):
        """Test VIP detection when VIP entity is matched."""
        mock_db.query.return_value.filter.return_value.first.return_value = sample_entity_jane
        mock_db.query.return_value.all.return_value = [sample_entity_jane]

        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {sample_entity_jane.id: sample_entity_jane}

        vip_entities = await entity_alert_service.get_vip_entities(
            mock_db, [sample_entity_jane.id]
        )
        assert len(vip_entities) == 1
        assert vip_entities[0].is_vip is True

    @pytest.mark.asyncio
    async def test_has_vip_false(self, entity_alert_service, mock_db, sample_entity_john):
        """Test VIP detection when no VIP entities are matched."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {sample_entity_john.id: sample_entity_john}

        vip_entities = await entity_alert_service.get_vip_entities(
            mock_db, [sample_entity_john.id]
        )
        assert len(vip_entities) == 0

    @pytest.mark.asyncio
    async def test_empty_entity_list_returns_no_vip(self, entity_alert_service, mock_db):
        """Test that empty entity list returns no VIP entities."""
        vip_entities = await entity_alert_service.get_vip_entities(mock_db, [])
        assert len(vip_entities) == 0


# =============================================================================
# Blocklist Suppression Tests
# =============================================================================


class TestBlocklistSuppression:
    """Tests for blocklist alert suppression."""

    @pytest.mark.asyncio
    async def test_should_suppress_blocked_entity(
        self, entity_alert_service, mock_db, sample_entity_blocked
    ):
        """Test that blocked entity suppresses alerts."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {sample_entity_blocked.id: sample_entity_blocked}

        should_suppress = await entity_alert_service.should_suppress_alert(
            mock_db, [sample_entity_blocked.id]
        )
        assert should_suppress is True

    @pytest.mark.asyncio
    async def test_should_not_suppress_normal_entity(
        self, entity_alert_service, mock_db, sample_entity_john
    ):
        """Test that non-blocked entity doesn't suppress alerts."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {sample_entity_john.id: sample_entity_john}

        should_suppress = await entity_alert_service.should_suppress_alert(
            mock_db, [sample_entity_john.id]
        )
        assert should_suppress is False

    @pytest.mark.asyncio
    async def test_should_suppress_mixed_entities(
        self, entity_alert_service, mock_db, sample_entity_john, sample_entity_blocked
    ):
        """Test that one blocked entity in list suppresses alerts."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {
            sample_entity_john.id: sample_entity_john,
            sample_entity_blocked.id: sample_entity_blocked,
        }

        should_suppress = await entity_alert_service.should_suppress_alert(
            mock_db, [sample_entity_john.id, sample_entity_blocked.id]
        )
        assert should_suppress is True

    @pytest.mark.asyncio
    async def test_empty_list_no_suppression(self, entity_alert_service, mock_db):
        """Test that empty entity list doesn't suppress."""
        should_suppress = await entity_alert_service.should_suppress_alert(mock_db, [])
        assert should_suppress is False


# =============================================================================
# Process Event Entities Tests
# =============================================================================


class TestProcessEventEntities:
    """Tests for the main process_event_entities method."""

    @pytest.mark.asyncio
    async def test_process_known_person(
        self, entity_alert_service, mock_db, sample_entity_john
    ):
        """Test processing event with known person."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {sample_entity_john.id: sample_entity_john}

        result = await entity_alert_service.process_event_entities(
            db=mock_db,
            event_id="test-event-id",
            matched_entity_ids=[sample_entity_john.id],
            original_description="A person is at the door.",
            has_person_or_vehicle=True,
        )

        assert isinstance(result, EntityAlertResult)
        assert result.recognition_status == "known"
        assert result.enriched_description == "John Smith is at the door."
        assert result.matched_entity_ids == [sample_entity_john.id]
        assert result.has_vip is False
        assert result.should_suppress is False
        assert result.entity_names == ["John Smith"]

    @pytest.mark.asyncio
    async def test_process_vip_person(
        self, entity_alert_service, mock_db, sample_entity_jane
    ):
        """Test processing event with VIP person."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {sample_entity_jane.id: sample_entity_jane}

        result = await entity_alert_service.process_event_entities(
            db=mock_db,
            event_id="test-event-id",
            matched_entity_ids=[sample_entity_jane.id],
            original_description="A person is at the door.",
            has_person_or_vehicle=True,
        )

        assert result.recognition_status == "known"
        assert result.has_vip is True
        assert result.vip_entity_ids == [sample_entity_jane.id]
        assert result.should_suppress is False

    @pytest.mark.asyncio
    async def test_process_blocked_person(
        self, entity_alert_service, mock_db, sample_entity_blocked
    ):
        """Test processing event with blocked person."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {sample_entity_blocked.id: sample_entity_blocked}

        result = await entity_alert_service.process_event_entities(
            db=mock_db,
            event_id="test-event-id",
            matched_entity_ids=[sample_entity_blocked.id],
            original_description="A person is at the door.",
            has_person_or_vehicle=True,
        )

        assert result.recognition_status == "known"
        assert result.should_suppress is True

    @pytest.mark.asyncio
    async def test_process_stranger(
        self, entity_alert_service, mock_db, sample_entity_unnamed
    ):
        """Test processing event with stranger (unnamed entity)."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {sample_entity_unnamed.id: sample_entity_unnamed}

        result = await entity_alert_service.process_event_entities(
            db=mock_db,
            event_id="test-event-id",
            matched_entity_ids=[sample_entity_unnamed.id],
            original_description="A person is at the door.",
            has_person_or_vehicle=True,
        )

        assert result.recognition_status == "stranger"
        # Description should not be enriched for unnamed entities
        assert result.enriched_description == "A person is at the door."
        assert result.entity_names == []

    @pytest.mark.asyncio
    async def test_process_unknown_person(self, entity_alert_service, mock_db):
        """Test processing event with unknown person (no match)."""
        entity_alert_service._cache_loaded = True
        entity_alert_service._entity_cache = {}

        result = await entity_alert_service.process_event_entities(
            db=mock_db,
            event_id="test-event-id",
            matched_entity_ids=[],
            original_description="A person is at the door.",
            has_person_or_vehicle=True,
        )

        assert result.recognition_status == "unknown"
        assert result.matched_entity_ids == []
        assert result.has_vip is False
        assert result.should_suppress is False

    @pytest.mark.asyncio
    async def test_process_no_person_or_vehicle(self, entity_alert_service, mock_db):
        """Test processing event without person or vehicle detection."""
        result = await entity_alert_service.process_event_entities(
            db=mock_db,
            event_id="test-event-id",
            matched_entity_ids=[],
            original_description="Motion detected.",
            has_person_or_vehicle=False,
        )

        assert result.recognition_status is None
        assert result.enriched_description is None


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_entity_alert_service_returns_same_instance(self):
        """Test that get_entity_alert_service returns singleton."""
        reset_entity_alert_service()
        service1 = get_entity_alert_service()
        service2 = get_entity_alert_service()
        assert service1 is service2

    def test_reset_clears_singleton(self):
        """Test that reset_entity_alert_service clears the singleton."""
        service1 = get_entity_alert_service()
        reset_entity_alert_service()
        service2 = get_entity_alert_service()
        assert service1 is not service2


# =============================================================================
# Cache Tests
# =============================================================================


class TestCache:
    """Tests for entity cache behavior."""

    def test_invalidate_cache(self, entity_alert_service, sample_entity_john):
        """Test cache invalidation."""
        entity_alert_service._entity_cache = {sample_entity_john.id: sample_entity_john}
        entity_alert_service._cache_loaded = True

        entity_alert_service._invalidate_cache()

        assert entity_alert_service._entity_cache == {}
        assert entity_alert_service._cache_loaded is False
