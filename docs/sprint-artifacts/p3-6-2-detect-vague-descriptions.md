# Story P3-6.2: Detect Vague Descriptions

## Story

**As a** system,
**I want** to automatically detect vague AI descriptions,
**So that** ambiguous events are flagged for review and users can identify uncertain analyses.

## Status: done

## Acceptance Criteria

### AC1: Detect Vague Phrase Patterns
- [x] Given an AI description text
- [x] When vagueness detection runs after AI response
- [x] Then flags descriptions containing vague indicators:
  - "appears to be"
  - "possibly"
  - "unclear"
  - "cannot determine"
  - "something"
  - "motion detected" (without additional specifics)
  - "might be"
  - "could be"
  - "seems like"
  - "hard to tell"
- [x] And detection is case-insensitive

### AC2: Detect Insufficient Detail
- [x] Given an AI description text
- [x] When vagueness detection analyzes content
- [x] Then flags descriptions that are:
  - Too short (< 10 words total)
  - Generic without specific subjects ("activity detected", "movement observed")
- [x] And logs the reason for flagging

### AC3: Set Low Confidence on Vague Descriptions
- [x] Given a description flagged as vague by pattern or length
- [x] When combined with AI confidence evaluation
- [x] Then event.low_confidence = True regardless of AI-reported score
- [x] And vagueness detection supplements (not replaces) AI confidence scoring

### AC4: Track Vagueness Reason
- [x] Given a vague description detected
- [x] When event is stored
- [x] Then event includes `vague_reason` field explaining why flagged
- [x] And reason is human-readable (e.g., "Contains vague phrase: 'appears to be'")

### AC5: Allow Specific Descriptions Through
- [x] Given a specific description like "Person in blue jacket delivered package to front door"
- [x] When vagueness detection runs
- [x] Then NOT flagged as vague
- [x] And low_confidence is NOT set by vagueness detection
- [x] And only AI confidence score determines low_confidence flag

### AC6: Integration with Event Pipeline
- [x] Given vagueness detection module
- [x] When integrated into protect_event_handler
- [x] Then runs after AI response parsing
- [x] And before event storage
- [x] And does not block event processing on detection errors

## Tasks / Subtasks

- [x] **Task 1: Create Description Quality Module** (AC: 1, 2, 5)
  - [x] Create `backend/app/services/description_quality.py`
  - [x] Implement `detect_vague_description(description: str) -> tuple[bool, Optional[str]]`
  - [x] Define VAGUE_PHRASES constant with regex patterns
  - [x] Add word count check for minimum length (10 words)
  - [x] Add generic phrase detection patterns
  - [x] Return (is_vague: bool, reason: Optional[str])

- [x] **Task 2: Add Vague Reason Field to Event Model** (AC: 4)
  - [x] Create Alembic migration to add `vague_reason` TEXT column to events
  - [x] Update Event SQLAlchemy model with `vague_reason` field
  - [x] Update EventCreate and EventResponse Pydantic schemas
  - [x] Run migration and verify column exists

- [x] **Task 3: Integrate Detection into Event Pipeline** (AC: 3, 6)
  - [x] Modify `protect_event_handler.py` to import description_quality
  - [x] Call `detect_vague_description()` after AI response parsing
  - [x] If vague detected: set `low_confidence = True` and `vague_reason`
  - [x] Ensure detection errors are caught and logged (non-blocking)

- [x] **Task 4: Write Unit Tests** (AC: 1, 2, 3, 4, 5)
  - [x] Create `backend/tests/test_services/test_description_quality.py`
  - [x] Test each vague phrase pattern is detected
  - [x] Test short descriptions are flagged
  - [x] Test specific descriptions pass through
  - [x] Test vague_reason is set correctly
  - [x] Test low_confidence flag is set on vague descriptions

- [x] **Task 5: Write Integration Tests** (AC: 6)
  - [x] Test vagueness detection runs in event pipeline
  - [x] Test detection errors don't block event processing
  - [x] Test vague events stored with correct flags

## Dev Notes

### Relevant Architecture Patterns and Constraints

**Module Design:**
- Create standalone `description_quality.py` utility module
- Pure function design - no database or service dependencies
- Easy to test in isolation
- Can be extended later for more quality metrics

**Detection Logic:**
```python
VAGUE_PHRASES = [
    r"\bappears\s+to\s+be\b",
    r"\bpossibly\b",
    r"\bunclear\b",
    r"\bcannot\s+determine\b",
    r"\bsomething\b",
    r"\bmotion\s+detected\b(?!.*\b(person|vehicle|animal|package)\b)",
    r"\bmight\s+be\b",
    r"\bcould\s+be\b",
    r"\bseems\s+like\b",
    r"\bhard\s+to\s+tell\b",
]

GENERIC_PHRASES = [
    r"^activity\s+detected\.?$",
    r"^movement\s+observed\.?$",
    r"^something\s+moved\.?$",
]

MIN_WORD_COUNT = 10
```

**Integration Point:**
- In `protect_event_handler._store_protect_event()` after AI response
- After confidence parsing, before database insert
- Sets `low_confidence=True` if vague (OR with AI confidence < 50)

**Error Handling:**
- Vagueness detection failure should NOT block event processing
- Log warnings on detection errors
- Default to not-vague if detection fails (benefit of doubt)

### Project Structure Notes

**Files to Create:**
```
backend/app/services/description_quality.py      # Vagueness detection logic
backend/alembic/versions/020_add_vague_reason.py # Migration
backend/tests/test_services/test_description_quality.py  # Unit tests
```

**Files to Modify:**
```
backend/app/models/event.py         # Add vague_reason field
backend/app/schemas/event.py        # Add vague_reason to schemas
backend/app/services/protect_event_handler.py  # Integrate detection
```

### References

- [Source: docs/epics-phase3.md#Story-P3-6.2] - Story definition and acceptance criteria
- [Source: docs/PRD-phase3.md#Confidence-Scoring] - FR28 requirement
- [Source: backend/app/services/ai_service.py] - Current AI response parsing
- [Source: backend/app/services/protect_event_handler.py] - Event storage integration point
- [Source: docs/sprint-artifacts/p3-6-1-extract-confidence-score-from-ai-responses.md] - Previous story patterns

## Learnings from Previous Story

**From Story p3-6-1-extract-confidence-score-from-ai-responses (Status: done)**

- **Confidence Fields Available**: `ai_confidence` (INTEGER 0-100) and `low_confidence` (BOOLEAN) already exist in Event model
- **Low Confidence Logic**: Currently `low_confidence = True` when `ai_confidence < 50` - vagueness detection should OR with this condition
- **Integration Point**: `_store_protect_event()` in protect_event_handler.py sets these fields - add vagueness check there
- **Migration Pattern**: Migration 019 added confidence fields - follow same pattern for `vague_reason TEXT`
- **Schema Updates**: Both EventCreate and EventResponse updated - same updates needed for `vague_reason`
- **Test Pattern**: 30 comprehensive tests in test_confidence_extraction.py - follow same approach
- **Non-blocking Errors**: Parsing failures return None and continue - vagueness detection should follow same pattern
- **AIResult Dataclass**: Contains `ai_confidence` field returned from providers - vagueness detection runs on the description text

[Source: docs/sprint-artifacts/p3-6-1-extract-confidence-score-from-ai-responses.md#Dev-Agent-Record]

## Dependencies

- **Prerequisites Met:**
  - P3-6.1 (Confidence scoring implemented, `low_confidence` field exists)
- **Note:** This story adds supplemental vagueness detection to complement AI confidence scoring

## Estimate

**Small-Medium** - New utility module, database migration, integration into existing pipeline

## Definition of Done

- [x] `description_quality.py` module created with vagueness detection
- [x] `vague_reason` field added to Event model and schema
- [x] Database migration created and applied
- [x] Vague descriptions set `low_confidence = True` and `vague_reason`
- [x] Specific descriptions pass through without vague flag
- [x] Detection integrated into protect_event_handler pipeline
- [x] Unit tests pass with >80% coverage
- [x] Integration tests verify end-to-end behavior
- [x] No TypeScript/Python errors

## Dev Agent Record

### Context Reference

docs/sprint-artifacts/p3-6-2-detect-vague-descriptions.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- Created `description_quality.py` module with `detect_vague_description()` function
- Implemented 13 vague phrase patterns with case-insensitive regex matching
- Implemented 6 generic phrase patterns for exact-match detection
- Added MIN_WORD_COUNT = 10 for short description detection
- Created migration 020 to add `vague_reason` TEXT column to events table
- Updated Event model and EventCreate/EventResponse schemas with `vague_reason` field
- Integrated vagueness detection into `protect_event_handler._store_protect_event()`
- Detection logic: `low_confidence = (ai_confidence < 50) OR is_vague`
- Non-blocking error handling: detection failures don't block event storage
- 52 unit tests covering all AC scenarios (vague phrases, short descriptions, generic phrases, specific pass-through)
- 7 integration tests verifying pipeline behavior and error handling

### File List

**New Files:**
- backend/app/services/description_quality.py
- backend/alembic/versions/020_add_vague_reason_to_events.py
- backend/tests/test_services/test_description_quality.py
- backend/tests/test_integration/test_vagueness_detection.py

**Modified Files:**
- backend/app/models/event.py
- backend/app/schemas/event.py
- backend/app/services/protect_event_handler.py

## Change Log

- 2025-12-08: Story drafted from sprint-status backlog
- 2025-12-08: Implementation complete - all tasks done, 59 tests passing
- 2025-12-08: Code review APPROVED

## Code Review Notes

### Review Date: 2025-12-08

### Reviewer: Claude Opus 4.5 (claude-opus-4-5-20251101)

### Review Outcome: APPROVED

### Acceptance Criteria Validation

| AC | Status | Evidence |
|----|--------|----------|
| AC1: Detect Vague Phrase Patterns | IMPLEMENTED | `description_quality.py:22-37` - 13 vague phrase patterns with case-insensitive regex. Tests: `test_description_quality.py::TestVaguePhraseDetection` (12 tests) |
| AC2: Detect Insufficient Detail | IMPLEMENTED | `description_quality.py:41-51` - Generic phrases + MIN_WORD_COUNT=10. Tests: `TestShortDescriptionDetection` (4 tests), `TestGenericPhraseDetection` (12 tests) |
| AC3: Set Low Confidence on Vague | IMPLEMENTED | `protect_event_handler.py:1824-1825` - `low_confidence = low_confidence_from_ai or low_confidence_from_vague`. Integration tests verify. |
| AC4: Track Vagueness Reason | IMPLEMENTED | `event.py:77` - `vague_reason` column. `protect_event_handler.py:1852` - stored in Event. Tests: `TestVagueReasonTracking` (3 tests) |
| AC5: Allow Specific Descriptions | IMPLEMENTED | `description_quality.py:130-131` - returns `(False, None)` for valid descriptions. Tests: `TestSpecificDescriptionsPassThrough` (10 tests) |
| AC6: Integration with Event Pipeline | IMPLEMENTED | `protect_event_handler.py:1791-1822` - try/except ensures non-blocking. Tests: `TestVaguenessDetectionErrorHandling` (1 test) |

### Task Validation

| Task | Status | Evidence |
|------|--------|----------|
| Task 1: Create Description Quality Module | COMPLETE | `backend/app/services/description_quality.py` - 147 lines, pure function design |
| Task 2: Add Vague Reason Field | COMPLETE | Migration `020_add_vague_reason_to_events.py`, Model `event.py:77`, Schemas `event.py:39,111` |
| Task 3: Integrate into Pipeline | COMPLETE | `protect_event_handler.py:1791-1852` - detection after AI response, before DB insert |
| Task 4: Write Unit Tests | COMPLETE | `test_description_quality.py` - 52 unit tests covering all patterns |
| Task 5: Write Integration Tests | COMPLETE | `test_vagueness_detection.py` - 7 integration tests verifying pipeline behavior |

### Test Results

- **Total Tests**: 59 (52 unit + 7 integration)
- **Pass Rate**: 100%
- **Coverage**: All ACs covered with specific test classes

### Code Quality Assessment

**Strengths:**
1. **Pure function design** - `detect_vague_description()` has no external dependencies, easy to test
2. **Comprehensive patterns** - 13 vague phrases + 6 generic phrases covers common AI ambiguity
3. **Non-blocking error handling** - Detection failures don't block event storage (AC6)
4. **Clear documentation** - Module docstring with examples, AC comments throughout
5. **Correct OR logic** - `low_confidence = (ai_confidence < 50) OR is_vague` per requirements

**No Issues Found:**
- No security vulnerabilities
- No performance concerns (regex patterns are efficient)
- No missing error handling
- No breaking changes to existing functionality

### Definition of Done Checklist

- [x] `description_quality.py` module created with vagueness detection
- [x] `vague_reason` field added to Event model and schema
- [x] Database migration created and applied (020_add_vague_reason)
- [x] Vague descriptions set `low_confidence = True` and `vague_reason`
- [x] Specific descriptions pass through without vague flag
- [x] Detection integrated into protect_event_handler pipeline
- [x] Unit tests pass with >80% coverage (52 tests)
- [x] Integration tests verify end-to-end behavior (7 tests)
- [x] No TypeScript/Python errors

### Recommendation

**APPROVE** - Story P3-6.2 is fully implemented per all acceptance criteria. The implementation is clean, well-tested, and follows established patterns from P3-6.1. Ready to mark as DONE.
