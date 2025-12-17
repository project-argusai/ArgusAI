# Story P6-3.2: Implement Audio Event Detection Pipeline

Status: done

## Story

As a home owner,
I want the system to detect and classify audio events from my cameras,
so that I can receive alerts for sounds like glass breaking, gunshots, screams, or doorbell rings even when motion isn't detected.

## Acceptance Criteria

1. Audio classification model integration point created (pluggable architecture)
2. Supported event types: glass_break, gunshot, scream, doorbell
3. Confidence threshold configurable per event type (default 70%)
4. Events created with `audio_event_type` field in database
5. Audio events can trigger alerts like visual motion events

## Tasks / Subtasks

- [x] Task 1: Add audio event fields to Event model (AC: #4)
  - [x] Add `audio_event_type` enum field (glass_break, gunshot, scream, doorbell, other)
  - [x] Add `audio_confidence` float field for detection confidence
  - [x] Add `audio_duration_ms` int field for event audio duration
  - [x] Create Alembic migration for new fields
  - [x] Update Event schema to include audio fields in API responses

- [x] Task 2: Create AudioEventDetector service (AC: #1, #2, #3)
  - [x] Create `backend/app/services/audio_event_detector.py`
  - [x] Define `AudioEventType` enum (glass_break, gunshot, scream, doorbell, other)
  - [x] Create `AudioClassificationResult` dataclass for detection results
  - [x] Implement pluggable classifier interface (`BaseAudioClassifier`)
  - [x] Create placeholder `MockAudioClassifier` for testing (returns random classification)
  - [x] Add configurable confidence thresholds per event type
  - [x] Implement `detect_audio_events()` method that processes audio buffers

- [x] Task 3: Integrate audio detection into event pipeline (AC: #1, #4)
  - [x] Modify `event_processor.py` to check for audio events when processing camera events
  - [x] Create `AudioEventHandler` that listens for audio buffer ready signals
  - [x] When audio event detected with confidence > threshold, create Event with audio_event_type
  - [x] Store audio event metadata in event record

- [x] Task 4: Add audio event alert triggering (AC: #5)
  - [x] Extend `AlertRule` model to support `audio_event_type` matching
  - [x] Update `alert_engine.py` `evaluate_rule()` to check audio event types
  - [x] Add audio event type filter to alert rule creation API
  - [x] Audio events should trigger webhooks just like motion events

- [x] Task 5: Create API endpoint for audio event configuration (AC: #3)
  - [x] Add GET `/api/v1/audio/thresholds` to retrieve current confidence thresholds
  - [x] Add PATCH `/api/v1/audio/thresholds` to update thresholds per event type
  - [x] Store thresholds in system_settings table
  - [x] Return default thresholds if not configured

- [x] Task 6: Write tests (AC: #1-5)
  - [x] Unit tests for AudioEventDetector with mock classifier
  - [x] Test confidence threshold filtering (events below threshold not created)
  - [x] Test event creation with audio_event_type field
  - [x] Test alert rule matching for audio event types
  - [x] Integration test for full audio event flow (buffer → detection → event → alert)

## Dev Notes

- This story builds on P6-3.1 (Audio Stream Extraction) which provides the audio buffer
- PyAV is already available for audio processing
- The classifier interface is designed to be pluggable - actual ML model integration can be added later
- Initial implementation uses MockAudioClassifier for testing/demo purposes
- Consider using librosa or similar for audio feature extraction in future
- Audio buffer from P6-3.1 provides ~5 seconds of audio for analysis

### Project Structure Notes

- New file: `backend/app/services/audio_event_detector.py` - Core detection service
- New file: `backend/app/services/audio_classifiers/__init__.py` - Classifier plugins
- New file: `backend/app/services/audio_classifiers/base.py` - Base classifier interface
- New file: `backend/app/services/audio_classifiers/mock.py` - Mock for testing
- Modified: `backend/app/models/event.py` - Add audio event fields
- Modified: `backend/app/models/alert_rule.py` - Add audio event type filter
- Modified: `backend/app/services/event_processor.py` - Integrate audio detection
- Modified: `backend/app/services/alert_engine.py` - Handle audio event alerts
- Modified: `backend/app/api/v1/events.py` - Return audio fields
- New migration: `backend/alembic/versions/xxx_add_audio_event_fields.py`

### Learnings from Previous Story

**From Story p6-3-1-add-audio-stream-extraction-from-rtsp (Status: done)**

- **Audio Service Available**: `AudioStreamService` at `backend/app/services/audio_stream_service.py` - use `get_audio_chunk()` method to retrieve audio buffer
- **Thread-Safe Ring Buffer**: Audio buffer uses thread-safe ring buffer implementation
- **Camera Model Extended**: Camera model already has `audio_enabled` and `audio_codec` fields
- **PyAV Integration**: Audio extraction integrates with existing PyAV RTSP handling
- **API Pattern**: Audio endpoints follow pattern `/api/v1/cameras/{camera_id}/audio/*`
- **Test Pattern**: 27 comprehensive tests in `test_audio_stream_service.py` - follow similar patterns
- **Supported Codecs**: AAC, PCMU, PCMA, Opus, MP3, PCM are supported

[Source: docs/sprint-artifacts/p6-3-1-add-audio-stream-extraction-from-rtsp.md#Dev-Agent-Record]

### References

- [Source: docs/epics-phase6.md#Story P6-3.2]
- [Source: docs/backlog.md#FF-015] - Audio Capture from Cameras
- [Source: backend/app/services/audio_stream_service.py] - Audio buffer provider
- [Source: backend/app/services/event_processor.py] - Event processing pipeline
- [Source: backend/app/services/alert_engine.py] - Alert rule evaluation
- [Source: docs/architecture/08-implementation-patterns.md] - Testing patterns

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p6-3-2-implement-audio-event-detection-pipeline.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

- All 73 tests pass (35 detector + 14 handler + 13 API + 11 alert engine)

### Completion Notes List

- AC#1 (Pluggable architecture): Implemented BaseAudioClassifier abstract interface with MockAudioClassifier for testing
- AC#2 (Event types): Defined AudioEventType enum with glass_break, gunshot, scream, doorbell, other
- AC#3 (Configurable thresholds): Default 70% threshold per event type, persisted in system_settings via API
- AC#4 (Database fields): Added audio_event_type, audio_confidence, audio_duration_ms to Event model
- AC#5 (Alert triggering): Extended AlertEngine with _check_audio_event_types() and audio_event_types condition support

### File List

New files:
- backend/app/services/audio_event_detector.py
- backend/app/services/audio_event_handler.py
- backend/app/services/audio_classifiers/__init__.py
- backend/app/services/audio_classifiers/base.py
- backend/app/services/audio_classifiers/mock.py
- backend/app/api/v1/audio.py
- backend/alembic/versions/048_add_audio_event_fields.py
- backend/tests/test_services/test_audio_event_detector.py
- backend/tests/test_services/test_audio_event_handler.py
- backend/tests/test_services/test_alert_engine_audio.py
- backend/tests/test_api/test_audio_api.py

Modified files:
- backend/app/models/event.py (added audio fields)
- backend/app/models/alert_rule.py (updated conditions doc)
- backend/app/schemas/event.py (added audio fields to response)
- backend/app/services/event_processor.py (added Step 16 audio enrichment)
- backend/app/services/alert_engine.py (added audio event type matching)
- backend/main.py (registered audio router)

## Senior Developer Review

**Review Date:** 2025-12-17
**Reviewer:** Claude Opus 4.5 (Code Review Workflow)
**Status:** ✅ APPROVED

### Acceptance Criteria Validation

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| 1 | Audio classification model integration point created (pluggable architecture) | ✅ Pass | `BaseAudioClassifier` ABC in `audio_classifiers/base.py` with `classify()`, `get_supported_event_types()`, `get_model_name()` methods |
| 2 | Supported event types: glass_break, gunshot, scream, doorbell | ✅ Pass | `AudioEventType` enum with 5 types (includes `other`). Verified in `test_all_supported_types_exist` |
| 3 | Confidence threshold configurable per event type (default 70%) | ✅ Pass | `DEFAULT_THRESHOLDS` dict with 0.70 for all types. API at `/api/v1/audio/thresholds` for PATCH updates |
| 4 | Events created with `audio_event_type` field in database | ✅ Pass | Migration `048_add_audio_event_fields.py` adds columns. Schema updated in `EventResponse` |
| 5 | Audio events can trigger alerts like visual motion events | ✅ Pass | `_check_audio_event_types()` method in AlertEngine (check #9). Tested in `test_alert_engine_audio.py` |

### Code Quality Assessment

**Architecture (9/10)**
- Clean pluggable classifier design via abstract base class
- Singleton pattern for service instances with proper lazy initialization
- Good separation: detector (classification) vs handler (event creation)
- Fire-and-forget async pattern for non-blocking enrichment

**Code Standards (9/10)**
- Comprehensive docstrings with story references (e.g., "Story P6-3.2 AC#4")
- Type hints throughout with dataclasses for structured data
- Proper validation with ValueError for invalid inputs
- Consistent logging with structured extra fields

**Testing (10/10)**
- 73 tests covering all components
- Unit tests for all service methods
- Edge cases: below threshold, no detection, disabled audio
- API tests for endpoints including validation errors

**Security (10/10)**
- Input validation on thresholds (0.0-1.0 range enforced at API and service level)
- Case-insensitive event type matching prevents injection
- No direct SQL - uses SQLAlchemy ORM

### Findings

**Strengths:**
1. Well-designed pluggable architecture for future ML model integration
2. Excellent test coverage with 73 tests including edge cases
3. Clean integration with existing event pipeline (Step 16)
4. Proper database migration with reversible downgrade

**Minor Observations (Non-blocking):**
1. `DeterministicMockClassifier` uses RMS for detection - useful for testing but documented as test-only
2. Audio enrichment is fire-and-forget which is good for performance but errors are logged only
3. The `other` event type was added beyond the AC requirements - this is fine as it provides extensibility

**Technical Debt:** None identified

### Test Results

```
73 passed, 33 warnings in 0.34s
- test_audio_event_detector.py: 35 tests
- test_audio_event_handler.py: 14 tests
- test_audio_api.py: 13 tests
- test_alert_engine_audio.py: 11 tests
```

### Recommendation

**APPROVED FOR MERGE** - All acceptance criteria met with comprehensive test coverage. Implementation follows existing patterns and integrates cleanly with the event pipeline.

## Change Log

- 2025-12-17: Story drafted (P6-3.2)
- 2025-12-17: Story implementation complete - all tasks done, 73 tests passing
- 2025-12-17: Senior Developer Review - APPROVED
