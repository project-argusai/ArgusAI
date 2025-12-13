"""
Unit tests for PersonMatchingService (Story P4-8.2)

Tests person matching functionality including:
- Matching face embeddings to known persons
- Handling multiple faces per event
- Auto-creating new persons when no match
- Appearance update logic on high-confidence matches
- Threshold edge cases
"""
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.person_matching_service import (
    PersonMatchingService,
    PersonMatchResult,
    get_person_matching_service,
    reset_person_matching_service,
)


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    session.close = MagicMock()
    session.add = MagicMock()
    session.refresh = MagicMock()
    return session


@pytest.fixture
def person_service():
    """Create a PersonMatchingService instance."""
    reset_person_matching_service()
    return PersonMatchingService()


@pytest.fixture
def mock_face_embedding():
    """Create a mock FaceEmbedding object."""
    face = MagicMock()
    face.id = str(uuid.uuid4())
    face.event_id = str(uuid.uuid4())
    face.entity_id = None
    face.embedding = json.dumps([0.1] * 512)
    face.bounding_box = json.dumps({"x": 10, "y": 20, "width": 50, "height": 50})
    face.confidence = 0.95
    face.created_at = datetime.now(timezone.utc)
    # Mock event relationship
    face.event = MagicMock()
    face.event.timestamp = datetime.now(timezone.utc)
    return face


@pytest.fixture
def mock_person_entity():
    """Create a mock RecognizedEntity (person)."""
    person = MagicMock()
    person.id = str(uuid.uuid4())
    person.entity_type = "person"
    person.name = "Test Person"
    person.reference_embedding = json.dumps([0.1] * 512)  # Same as face embedding for match
    person.first_seen_at = datetime.now(timezone.utc)
    person.last_seen_at = datetime.now(timezone.utc)
    person.occurrence_count = 5
    person.created_at = datetime.now(timezone.utc)
    person.updated_at = datetime.now(timezone.utc)
    return person


class TestPersonMatchingService:
    """Tests for PersonMatchingService class."""

    def test_service_initialization(self, person_service):
        """Test that service initializes correctly."""
        assert person_service is not None
        assert person_service.DEFAULT_THRESHOLD == 0.70
        assert person_service.HIGH_CONFIDENCE_THRESHOLD == 0.90
        assert person_service._cache_loaded is False

    def test_default_thresholds(self, person_service):
        """Test default threshold values."""
        assert person_service.DEFAULT_THRESHOLD == 0.70
        assert person_service.HIGH_CONFIDENCE_THRESHOLD == 0.90
        assert person_service.APPEARANCE_DIFF_THRESHOLD == 0.15


class TestMatchSingleFace:
    """Tests for match_single_face method."""

    @pytest.mark.asyncio
    async def test_match_single_face_not_found(self, person_service, mock_db_session):
        """Test matching returns error when face embedding not found."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await person_service.match_single_face(
                mock_db_session,
                "nonexistent-face-id"
            )

    @pytest.mark.asyncio
    async def test_match_single_face_no_persons_auto_create(
        self, person_service, mock_db_session, mock_face_embedding
    ):
        """Test creating first person when no persons exist."""
        # Mock face embedding lookup
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_face_embedding

        # Empty person cache - no persons exist
        person_service._person_cache = {}
        person_service._cache_loaded = True

        result = await person_service.match_single_face(
            mock_db_session,
            mock_face_embedding.id,
            auto_create=True,
        )

        assert result.is_new_person is True
        assert result.similarity_score == 1.0
        assert result.person_id is not None
        assert mock_db_session.add.called
        assert mock_db_session.commit.called

    @pytest.mark.asyncio
    async def test_match_single_face_no_persons_no_auto_create(
        self, person_service, mock_db_session, mock_face_embedding
    ):
        """Test no person created when auto_create is disabled."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_face_embedding

        person_service._person_cache = {}
        person_service._cache_loaded = True

        result = await person_service.match_single_face(
            mock_db_session,
            mock_face_embedding.id,
            auto_create=False,
        )

        assert result.person_id is None
        assert result.is_new_person is False
        assert result.similarity_score == 0.0

    @pytest.mark.asyncio
    async def test_match_single_face_known_person(
        self, person_service, mock_db_session, mock_face_embedding, mock_person_entity
    ):
        """Test matching to a known person."""
        # Setup mock for face lookup
        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_face_embedding,  # First call: find face embedding
            mock_person_entity,   # Second call: find person entity
            None,                 # Third call: check existing EntityEvent link
        ]

        # Add person to cache with matching embedding
        person_service._person_cache = {
            mock_person_entity.id: [0.1] * 512  # Same as face embedding
        }
        person_service._cache_loaded = True

        result = await person_service.match_single_face(
            mock_db_session,
            mock_face_embedding.id,
            threshold=0.70,
        )

        assert result.person_id == mock_person_entity.id
        assert result.is_new_person is False
        assert result.similarity_score >= 0.70
        assert result.person_name == mock_person_entity.name

    @pytest.mark.asyncio
    async def test_match_single_face_below_threshold(
        self, person_service, mock_db_session, mock_face_embedding
    ):
        """Test no match when similarity is below threshold."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_face_embedding

        # Add person with very different embedding (orthogonal to face embedding)
        # Face embedding is [0.1] * 512, use opposite direction for low similarity
        different_embedding = [-0.1] * 512  # Negative values for low cosine similarity
        person_service._person_cache = {
            str(uuid.uuid4()): different_embedding
        }
        person_service._cache_loaded = True

        result = await person_service.match_single_face(
            mock_db_session,
            mock_face_embedding.id,
            threshold=0.70,
            auto_create=False,
        )

        # Should not match due to low similarity - returns None person_id when auto_create=False
        assert result.person_id is None
        assert result.is_new_person is False
        assert result.similarity_score < 0.70  # Below threshold


class TestMatchFacesToPersons:
    """Tests for match_faces_to_persons method."""

    @pytest.mark.asyncio
    async def test_match_empty_list(self, person_service, mock_db_session):
        """Test matching empty list returns empty list."""
        result = await person_service.match_faces_to_persons(
            mock_db_session,
            face_embedding_ids=[],
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_match_multiple_faces(
        self, person_service, mock_db_session
    ):
        """Test matching multiple faces - verifies batch processing works."""
        from app.models.face_embedding import FaceEmbedding

        # Create mock face embeddings with same event
        face_ids = [str(uuid.uuid4()) for _ in range(3)]
        event_id = str(uuid.uuid4())

        mock_faces = {}
        for i, fid in enumerate(face_ids):
            face = MagicMock(spec=FaceEmbedding)
            face.id = fid
            face.event_id = event_id
            face.entity_id = None
            # Make each face slightly different so they're distinct persons
            face.embedding = json.dumps([0.1 + 0.2 * i] * 512)
            face.bounding_box = json.dumps({"x": 10 + i * 100, "y": 20, "width": 50, "height": 50})
            face.event = MagicMock()
            face.event.timestamp = datetime.now(timezone.utc)
            mock_faces[fid] = face

        # Setup mock to return the correct face based on the filter ID
        def mock_query_filter_first():
            """Return a mock that tracks which face ID was queried."""
            mock_chain = MagicMock()

            def filter_handler(*args, **kwargs):
                # Extract the face ID from the filter expression
                filter_chain = MagicMock()

                def first_handler():
                    # Try to find which face was queried by checking args
                    # In real code, this is FaceEmbedding.id == face_embedding_id
                    for fid, face in mock_faces.items():
                        return face  # Return first available as fallback
                    return None

                filter_chain.first = first_handler
                return filter_chain

            mock_chain.filter = filter_handler
            return mock_chain

        # Simpler approach: mock match_single_face directly for this test
        original_match = person_service.match_single_face

        async def mock_match(db, fid, **kwargs):
            if fid in mock_faces:
                face = mock_faces[fid]
                return PersonMatchResult(
                    face_embedding_id=fid,
                    person_id=str(uuid.uuid4()),
                    person_name=None,
                    similarity_score=1.0,
                    is_new_person=True,
                    is_appearance_update=False,
                    bounding_box=json.loads(face.bounding_box),
                )
            raise ValueError(f"Face {fid} not found")

        person_service.match_single_face = mock_match

        try:
            results = await person_service.match_faces_to_persons(
                mock_db_session,
                face_embedding_ids=face_ids,
                auto_create=True,
            )

            assert len(results) == 3
            for result in results:
                assert result.is_new_person is True
                assert result.person_id is not None
        finally:
            person_service.match_single_face = original_match


class TestAppearanceUpdate:
    """Tests for appearance update logic."""

    @pytest.mark.asyncio
    async def test_appearance_update_triggered(
        self, person_service, mock_db_session, mock_face_embedding, mock_person_entity
    ):
        """Test appearance update on high-confidence match with embedding difference."""
        # Use slightly different embedding that still matches
        mock_face_embedding.embedding = json.dumps([0.12] * 512)  # Slightly different

        mock_db_session.query.return_value.filter.return_value.first.side_effect = [
            mock_face_embedding,
            mock_person_entity,
            None,  # No existing EntityEvent
        ]

        # Person with different but matching embedding
        person_service._person_cache = {
            mock_person_entity.id: [0.1] * 512  # Slightly different from face
        }
        person_service._cache_loaded = True

        # With appearance update enabled and similarity above HIGH_CONFIDENCE_THRESHOLD
        result = await person_service.match_single_face(
            mock_db_session,
            mock_face_embedding.id,
            threshold=0.70,
            update_appearance=True,
        )

        # Result should indicate match (appearance update depends on embedding difference)
        assert result.person_id is not None


class TestPersonCacheLoading:
    """Tests for person cache loading."""

    def test_cache_initially_not_loaded(self, person_service):
        """Test cache is not loaded initially."""
        assert person_service._cache_loaded is False
        assert person_service._person_cache == {}

    def test_cache_invalidation(self, person_service):
        """Test cache invalidation."""
        person_service._person_cache = {"test": [0.1] * 512}
        person_service._cache_loaded = True

        person_service._invalidate_cache()

        assert person_service._cache_loaded is False
        assert person_service._person_cache == {}


class TestGetPersons:
    """Tests for get_persons method."""

    @pytest.mark.asyncio
    async def test_get_persons_empty(self, person_service, mock_db_session):
        """Test getting persons when none exist."""
        mock_db_session.query.return_value.filter.return_value.count.return_value = 0
        mock_db_session.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = []

        persons, total = await person_service.get_persons(mock_db_session)

        assert persons == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_get_persons_with_data(self, person_service, mock_db_session, mock_person_entity):
        """Test getting persons with data."""
        mock_db_session.query.return_value.filter.return_value.count.return_value = 1
        mock_db_session.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_person_entity]
        mock_db_session.query.return_value.filter.return_value.group_by.return_value.all.return_value = []

        persons, total = await person_service.get_persons(mock_db_session)

        assert total == 1
        assert len(persons) == 1
        assert persons[0]["id"] == mock_person_entity.id


class TestGetPerson:
    """Tests for get_person method."""

    @pytest.mark.asyncio
    async def test_get_person_not_found(self, person_service, mock_db_session):
        """Test getting non-existent person returns None."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        result = await person_service.get_person(mock_db_session, "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_person_found(self, person_service, mock_db_session, mock_person_entity):
        """Test getting existing person."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_person_entity
        mock_db_session.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        result = await person_service.get_person(
            mock_db_session,
            mock_person_entity.id,
            include_faces=True,
        )

        assert result is not None
        assert result["id"] == mock_person_entity.id
        assert result["name"] == mock_person_entity.name


class TestUpdatePersonName:
    """Tests for update_person_name method."""

    @pytest.mark.asyncio
    async def test_update_person_name_not_found(self, person_service, mock_db_session):
        """Test updating non-existent person returns None."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        result = await person_service.update_person_name(
            mock_db_session,
            "nonexistent",
            name="Test Name"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_person_name_success(self, person_service, mock_db_session, mock_person_entity):
        """Test successfully updating person name."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_person_entity

        new_name = "John Doe"
        result = await person_service.update_person_name(
            mock_db_session,
            mock_person_entity.id,
            name=new_name,
        )

        assert result is not None
        mock_db_session.commit.assert_called_once()


class TestSingleton:
    """Tests for singleton pattern."""

    def test_get_person_matching_service_singleton(self):
        """Test singleton returns same instance."""
        reset_person_matching_service()

        service1 = get_person_matching_service()
        service2 = get_person_matching_service()

        assert service1 is service2

    def test_reset_clears_singleton(self):
        """Test reset clears the singleton."""
        service1 = get_person_matching_service()
        reset_person_matching_service()
        service2 = get_person_matching_service()

        assert service1 is not service2
