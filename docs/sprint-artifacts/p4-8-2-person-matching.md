# Story P4-8.2: Person Matching

**Epic:** P4-8 Person & Vehicle Recognition (Growth)
**Status:** done
**Created:** 2025-12-13
**Story Key:** p4-8-2-person-matching

---

## User Story

**As a** home security user
**I want** the system to match detected faces to known persons
**So that** I get personalized alerts like "John is at the door" instead of generic "Person detected"

---

## Background & Context

This story builds on P4-8.1 (Face Embedding Storage) to add face-to-person matching. The face embeddings generated in P4-8.1 need to be matched against named persons for recognition.

**Dependencies (Already Done):**
- **P4-8.1:** `FaceDetectionService`, `FaceEmbeddingService`, `FaceEmbedding` model
- **P4-3.3:** `EntityService`, `RecognizedEntity` model with `entity_type` and `name` fields
- **P4-3.3:** `EntityEvent` junction table for linking entities to events

**What This Story Adds:**
1. **Face-to-Person Matching** - Link face embeddings to RecognizedEntity records (type='person')
2. **Multiple Faces Handling** - Match each face in a frame to potentially different persons
3. **Confidence Thresholds** - Configurable matching threshold separate from general entity matching
4. **Appearance Change Handling** - Update reference embedding when high-confidence match differs
5. **Named Person Alerts** - Include person name in event descriptions when matched

**Key Insight:**
The existing `RecognizedEntity` model already supports named entities with `entity_type='person'`. Face embeddings from P4-8.1 are more focused (cropped faces) than full-frame embeddings, so they should provide better person matching accuracy.

---

## Acceptance Criteria

### AC1: Face-to-Person Matching Service
- [x] Create `PersonMatchingService` class that matches face embeddings to known persons
- [x] Use existing `RecognizedEntity` records where `entity_type='person'`
- [x] Calculate cosine similarity between face embeddings and person reference embeddings
- [x] Return match result with person ID, name, and confidence score
- [x] Support configurable matching threshold (default 0.70, tighter than entity default of 0.75)

### AC2: Multiple Faces in Single Frame
- [x] Process each face embedding independently
- [x] Each face can match to a different known person (or none)
- [x] Return list of match results, one per face
- [x] Order results by face confidence (highest first)

### AC3: Link Face Embeddings to Entities
- [x] Update `FaceEmbedding.entity_id` when a match is found
- [x] Create `EntityEvent` link when face matches to person
- [x] Update person's `last_seen_at` and `occurrence_count`
- [x] Handle case where same person appears multiple times in same event

### AC4: New Person Creation from Faces
- [x] When no match found, optionally create new entity with `entity_type='person'`
- [x] Use face embedding as reference embedding for new person
- [x] New persons start unnamed (user can name later via existing UI)
- [x] Configurable setting to enable/disable auto-creation (`auto_create_persons`)

### AC5: Appearance Change Handling
- [x] When high-confidence match (>0.90) but embedding differs significantly
- [x] Option to update reference embedding (weighted average or replace)
- [x] Track embedding version to handle model upgrades
- [x] Log appearance updates for debugging

### AC6: Pipeline Integration
- [x] Integrate person matching after face embedding storage in event processor
- [x] Run asynchronously (non-blocking, after event stored)
- [x] Only run when `face_recognition_enabled` is true
- [x] Include matched person names in logs

### AC7: API Endpoints for Person Data
- [x] `GET /api/v1/context/persons` - List all known persons with face counts
- [x] `GET /api/v1/context/persons/{id}` - Get person details with recent face matches
- [x] `PUT /api/v1/context/persons/{id}` - Update person name
- [x] Leverage existing entity endpoints where possible (avoid duplication)

### AC8: Testing
- [x] Unit tests for PersonMatchingService (matching, no-match, multi-face)
- [x] Integration tests for pipeline (face → embedding → person match)
- [x] Test appearance change handling
- [x] Test with threshold edge cases (0.69 vs 0.70 vs 0.71)

---

## Technical Implementation

### Task 1: Create PersonMatchingService
**File:** `backend/app/services/person_matching_service.py` (new)
```python
class PersonMatchingService:
    """
    Match face embeddings to known persons.

    Uses CLIP embeddings from FaceEmbeddingService and matches against
    RecognizedEntity records with entity_type='person'.
    """
    DEFAULT_THRESHOLD = 0.70  # Tighter than general entity threshold
    HIGH_CONFIDENCE_THRESHOLD = 0.90

    async def match_faces_to_persons(
        self,
        db: Session,
        face_embedding_ids: list[str],
        auto_create: bool = True,
    ) -> list[PersonMatchResult]:
        """Match multiple face embeddings to known persons."""

    async def match_single_face(
        self,
        db: Session,
        face_embedding_id: str,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> Optional[PersonMatchResult]:
        """Match a single face embedding to a person."""
```

### Task 2: Create PersonMatchResult Dataclass
**File:** `backend/app/services/person_matching_service.py`
```python
@dataclass
class PersonMatchResult:
    face_embedding_id: str
    person_id: Optional[str]  # None if no match and no auto-create
    person_name: Optional[str]
    similarity_score: float
    is_new_person: bool
    is_appearance_update: bool
    bounding_box: dict  # From face embedding
```

### Task 3: Add Person Matching Settings
**File:** `backend/app/schemas/system.py` (modify)
- Add `person_match_threshold` (default 0.70)
- Add `auto_create_persons` (default true)
- Add `update_appearance_on_high_match` (default true)

### Task 4: Integrate into Event Pipeline
**File:** `backend/app/services/event_processor.py` (modify)
- Add Step 13: Person matching after face processing
- Call PersonMatchingService with face embedding IDs from Step 12
- Log matched person names

### Task 5: Add Person-Focused API Endpoints
**File:** `backend/app/api/v1/context.py` (modify)
- Add `GET /api/v1/context/persons` endpoint
- Filter existing entities by `entity_type='person'`
- Include face_count from FaceEmbedding table

### Task 6: Write Tests
**Files:**
- `backend/tests/test_services/test_person_matching_service.py` (new)
- `backend/tests/test_api/test_context_persons.py` (new)

---

## Dev Notes

### Architecture Constraints

**Why a Separate PersonMatchingService?**
- Face embeddings are more focused than full-frame embeddings
- Person matching needs tighter thresholds (faces look similar)
- Need to handle multiple faces per event differently than single entity match
- Separation of concerns: FaceEmbeddingService handles detection/storage, PersonMatchingService handles recognition

**Embedding Compatibility:**
- Face embeddings use same CLIP model as general embeddings
- Existing `RecognizedEntity` records may have full-frame embeddings (entity_type='person')
- New face-based entities will have face-cropped embeddings
- Consider tracking embedding source (face vs full-frame) in future

[Source: docs/architecture.md#Phase-4-ADRs]

### Privacy Requirements

From PRD Phase 4:
> "Face embeddings stored locally only (never cloud)"
> "Named person/vehicle tagging" (user-initiated naming)

Implementation:
1. Auto-created persons are unnamed by default
2. User must explicitly name persons via UI
3. Person data excluded from any backup/export by default

[Source: docs/PRD-phase4.md#NFR1-Privacy]

### Learnings from Previous Story

**From Story p4-8-1-face-embedding-storage (Status: done)**

- **Settings Pattern**: Use `no_prefix_fields` set for settings accessed by services
- **Async Fire-and-Forget**: Use `asyncio.create_task()` for non-blocking background processing
- **Service Singleton**: Follow `get_face_embedding_service()` pattern
- **FaceEmbedding has entity_id**: Already has nullable FK to `recognized_entities`

**Files to Reference:**
- `backend/app/services/face_embedding_service.py` - Face processing patterns
- `backend/app/services/entity_service.py` - Entity matching and creation
- `backend/app/models/face_embedding.py` - FaceEmbedding.entity_id column

[Source: docs/sprint-artifacts/p4-8-1-face-embedding-storage.md#Dev-Agent-Record]

---

## Dev Agent Record

### Context Reference

- [docs/sprint-artifacts/p4-8-2-person-matching.context.xml](p4-8-2-person-matching.context.xml)

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Initial tests passed: 30/30 for P4-8.2 specific tests
- Fixed test mocking issues in threshold and multi-face tests

### Completion Notes List

1. **PersonMatchingService Created** - Full implementation with cosine similarity matching, auto-create, and appearance updates
2. **Settings Added** - `person_match_threshold`, `auto_create_persons`, `update_appearance_on_high_match`
3. **Pipeline Integration** - Step 13 added to event_processor.py for async person matching
4. **API Endpoints** - GET/PUT for /api/v1/context/persons with proper schemas
5. **Tests** - 20 unit tests for service, 10 API tests

### File List

**New Files:**
- `backend/app/services/person_matching_service.py` - PersonMatchingService class with match/create/update logic
- `backend/tests/test_services/test_person_matching_service.py` - 20 unit tests
- `backend/tests/test_api/test_context_persons.py` - 10 API endpoint tests

**Modified Files:**
- `backend/app/schemas/system.py` - Added 3 person matching settings fields
- `backend/app/api/v1/system.py` - Added settings to no_prefix_fields set
- `backend/app/api/v1/context.py` - Added person endpoints (list, get, update)
- `backend/app/services/event_processor.py` - Added Step 13 person matching integration

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-13 | SM Agent | Initial story creation |
| 2025-12-13 | Dev Agent | Implementation complete - all AC met |
| 2025-12-13 | Senior Dev Review | Code review approved |

---

## Senior Developer Review (AI)

### Reviewer
Brent (Claude Opus 4.5)

### Date
2025-12-13

### Outcome
**APPROVE** - All acceptance criteria verified implemented, all tasks verified complete, tests passing.

### Summary
Story P4-8.2 implements face-to-person matching with a well-structured `PersonMatchingService`. The implementation correctly links face embeddings to `RecognizedEntity` records, handles multiple faces per event, and integrates cleanly into the event processing pipeline as Step 13.

### Key Findings

**No HIGH or MEDIUM severity issues found.**

**Low Severity:**
- `import numpy as np` inside method (line 433) could be moved to top of file for consistency, but it's a minor style issue and keeps numpy as a lazy import.

### Acceptance Criteria Coverage

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| AC1 | Face-to-Person Matching Service | IMPLEMENTED | `person_matching_service.py:47-488` |
| AC2 | Multiple Faces in Single Frame | IMPLEMENTED | `person_matching_service.py:126-183` |
| AC3 | Link Face Embeddings to Entities | IMPLEMENTED | `person_matching_service.py:368-378, 457-474` |
| AC4 | New Person Creation from Faces | IMPLEMENTED | `person_matching_service.py:335-393` |
| AC5 | Appearance Change Handling | IMPLEMENTED | `person_matching_service.py:424-450` |
| AC6 | Pipeline Integration | IMPLEMENTED | `event_processor.py:1545-1593` |
| AC7 | API Endpoints for Person Data | IMPLEMENTED | `context.py:1294-1448` |
| AC8 | Testing | IMPLEMENTED | 30 tests, all passing |

**Summary: 8 of 8 acceptance criteria fully implemented**

### Task Completion Validation

| Task | Marked As | Verified As | Evidence |
|------|-----------|-------------|----------|
| Task 1: Create PersonMatchingService | Complete | VERIFIED | `person_matching_service.py:47-709` |
| Task 2: Create PersonMatchResult | Complete | VERIFIED | `person_matching_service.py:35-44` |
| Task 3: Add Person Matching Settings | Complete | VERIFIED | `system.py:282-290, 523-525` |
| Task 4: Integrate into Event Pipeline | Complete | VERIFIED | `event_processor.py:1545-1593` |
| Task 5: Add Person-Focused API Endpoints | Complete | VERIFIED | `context.py:1294-1448` |
| Task 6: Write Tests | Complete | VERIFIED | 30 tests total |

**Summary: 6 of 6 completed tasks verified, 0 questionable, 0 false completions**

### Test Coverage and Gaps
- Unit tests: 20 tests in `test_person_matching_service.py` covering matching, no-match, multi-face, threshold edge cases
- API tests: 10 tests in `test_context_persons.py` covering list/get/update endpoints
- All tests passing (30/30)

### Architectural Alignment
- Follows singleton service pattern (`get_person_matching_service()`)
- Uses existing `batch_cosine_similarity` from `similarity_service.py`
- Properly integrates with `RecognizedEntity` and `EntityEvent` models
- Uses async fire-and-forget pattern consistent with P4-8.1

### Security Notes
- Face data stored locally only (privacy requirement met)
- New persons start unnamed (user must explicitly name)
- No sensitive data exposure in API responses

### Best-Practices and References
- [FastAPI Dependency Injection](https://fastapi.tiangolo.com/tutorial/dependencies/) - Used for service injection in endpoints
- [SQLAlchemy 2.0 Patterns](https://docs.sqlalchemy.org/en/20/) - Session management follows best practices

### Action Items

**Code Changes Required:**
- None required

**Advisory Notes:**
- Note: Consider moving `import numpy as np` to module top-level for consistency (minor style preference)
- Note: Future enhancement could track embedding source (face vs full-frame) for better debugging
