"""
Unit tests for VehicleMatchingService (Story P4-8.3)

Tests vehicle matching functionality including:
- Matching vehicle embeddings to known vehicles
- Creating new vehicle entities
- Updating vehicle appearance
- Extracting vehicle characteristics from descriptions
"""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np


class TestVehicleMatchingService:
    """Tests for VehicleMatchingService class."""

    @pytest.fixture
    def vehicle_service(self):
        """Create a VehicleMatchingService instance."""
        from app.services.vehicle_matching_service import VehicleMatchingService

        service = VehicleMatchingService()
        return service

    def test_service_initialization(self, vehicle_service):
        """Test that service initializes correctly."""
        assert vehicle_service is not None
        assert vehicle_service.DEFAULT_THRESHOLD == 0.65
        assert vehicle_service.HIGH_CONFIDENCE_THRESHOLD == 0.85
        assert vehicle_service._cache_loaded is False

    def test_extract_vehicle_characteristics_basic(self, vehicle_service):
        """Test basic characteristics extraction."""
        description = "A red SUV is parked in the driveway."

        result = vehicle_service._extract_vehicle_characteristics(description)

        assert "colors" in result
        assert "red" in result["colors"]
        assert result["primary_color"] == "red"
        assert result["described_type"] == "suv"

    def test_extract_vehicle_characteristics_multiple_colors(self, vehicle_service):
        """Test extraction with multiple colors."""
        description = "A black and silver sedan is driving down the street."

        result = vehicle_service._extract_vehicle_characteristics(description)

        assert "black" in result["colors"]
        assert "silver" in result["colors"]
        assert result["primary_color"] == "black"

    def test_extract_vehicle_characteristics_truck(self, vehicle_service):
        """Test extraction for truck type."""
        description = "A white pickup truck is in the parking lot."

        result = vehicle_service._extract_vehicle_characteristics(description)

        assert result["described_type"] == "truck"
        assert "white" in result["colors"]

    def test_extract_vehicle_characteristics_with_make(self, vehicle_service):
        """Test extraction with car make."""
        description = "A blue Toyota sedan is at the stop sign."

        result = vehicle_service._extract_vehicle_characteristics(description)

        assert result["make"] == "Toyota"
        assert result["described_type"] == "sedan"
        # Should have vehicle signature with color + make
        assert "vehicle_signature" in result
        assert result["vehicle_signature"] == "blue-toyota"

    def test_extract_vehicle_characteristics_motorcycle(self, vehicle_service):
        """Test extraction for motorcycle."""
        description = "A black motorcycle is parked by the curb."

        result = vehicle_service._extract_vehicle_characteristics(description)

        assert result["described_type"] == "motorcycle"

    def test_extract_vehicle_characteristics_empty_description(self, vehicle_service):
        """Test extraction with empty description."""
        result = vehicle_service._extract_vehicle_characteristics(None)
        assert result == {}

        result = vehicle_service._extract_vehicle_characteristics("")
        assert result == {}

    def test_extract_vehicle_characteristics_with_detected_type(self, vehicle_service):
        """Test extraction with pre-detected vehicle type."""
        description = "A vehicle is in the driveway."

        result = vehicle_service._extract_vehicle_characteristics(
            description, detected_type="car"
        )

        assert result["detected_type"] == "car"

    def test_extract_vehicle_characteristics_no_match(self, vehicle_service):
        """Test extraction when no vehicle info in description."""
        description = "A person is walking down the sidewalk."

        result = vehicle_service._extract_vehicle_characteristics(description)

        assert "colors" not in result
        assert "described_type" not in result

    def test_invalidate_cache(self, vehicle_service):
        """Test cache invalidation."""
        vehicle_service._vehicle_cache = {"v1": [0.1] * 512}
        vehicle_service._cache_loaded = True

        vehicle_service._invalidate_cache()

        assert vehicle_service._vehicle_cache == {}
        assert vehicle_service._cache_loaded is False

    @pytest.mark.asyncio
    async def test_match_single_vehicle_not_found(self, vehicle_service):
        """Test matching when vehicle embedding not found."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="VehicleEmbedding .* not found"):
            await vehicle_service.match_single_vehicle(
                db=mock_db,
                vehicle_embedding_id="nonexistent"
            )

    @pytest.mark.asyncio
    async def test_match_single_vehicle_first_vehicle_auto_create(self, vehicle_service):
        """Test matching when this is the first vehicle and auto_create is True."""
        # Setup mock embedding
        mock_embedding = MagicMock()
        mock_embedding.id = "emb-1"
        mock_embedding.event_id = "event-1"
        mock_embedding.embedding = json.dumps([0.1] * 512)
        mock_embedding.bounding_box = json.dumps({"x": 10, "y": 20, "width": 100, "height": 80})
        mock_embedding.vehicle_type = "car"
        mock_embedding.event = MagicMock()
        mock_embedding.event.timestamp = datetime.now(timezone.utc)

        mock_db = MagicMock()
        # First query returns embedding
        mock_db.query.return_value.filter.return_value.first.return_value = mock_embedding

        # Force empty cache (first vehicle)
        vehicle_service._vehicle_cache = {}
        vehicle_service._cache_loaded = True

        result = await vehicle_service.match_single_vehicle(
            db=mock_db,
            vehicle_embedding_id="emb-1",
            auto_create=True
        )

        assert result.is_new_vehicle is True
        assert result.vehicle_id is not None
        assert result.similarity_score == 1.0

    @pytest.mark.asyncio
    async def test_match_single_vehicle_no_auto_create(self, vehicle_service):
        """Test matching when no match and auto_create is False."""
        mock_embedding = MagicMock()
        mock_embedding.id = "emb-1"
        mock_embedding.event_id = "event-1"
        mock_embedding.embedding = json.dumps([0.1] * 512)
        mock_embedding.bounding_box = json.dumps({"x": 10, "y": 20, "width": 100, "height": 80})
        mock_embedding.vehicle_type = "car"
        mock_embedding.event = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_embedding

        # Empty cache (no existing vehicles)
        vehicle_service._vehicle_cache = {}
        vehicle_service._cache_loaded = True

        result = await vehicle_service.match_single_vehicle(
            db=mock_db,
            vehicle_embedding_id="emb-1",
            auto_create=False
        )

        assert result.is_new_vehicle is False
        assert result.vehicle_id is None
        assert result.similarity_score == 0.0

    @pytest.mark.asyncio
    async def test_get_vehicles(self, vehicle_service):
        """Test getting all vehicles."""
        from app.models.recognized_entity import RecognizedEntity

        mock_vehicle = MagicMock()
        mock_vehicle.id = "v-1"
        mock_vehicle.name = "My Car"
        mock_vehicle.first_seen_at = datetime.now(timezone.utc)
        mock_vehicle.last_seen_at = datetime.now(timezone.utc)
        mock_vehicle.occurrence_count = 5
        mock_vehicle.metadata = '{"detected_type": "car", "primary_color": "blue"}'

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_vehicle]
        mock_db.query.return_value = mock_query

        # Mock embedding counts
        mock_count = MagicMock()
        mock_count.entity_id = "v-1"
        mock_count.count = 3
        mock_query.filter.return_value.group_by.return_value.all.return_value = [mock_count]

        vehicles, total = await vehicle_service.get_vehicles(mock_db)

        assert total == 1
        assert len(vehicles) == 1
        assert vehicles[0]["id"] == "v-1"
        assert vehicles[0]["name"] == "My Car"

    @pytest.mark.asyncio
    async def test_get_vehicle_detail(self, vehicle_service):
        """Test getting single vehicle details."""
        mock_vehicle = MagicMock()
        mock_vehicle.id = "v-1"
        mock_vehicle.name = "Family Van"
        mock_vehicle.first_seen_at = datetime.now(timezone.utc)
        mock_vehicle.last_seen_at = datetime.now(timezone.utc)
        mock_vehicle.occurrence_count = 10
        mock_vehicle.created_at = datetime.now(timezone.utc)
        mock_vehicle.updated_at = datetime.now(timezone.utc)
        mock_vehicle.metadata = '{"detected_type": "van"}'

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_vehicle

        result = await vehicle_service.get_vehicle(
            mock_db, "v-1", include_embeddings=False
        )

        assert result is not None
        assert result["id"] == "v-1"
        assert result["name"] == "Family Van"

    @pytest.mark.asyncio
    async def test_get_vehicle_not_found(self, vehicle_service):
        """Test getting non-existent vehicle."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await vehicle_service.get_vehicle(mock_db, "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_vehicle_name(self, vehicle_service):
        """Test updating vehicle name."""
        mock_vehicle = MagicMock()
        mock_vehicle.id = "v-1"
        mock_vehicle.first_seen_at = datetime.now(timezone.utc)
        mock_vehicle.last_seen_at = datetime.now(timezone.utc)
        mock_vehicle.occurrence_count = 5
        mock_vehicle.metadata = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_vehicle

        result = await vehicle_service.update_vehicle_name(
            mock_db, "v-1", name="Work Truck"
        )

        assert result is not None
        assert mock_vehicle.name == "Work Truck"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_vehicle_name_not_found(self, vehicle_service):
        """Test updating name of non-existent vehicle."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = await vehicle_service.update_vehicle_name(
            mock_db, "nonexistent", name="Test"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_vehicle_metadata(self, vehicle_service):
        """Test updating vehicle metadata."""
        mock_vehicle = MagicMock()
        mock_vehicle.id = "v-1"
        mock_vehicle.name = "My Car"
        mock_vehicle.first_seen_at = datetime.now(timezone.utc)
        mock_vehicle.last_seen_at = datetime.now(timezone.utc)
        mock_vehicle.occurrence_count = 5
        mock_vehicle.metadata = '{"detected_type": "car"}'

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_vehicle

        result = await vehicle_service.update_vehicle_metadata(
            mock_db, "v-1", metadata_updates={"license_plate": "ABC123"}
        )

        assert result is not None
        # Verify metadata was updated
        updated_meta = json.loads(mock_vehicle.metadata)
        assert "license_plate" in updated_meta


class TestVehicleMatchingServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_vehicle_matching_service_returns_same_instance(self):
        """Test that get_vehicle_matching_service returns singleton."""
        from app.services.vehicle_matching_service import (
            get_vehicle_matching_service,
            reset_vehicle_matching_service,
        )

        reset_vehicle_matching_service()

        service1 = get_vehicle_matching_service()
        service2 = get_vehicle_matching_service()

        assert service1 is service2

    def test_reset_vehicle_matching_service(self):
        """Test that reset creates new instance."""
        from app.services.vehicle_matching_service import (
            get_vehicle_matching_service,
            reset_vehicle_matching_service,
        )

        service1 = get_vehicle_matching_service()
        reset_vehicle_matching_service()
        service2 = get_vehicle_matching_service()

        assert service1 is not service2


class TestVehicleCharacteristicsExtraction:
    """Additional tests for characteristics extraction edge cases."""

    @pytest.fixture
    def vehicle_service(self):
        from app.services.vehicle_matching_service import VehicleMatchingService
        return VehicleMatchingService()

    def test_extract_bus_type(self, vehicle_service):
        """Test bus type extraction."""
        description = "A yellow school bus is stopping at the corner."
        result = vehicle_service._extract_vehicle_characteristics(description)
        assert result["described_type"] == "bus"
        assert "yellow" in result["colors"]

    def test_extract_convertible(self, vehicle_service):
        """Test convertible extraction."""
        # Use description without "sports car" since sedan is checked before convertible
        description = "A red convertible is parked outside."
        result = vehicle_service._extract_vehicle_characteristics(description)
        assert result["described_type"] == "convertible"

    def test_extract_delivery_van(self, vehicle_service):
        """Test delivery van extraction."""
        description = "A white delivery van is at the front door."
        result = vehicle_service._extract_vehicle_characteristics(description)
        assert result["described_type"] == "van"

    def test_extract_multiple_makes(self, vehicle_service):
        """Test that first make is extracted."""
        description = "A Honda or Toyota sedan is in the driveway."
        result = vehicle_service._extract_vehicle_characteristics(description)
        assert result["make"] == "Honda"

    def test_extract_case_insensitive(self, vehicle_service):
        """Test case insensitive extraction."""
        description = "A BLUE SUV is parked."
        result = vehicle_service._extract_vehicle_characteristics(description)
        assert "blue" in result["colors"]
        assert result["described_type"] == "suv"


class TestVehicleSignatureExtraction:
    """Test vehicle signature extraction (Story P9-1.8)."""

    @pytest.fixture
    def vehicle_service(self):
        """Provide a fresh VehicleMatchingService instance."""
        from app.services.vehicle_matching_service import VehicleMatchingService
        return VehicleMatchingService()

    def test_extract_full_signature_color_make_model(self, vehicle_service):
        """Test extraction with color, make, and model."""
        description = "A white Toyota Camry pulled into the driveway."
        result = vehicle_service._extract_vehicle_characteristics(description)

        assert result["primary_color"] == "white"
        assert result["make"] == "Toyota"
        assert result["model"] == "Camry"
        assert result["vehicle_signature"] == "white-toyota-camry"

    def test_extract_signature_color_make_only(self, vehicle_service):
        """Test extraction with just color and make."""
        description = "A red Honda is parked on the street."
        result = vehicle_service._extract_vehicle_characteristics(description)

        assert result["primary_color"] == "red"
        assert result["make"] == "Honda"
        assert "vehicle_signature" in result
        assert result["vehicle_signature"] == "red-honda"

    def test_extract_signature_truck_model(self, vehicle_service):
        """Test extraction for Ford F-150."""
        description = "A black Ford F-150 arrived in the parking lot."
        result = vehicle_service._extract_vehicle_characteristics(description)

        assert result["primary_color"] == "black"
        assert result["make"] == "Ford"
        assert "model" in result
        assert result["vehicle_signature"] == "black-ford-f150"

    def test_extract_signature_tesla(self, vehicle_service):
        """Test extraction for Tesla Model 3."""
        description = "A white Tesla Model 3 is charging."
        result = vehicle_service._extract_vehicle_characteristics(description)

        assert result["primary_color"] == "white"
        assert result["make"] == "Tesla"
        assert result["vehicle_signature"] == "white-tesla-model3"

    def test_extract_signature_gray_grey_normalized(self, vehicle_service):
        """Test that grey is normalized to gray in signature."""
        description = "A grey Honda Civic is at the stop sign."
        result = vehicle_service._extract_vehicle_characteristics(description)

        # Grey should be normalized to gray in the signature
        assert result["vehicle_signature"] == "gray-honda-civic"

    def test_no_signature_without_color(self, vehicle_service):
        """Test no signature when only make is present (need 2+ parts)."""
        description = "A Toyota is in the driveway."
        result = vehicle_service._extract_vehicle_characteristics(description)

        assert result["make"] == "Toyota"
        # Should NOT have signature with only one part
        assert "vehicle_signature" not in result

    def test_different_vehicles_different_signatures(self, vehicle_service):
        """Test that different vehicles produce different signatures."""
        desc1 = "A white Toyota Camry arrived."
        desc2 = "A black Ford F-150 arrived."

        result1 = vehicle_service._extract_vehicle_characteristics(desc1)
        result2 = vehicle_service._extract_vehicle_characteristics(desc2)

        assert result1["vehicle_signature"] != result2["vehicle_signature"]
        assert result1["vehicle_signature"] == "white-toyota-camry"
        assert result2["vehicle_signature"] == "black-ford-f150"

    def test_same_vehicle_same_signature(self, vehicle_service):
        """Test that same vehicle produces consistent signature."""
        desc1 = "A white Toyota Camry pulled into the driveway."
        desc2 = "The white Toyota Camry is still parked there."

        result1 = vehicle_service._extract_vehicle_characteristics(desc1)
        result2 = vehicle_service._extract_vehicle_characteristics(desc2)

        assert result1["vehicle_signature"] == result2["vehicle_signature"]
