# Story P4-3.1: Event Embedding Generation

Status: done

## Story

As a **home security system user**,
I want **event thumbnails to be converted into vector embeddings using CLIP**,
so that **the system can find similar past events and recognize recurring visitors/vehicles**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| 1 | CLIP ViT-B/32 model loaded and initialized on startup | Unit test model initialization |
| 2 | Embedding generated for each new event thumbnail | Create event, verify embedding stored |
| 3 | Embeddings stored in `event_embeddings` table with event_id reference | Database query verification |
| 4 | Embedding dimension is 512 (CLIP ViT-B/32 output) | Assert embedding array length |
| 5 | Embedding generation completes in <200ms per image | Performance timing test |
| 6 | Model version tracked in database for future compatibility | Check model_version column populated |
| 7 | Graceful fallback if embedding generation fails (event still created) | Test with corrupted image |
| 8 | Batch processing endpoint for generating embeddings on existing events | API endpoint returns success/count |
| 9 | Batch processing respects rate limiting (max 100 events per request) | Test with >100 events |
| 10 | Embedding generation works for both base64 and file-path thumbnails | Test both thumbnail storage modes |
| 11 | SQLite fallback stores embeddings as JSON array (no pgvector required) | Verify with SQLite database |
| 12 | API endpoint to check embedding status for an event | GET endpoint returns embedding metadata |

## Tasks / Subtasks

- [x] **Task 1: Create EmbeddingService with CLIP model** (AC: 1, 5)
  - [x] Add `sentence-transformers` to requirements.txt
  - [x] Create `backend/app/services/embedding_service.py`
  - [x] Implement model lazy loading on first use
  - [x] Add `generate_embedding(image_bytes: bytes) -> list[float]` method
  - [x] Add timing instrumentation for performance monitoring
  - [x] Handle CUDA/MPS availability for GPU acceleration (optional)

- [x] **Task 2: Create EventEmbedding database model** (AC: 3, 6, 11)
  - [x] Create `backend/app/models/event_embedding.py`
  - [x] Add fields: id, event_id, embedding (Text/JSON), model_version, created_at
  - [x] Create relationship with Event model
  - [x] Add unique constraint on event_id
  - [x] Create Alembic migration for new table

- [x] **Task 3: Integrate embedding generation into event pipeline** (AC: 2, 7, 10)
  - [x] Add embedding step to `event_processor.py` after AI description
  - [x] Extract thumbnail bytes from base64 or file path
  - [x] Call `EmbeddingService.generate_embedding()`
  - [x] Store embedding in database
  - [x] Handle failures gracefully (log warning, don't block event creation)

- [x] **Task 4: Create batch processing endpoint** (AC: 8, 9)
  - [x] Add `POST /api/v1/context/embeddings/batch` endpoint
  - [x] Query events without embeddings
  - [x] Limit batch size to 100 events per request
  - [x] Process embeddings with progress tracking
  - [x] Return count of processed/failed embeddings

- [x] **Task 5: Create embedding status endpoint** (AC: 12)
  - [x] Add `GET /api/v1/context/embeddings/{event_id}` endpoint
  - [x] Return embedding metadata (exists, model_version, created_at)
  - [x] Return 404 if event not found

- [x] **Task 6: Write unit tests** (AC: 1, 4, 5, 6, 7)
  - [x] Test model initialization
  - [x] Test embedding dimension (512)
  - [x] Test embedding generation timing (<200ms)
  - [x] Test model version tracking
  - [x] Test graceful failure handling
  - [x] Mock CLIP model for fast CI tests

- [x] **Task 7: Write integration tests** (AC: 2, 3, 8, 9, 10, 11)
  - [x] Test event creation with embedding storage
  - [x] Test both thumbnail modes (base64, file path)
  - [x] Test batch processing endpoint
  - [x] Test SQLite JSON storage

## Dev Notes

### Architecture Alignment

This story implements the first component of the Temporal Context Engine (Epic P4-3). The embedding service will be used by subsequent stories for similarity search (P4-3.2) and recurring visitor detection (P4-3.3).

**Component Flow:**
```
Event Created → EventProcessor → EmbeddingService.generate_embedding()
                                          ↓
                                  CLIP Model (ViT-B/32)
                                          ↓
                                  EventEmbedding (DB)
```

### Key Implementation Details

**Technology Choice (ADR-P4-001):**
- Model: CLIP ViT-B/32 via sentence-transformers
- Embedding dimension: 512
- Target inference time: <200ms per image

**EmbeddingService Structure:**
```python
class EmbeddingService:
    """Generate image embeddings using CLIP model."""

    MODEL_NAME = "clip-ViT-B-32"
    MODEL_VERSION = "clip-ViT-B-32-v1"
    EMBEDDING_DIM = 512

    def __init__(self):
        self._model = None  # Lazy loading

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.MODEL_NAME)
        return self._model

    async def generate_embedding(self, image_bytes: bytes) -> list[float]:
        """Generate 512-dim embedding from image bytes."""
        # Convert bytes to PIL Image
        # Generate embedding
        # Return as list for JSON serialization
```

**Database Schema (SQLite compatible):**
```python
class EventEmbedding(Base):
    __tablename__ = "event_embeddings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String, ForeignKey('events.id', ondelete='CASCADE'), nullable=False, unique=True)
    embedding = Column(Text, nullable=False)  # JSON array of floats
    model_version = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    event = relationship("Event", back_populates="embedding")
```

**Event Pipeline Integration (event_processor.py):**
```python
# After Step 7 (AI Description) or Step 8 (MQTT Publishing)
# Step 9: Generate embedding for temporal context
try:
    embedding = await embedding_service.generate_embedding(thumbnail_bytes)
    await embedding_service.store_embedding(event_id, embedding)
except Exception as e:
    logger.warning(f"Embedding generation failed for event {event_id}: {e}")
    # Don't block event creation
```

### Project Structure Notes

**Files to create:**
- `backend/app/services/embedding_service.py` - Embedding generation
- `backend/app/models/event_embedding.py` - Database model
- `backend/app/api/v1/context.py` - Context API endpoints
- `backend/alembic/versions/xxxx_add_event_embeddings_table.py` - Migration
- `backend/tests/test_services/test_embedding_service.py` - Unit tests
- `backend/tests/test_integration/test_embedding_integration.py` - Integration tests

**Files to modify:**
- `backend/app/models/__init__.py` - Export new model
- `backend/app/services/event_processor.py` - Add embedding step
- `backend/requirements.txt` - Add sentence-transformers
- `backend/app/api/v1/__init__.py` - Register context router

### Performance Considerations

- Model loading is lazy (first embedding request triggers load)
- CLIP ViT-B/32 is ~350MB, loads in ~2-3 seconds on first use
- GPU acceleration available if CUDA/MPS present (optional, not required)
- Embeddings stored as JSON for SQLite compatibility (pgvector migration possible later)

### Learnings from Previous Story

**From Story P4-2.5 (Camera Status Sensors) (Status: done)**

- **Service Singleton Pattern**: Use `get_embedding_service()` dependency function for FastAPI injection
- **Event Processor Hook**: Add embedding step after existing Step 8 (MQTT publishing)
- **Graceful Degradation**: Log warnings but don't fail event creation if embedding fails
- **Test Coverage Pattern**: 28 unit tests + 12 integration tests = comprehensive coverage target

**Files Created in Previous Epic (P4-2):**
- `backend/app/services/mqtt_service.py` (P4-2.1) - Service pattern reference
- `backend/app/services/mqtt_status_service.py` (P4-2.5) - Scheduler pattern reference
- `backend/app/schemas/mqtt.py` (P4-2.5) - Schema pattern reference

**Reusable Patterns:**
- Service initialization in `main.py` lifespan context
- Dependency injection via `Depends(get_embedding_service)`
- Error handling: catch exceptions, log warnings, continue processing

[Source: docs/sprint-artifacts/p4-2-5-camera-status-sensors.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase4.md#Story-P4-3.1-Event-Embedding-Generation]
- [Source: docs/PRD-phase4.md#FR1 - System stores event embeddings for similarity comparison]
- [Source: docs/architecture.md#Phase-4-Additions - ADR-P4-001: Image Embedding Model Selection]
- [Source: docs/architecture.md#Phase-4-Database-Schema-Additions - event_embeddings table]
- [Sentence Transformers CLIP Documentation](https://www.sbert.net/docs/sentence_transformer/pretrained_models.html)

## Dev Agent Record

### Context Reference

- [p4-3-1-event-embedding-generation.context.xml](./p4-3-1-event-embedding-generation.context.xml)

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

None

### Completion Notes List

- All 40 tests passing (18 unit tests, 12 integration tests, 10 API validation tests)
- Embedding service uses lazy model loading - CLIP model only loads on first use
- Step 9 added to event_processor.py for embedding generation (after MQTT publishing)
- Embeddings stored as JSON arrays in SQLite Text column for compatibility
- Batch endpoint validates limit 1-100 per request
- Event relationship added for one-to-one embedding access

### File List

**Files Created:**
- `backend/app/services/embedding_service.py` - EmbeddingService with CLIP model
- `backend/app/models/event_embedding.py` - EventEmbedding database model
- `backend/app/api/v1/context.py` - Context API endpoints
- `backend/alembic/versions/029_add_event_embeddings_table.py` - Migration
- `backend/tests/test_services/test_embedding_service.py` - 18 unit tests
- `backend/tests/test_integration/test_embedding_integration.py` - 12 integration tests
- `backend/tests/test_api/test_context.py` - 10 API validation tests

**Files Modified:**
- `backend/app/models/__init__.py` - Added EventEmbedding export
- `backend/app/models/event.py` - Added embedding relationship
- `backend/app/services/event_processor.py` - Added Step 9 embedding generation
- `backend/requirements.txt` - Added sentence-transformers>=2.2.0
- `backend/main.py` - Registered context router

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-11 | Claude Opus 4.5 | Initial story draft |
| 2025-12-11 | Claude Opus 4.5 | Implementation complete - all tasks done |
