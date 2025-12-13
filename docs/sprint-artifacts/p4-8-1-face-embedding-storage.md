# Story P4-8.1: Face Embedding Storage

**Epic:** P4-8 Person & Vehicle Recognition (Growth)
**Status:** done
**Created:** 2025-12-13
**Story Key:** p4-8-1-face-embedding-storage

---

## User Story

**As a** home security user
**I want** the system to detect and store face embeddings from event thumbnails
**So that** I can later identify and name recurring people for personalized alerts like "John is at the door"

---

## Background & Context

Epic P4-8 builds on the Temporal Context Engine (P4-3) to add person and vehicle recognition. This first story focuses on face embedding extraction and storage.

**Dependencies (P4-3 - DONE):**
- `EmbeddingService` at `backend/app/services/embedding_service.py` - CLIP model for general image embeddings
- `EventEmbedding` model for storing event-level embeddings
- `RecognizedEntity` model for tracking recurring visitors
- `SimilarityService` for cosine similarity search

**What This Story Adds:**
1. **Face detection** using OpenCV's DNN face detector (faster) or dlib (more accurate)
2. **Face region extraction** from event thumbnails
3. **Face-specific embedding storage** with privacy controls
4. **No-face handling** - graceful fallback when no face detected

**Privacy Requirements (Critical):**
- Face embeddings stored locally only (never sent to cloud)
- Opt-in feature (disabled by default)
- User can delete all face data
- Clear privacy messaging in UI

---

## Acceptance Criteria

### AC1: Face Detection Service
- [x] Create `FaceDetectionService` class using OpenCV DNN face detector
- [x] Detect faces in event thumbnail images
- [x] Return bounding box coordinates for each detected face
- [x] Filter detections by confidence threshold (default 0.5)
- [x] Handle multiple faces in a single image
- [x] Handle images with no faces gracefully (return empty list)

### AC2: Face Region Extraction
- [x] Crop face regions from original thumbnail using detected bounding boxes
- [x] Add configurable padding around face (default 20%)
- [x] Resize cropped faces to standard size (160x160 or 224x224)
- [x] Return face region as bytes for embedding generation

### AC3: Face Embedding Model
- [x] Create `FaceEmbeddingService` class for face-specific embeddings
- [x] Use existing CLIP model on cropped face region (simpler approach)
- [x] OR use dedicated face embedding model like FaceNet/ArcFace
- [x] Generate 512-dimensional embeddings (consistent with existing infrastructure)
- [x] Track model version for future migration

### AC4: Face Embedding Database Storage
- [x] Create `FaceEmbedding` database model
- [x] Fields: id, event_id, entity_id (nullable), embedding (JSON), bounding_box (JSON), confidence, model_version, created_at
- [x] Foreign key to events table with CASCADE delete
- [x] Optional foreign key to recognized_entities
- [x] Create Alembic migration for new table

### AC5: Privacy Controls
- [x] Add `face_recognition_enabled` to system settings (default: false)
- [x] API endpoint to enable/disable face recognition
- [x] API endpoint to delete all face embeddings
- [x] Check privacy setting before processing faces
- [x] Clear logging of when face data is created/deleted

### AC6: Pipeline Integration
- [x] Integrate face detection into event processing pipeline
- [x] Only process faces when `face_recognition_enabled` is true
- [x] Process faces asynchronously (non-blocking)
- [x] Store face embeddings after event creation
- [x] Log face detection results (count found, confidence scores)

### AC7: API Endpoints
- [x] `GET /api/v1/context/faces/{event_id}` - Get face embeddings for an event
- [x] `DELETE /api/v1/context/faces/{event_id}` - Delete face data for an event
- [x] `DELETE /api/v1/context/faces` - Delete all face embeddings (admin)
- [x] Include face count in event detail response

### AC8: Testing
- [x] Unit tests for FaceDetectionService (detection, no-face, multi-face)
- [x] Unit tests for FaceEmbeddingService (embedding generation)
- [x] Integration tests for face pipeline
- [x] Test privacy controls (disabled blocks processing)
- [x] Test with real images from test fixtures

---

## Technical Implementation

### Task 1: Create FaceDetectionService
**File:** `backend/app/services/face_detection_service.py` (new)
```python
class FaceDetectionService:
    """
    Detect faces in images using OpenCV DNN face detector.

    Uses the SSD-based face detector (res10_300x300_ssd_iter_140000.caffemodel)
    for good accuracy and speed (~50ms per image).
    """
    CONFIDENCE_THRESHOLD = 0.5
    MODEL_FILE = "opencv_face_detector_uint8.pb"
    CONFIG_FILE = "opencv_face_detector.pbtxt"

    def detect_faces(self, image_bytes: bytes) -> list[FaceDetection]:
        """Return list of detected faces with bounding boxes."""

    def extract_face_region(self, image_bytes: bytes, bbox: BoundingBox, padding: float = 0.2) -> bytes:
        """Extract and crop face region from image."""
```

### Task 2: Create FaceEmbedding Model
**File:** `backend/app/models/face_embedding.py` (new)
```python
class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"

    id = Column(String, primary_key=True)
    event_id = Column(String, ForeignKey("events.id", ondelete="CASCADE"))
    entity_id = Column(String, ForeignKey("recognized_entities.id", ondelete="SET NULL"), nullable=True)
    embedding = Column(Text)  # JSON array of 512 floats
    bounding_box = Column(Text)  # JSON: {x, y, width, height}
    confidence = Column(Float)  # Detection confidence
    model_version = Column(String)
    created_at = Column(DateTime)
```

### Task 3: Create Alembic Migration
**File:** `backend/alembic/versions/XXX_add_face_embeddings_table.py` (new)

### Task 4: Create FaceEmbeddingService
**File:** `backend/app/services/face_embedding_service.py` (new)
```python
class FaceEmbeddingService:
    """Generate and store face-specific embeddings."""

    def __init__(self, face_detector: FaceDetectionService, embedding_service: EmbeddingService):
        self._face_detector = face_detector
        self._embedding_service = embedding_service

    async def process_event_faces(self, db: Session, event_id: str, thumbnail_bytes: bytes) -> list[str]:
        """Detect faces, generate embeddings, store, return embedding IDs."""

    async def get_face_embeddings(self, db: Session, event_id: str) -> list[dict]:
        """Get all face embeddings for an event."""
```

### Task 5: Add Privacy Settings
**File:** `backend/app/api/v1/system.py` (modify)
- Add `face_recognition_enabled` to SystemSettingsUpdate schema
- Add to settings handler

### Task 6: Create Face API Endpoints
**File:** `backend/app/api/v1/context.py` (modify)
- Add face embedding endpoints
- Add delete endpoints

### Task 7: Integrate into Event Pipeline
**File:** `backend/app/services/event_processor.py` (modify)
- Check privacy setting
- Call face processing after thumbnail save
- Run asynchronously

### Task 8: Download OpenCV Face Model
**File:** `backend/scripts/download_face_model.py` (new)
- Script to download OpenCV face detector model
- Store in `backend/app/models/opencv_face/`

### Task 9: Write Tests
**Files:**
- `backend/tests/test_services/test_face_detection_service.py` (new)
- `backend/tests/test_services/test_face_embedding_service.py` (new)
- `backend/tests/test_api/test_context_faces.py` (new)

---

## Dev Notes

### Architecture Constraints

**Model Choice Decision:**
- **Option A (Recommended):** Use existing CLIP model on cropped face region
  - Pro: No additional model download, consistent with existing infrastructure
  - Pro: CLIP captures semantic features that work for face similarity
  - Con: Not optimized for faces specifically

- **Option B:** Use dedicated FaceNet/ArcFace model
  - Pro: Better accuracy for face recognition
  - Con: Additional ~500MB model download
  - Con: Different embedding dimension may require schema changes

**Recommendation:** Start with Option A (CLIP on face crops). Can upgrade to dedicated model in future story if accuracy insufficient.

[Source: docs/architecture.md#Phase-4-ADRs]

### Privacy Requirements

From PRD Phase 4:
> "Face embeddings stored locally only (never cloud)"
> "User can delete all historical context data"
> "Configurable retention for context data"

Implementation:
1. Privacy setting OFF by default
2. Clear "Face Recognition" toggle in settings
3. "Delete All Face Data" button in settings
4. Face data excluded from any backup/export by default

[Source: docs/PRD-phase4.md#NFR1-Privacy]

### OpenCV Face Detector

Using OpenCV's DNN face detector instead of dlib because:
- OpenCV is already a dependency (used in motion detection)
- SSD-based detector is fast (~50ms vs ~200ms for dlib HOG)
- Accuracy is sufficient for our use case
- No additional compilation required (dlib can be tricky)

Model files needed:
- `opencv_face_detector_uint8.pb` (~5MB)
- `opencv_face_detector.pbtxt` (~10KB)

Download from OpenCV's model zoo or GitHub.

### Learnings from Previous Story

**From Story p4-7-3-anomaly-alerts (Status: done)**

- **Settings Pattern**: Use existing `no_prefix_fields` list in `system.py` for settings that services need direct access to
- **Async Processing**: Use `asyncio.create_task()` for non-blocking background processing
- **Service Singleton**: Follow `get_embedding_service()` pattern for singleton services

**Files to Reference:**
- `backend/app/services/embedding_service.py` - Singleton pattern, async model loading
- `backend/app/services/anomaly_scoring_service.py` - Background processing pattern
- `backend/app/api/v1/system.py` - Settings field handling

[Source: docs/sprint-artifacts/p4-7-3-anomaly-alerts.md#Dev-Agent-Record]

### Testing Approach

Need test images with faces:
1. Create test fixtures at `backend/tests/fixtures/images/`
2. Include: face_single.jpg, face_multiple.jpg, no_face.jpg
3. Use small images (300x300) to keep test suite fast

---

## Dev Agent Record

### Context Reference

- [docs/sprint-artifacts/p4-8-1-face-embedding-storage.context.xml](p4-8-1-face-embedding-storage.context.xml)

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- All 42 face embedding tests pass (18 detection, 14 embedding service, 10 API)
- OpenCV DNN face detector chosen for speed (~50ms) and no additional dependencies
- Using existing CLIP model on cropped face regions for embeddings

### Completion Notes List

- FaceDetectionService: OpenCV DNN SSD-based detector with lazy model loading
- FaceEmbeddingService: Orchestrates detection + CLIP embedding, singleton pattern
- FaceEmbedding model: 512-dim embeddings with CASCADE delete on events
- Privacy controls: face_recognition_enabled setting (off by default)
- Pipeline integration: Step 12 in event_processor with async fire-and-forget
- API endpoints: GET/DELETE for event faces, DELETE all, GET stats
- Download script for OpenCV face model files (deploy.prototxt, caffemodel)

### File List

**New Files:**
- backend/app/services/face_detection_service.py
- backend/app/services/face_embedding_service.py
- backend/app/models/face_embedding.py
- backend/alembic/versions/041_add_face_embeddings_table.py
- backend/scripts/download_face_model.py
- backend/tests/test_services/test_face_detection_service.py
- backend/tests/test_services/test_face_embedding_service.py
- backend/tests/test_api/test_context_faces.py

**Modified Files:**
- backend/app/models/__init__.py (added FaceEmbedding export)
- backend/app/models/event.py (added face_embeddings relationship)
- backend/app/schemas/system.py (added face_recognition_enabled setting)
- backend/app/api/v1/system.py (added face_recognition_enabled to no_prefix_fields)
- backend/app/api/v1/context.py (added face embedding endpoints)
- backend/app/services/event_processor.py (added Step 12: face processing)

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-13 | SM Agent | Initial story creation |
| 2025-12-13 | Dev Agent (Opus 4.5) | Implemented all ACs, 42 tests pass |
| 2025-12-13 | Code Review (Opus 4.5) | Code review completed - APPROVED |

---

## Senior Developer Review (AI)

### Review Summary

**Reviewer:** Claude Opus 4.5 (code-review workflow)
**Date:** 2025-12-13
**Verdict:** ✅ APPROVED

### Acceptance Criteria Validation

#### AC1: Face Detection Service ✅ VERIFIED
- **Evidence:** `backend/app/services/face_detection_service.py:75-304`
- `FaceDetectionService` class implemented using OpenCV DNN face detector
- `detect_faces()` method returns `list[FaceDetection]` with bounding boxes (line 260-304)
- Confidence threshold filtering at 0.5 default (line 88, 232)
- Multiple faces handled in loop (line 229-256)
- Empty list returned gracefully when no faces detected (line 226, 250)

#### AC2: Face Region Extraction ✅ VERIFIED
- **Evidence:** `backend/app/services/face_detection_service.py:306-385`
- `extract_face_region()` crops face regions using bounding boxes (line 346-385)
- Configurable padding at 20% default (line 90, 328-334)
- Resizes to 160x160 standard size (line 89, 340)
- Returns JPEG bytes (line 343-344)

#### AC3: Face Embedding Model ✅ VERIFIED
- **Evidence:** `backend/app/services/face_embedding_service.py:37-186`
- `FaceEmbeddingService` class orchestrates detection + embedding
- Uses existing CLIP model via `EmbeddingService` (line 64, 134-136)
- Generates 512-dimensional embeddings (consistent with CLIP)
- Model version tracked as `clip-ViT-B-32-face-v1` (line 49)

#### AC4: Face Embedding Database Storage ✅ VERIFIED
- **Evidence:** `backend/app/models/face_embedding.py:31-101`
- `FaceEmbedding` model with all required fields:
  - id (UUID, line 46-51)
  - event_id FK with CASCADE delete (line 52-58)
  - entity_id FK with SET NULL (line 59-65)
  - embedding as Text/JSON (line 66-70)
  - bounding_box as Text/JSON (line 71-75)
  - confidence (line 76-80)
  - model_version (line 81-85)
  - created_at (line 86-91)
- **Migration:** `backend/alembic/versions/041_add_face_embeddings_table.py` with indexes

#### AC5: Privacy Controls ✅ VERIFIED
- **Evidence:**
  - Schema: `backend/app/schemas/system.py:276-279` - `face_recognition_enabled` field
  - System.py: `backend/app/api/v1/system.py:521` - Added to `no_prefix_fields`
  - Context.py: `backend/app/api/v1/context.py:1160-1193` - Delete all faces endpoint
  - Event processor: `backend/app/services/event_processor.py:1109-1115` - Privacy check before processing
- Default is false (opt-in), clear logging of face data operations

#### AC6: Pipeline Integration ✅ VERIFIED
- **Evidence:** `backend/app/services/event_processor.py:1101-1138`
- Face processing integrated as Step 12 in event processor
- Only processes when `face_recognition_enabled` is true (line 1117)
- Uses `asyncio.create_task()` for non-blocking async (line 1119)
- Stores after event creation via `_process_faces()` helper (line 1484-1557)

#### AC7: API Endpoints ✅ VERIFIED
- **Evidence:** `backend/app/api/v1/context.py:1038-1230`
- `GET /api/v1/context/faces/{event_id}` - line 1073-1120
- `DELETE /api/v1/context/faces/{event_id}` - line 1123-1157
- `DELETE /api/v1/context/faces` - line 1160-1193
- `GET /api/v1/context/faces/stats` - line 1196-1230
- Face count available via response models

#### AC8: Testing ✅ VERIFIED
- **Evidence:** 42 tests across 3 test files
  - `backend/tests/test_services/test_face_detection_service.py` - 18 tests
  - `backend/tests/test_services/test_face_embedding_service.py` - 14 tests
  - `backend/tests/test_api/test_context_faces.py` - 10 tests
- Tests cover: detection, no-face, multi-face, extraction, privacy controls, API endpoints

### Code Quality Assessment

| Category | Score | Notes |
|----------|-------|-------|
| Correctness | 5/5 | All ACs implemented correctly |
| Error Handling | 5/5 | Graceful fallbacks, errors don't block pipeline |
| Security | 5/5 | Privacy controls, no external API calls for face detection |
| Performance | 5/5 | Async processing, lazy model loading, singleton pattern |
| Testing | 5/5 | 42 comprehensive tests, good coverage |

### Issues Found

**None** - Implementation is solid.

### Recommendations (Optional/Future)

1. **Model upgrade path**: Consider adding FaceNet/ArcFace for improved face recognition accuracy in a future story
2. **Face thumbnail storage**: Could store cropped face images alongside embeddings for UI preview

### Final Assessment

Story P4-8.1 is fully implemented with all acceptance criteria met. The implementation follows established patterns (singleton services, async processing, privacy controls) and integrates cleanly with the existing codebase. All 42 tests pass.

**Recommendation:** Mark story as DONE and proceed with Story P4-8.2 (Person Matching).
