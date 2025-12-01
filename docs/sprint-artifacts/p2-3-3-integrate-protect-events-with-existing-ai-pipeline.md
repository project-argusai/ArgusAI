# Story P2-3.3: Integrate Protect Events with Existing AI Pipeline

Status: done

## Story

As a **backend service**,
I want **Protect events to flow through the same AI pipeline as RTSP events**,
So that **all events receive AI descriptions consistently**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| AC1 | Given a snapshot has been retrieved from Protect, when the event handler submits it for AI analysis, then the existing AI service processes it using configured providers | Integration test |
| AC2 | AI submission uses existing `AIService.generate_description()` method with base64-encoded image | Unit test |
| AC3 | AI submission includes context: camera name, event type (person/vehicle/package/animal/motion) | Unit test |
| AC4 | AI provider fallback chain works: OpenAI → Claude → Gemini (existing behavior) | Integration test |
| AC5 | Event record is created in `events` table with `source_type: 'protect'` | Unit test |
| AC6 | Event record includes `protect_event_id` (Protect's native event ID) | Unit test |
| AC7 | Event record includes `smart_detection_type` (person/vehicle/package/animal/motion) | Unit test |
| AC8 | Event stores AI description, confidence, objects_detected from AIResult | Unit test |
| AC9 | Event stores thumbnail_path from SnapshotResult | Unit test |
| AC10 | End-to-end latency from Protect detection to stored event is tracked (NFR2: <2 seconds target) | Performance test |
| AC11 | Processing time is logged as `processing_time_ms` | Unit test |
| AC12 | WebSocket broadcasts `EVENT_CREATED` to frontend with all event details | Integration test |
| AC13 | Existing RTSP/USB event flow remains unaffected | Regression test |

## Tasks / Subtasks

- [x] **Task 1: Extend Event model for Protect source** (AC: 5, 6, 7)
  - [x] 1.1 Add `source_type` column to Event model (TEXT DEFAULT 'rtsp', values: 'rtsp', 'usb', 'protect')
  - [x] 1.2 Add `protect_event_id` column (TEXT NULL, Protect's native event ID)
  - [x] 1.3 Add `smart_detection_type` column (TEXT NULL, values: person/vehicle/package/animal/motion)
  - [x] 1.4 Create Alembic migration for schema changes
  - [x] 1.5 Update EventCreate/EventResponse Pydantic schemas

- [x] **Task 2: Create Protect event submission service** (AC: 1, 2, 3, 10, 11)
  - [x] 2.1 Create `_submit_to_ai_pipeline()` method in `protect_event_handler.py`
  - [x] 2.2 Accept SnapshotResult, Camera, and event_type parameters
  - [x] 2.3 Load AI service with `get_ai_service()` and ensure API keys loaded
  - [x] 2.4 Call `AIService.generate_description()` with base64 image from SnapshotResult
  - [x] 2.5 Pass context: camera.name, timestamp, detected_objects=[event_type]
  - [x] 2.6 Track processing time from snapshot retrieval to AI result
  - [x] 2.7 Return AIResult for event creation

- [x] **Task 3: Implement event storage for Protect events** (AC: 5, 6, 7, 8, 9)
  - [x] 3.1 Create `_store_protect_event()` method in `protect_event_handler.py`
  - [x] 3.2 Accept AIResult, SnapshotResult, Camera, event_type, protect_event_id
  - [x] 3.3 Create Event record with source_type='protect'
  - [x] 3.4 Set protect_event_id from Protect WebSocket message
  - [x] 3.5 Set smart_detection_type from event_type
  - [x] 3.6 Store description, confidence, objects_detected from AIResult
  - [x] 3.7 Store thumbnail_path from SnapshotResult
  - [x] 3.8 Commit to database and return Event

- [x] **Task 4: Wire full pipeline in event handler** (AC: 1, 10, 12)
  - [x] 4.1 Replace TODO comment in `handle_event()` with AI pipeline call
  - [x] 4.2 After snapshot retrieval, call `_submit_to_ai_pipeline()`
  - [x] 4.3 If AI succeeds, call `_store_protect_event()`
  - [x] 4.4 Track total processing_time_ms from event received to stored
  - [x] 4.5 Log processing time and compare to NFR2 (2 second target)

- [x] **Task 5: Implement WebSocket broadcast** (AC: 12)
  - [x] 5.1 Import WebSocket manager from existing `websocket_manager.py`
  - [x] 5.2 After event stored, broadcast `EVENT_CREATED` message
  - [x] 5.3 Include full event details: id, camera_id, timestamp, description, thumbnail_path, source_type, smart_detection_type
  - [x] 5.4 Use existing broadcast format for consistency with RTSP events

- [x] **Task 6: Testing** (AC: all)
  - [x] 6.1 Unit tests for Event model new columns
  - [x] 6.2 Unit tests for `_submit_to_ai_pipeline()` with mock AIService
  - [x] 6.3 Unit tests for `_store_protect_event()` with database
  - [x] 6.4 Integration test for full pipeline: event → snapshot → AI → stored event
  - [x] 6.5 Performance test verifying <2 second end-to-end latency
  - [x] 6.6 Regression test: RTSP events still work (existing tests pass)
  - [x] 6.7 Unit test for WebSocket broadcast on event creation

## Dev Notes

### Architecture Patterns

**Full Protect Event Pipeline:**
```
Protect WebSocket Event (Story P2-3.1)
        ↓
ProtectEventHandler.handle_event()
        ↓
1. Parse event, look up camera, check filters (P2-3.1)
        ↓
2. SnapshotService.get_snapshot() → SnapshotResult (P2-3.2)
        ↓
3. _submit_to_ai_pipeline(SnapshotResult, camera, event_type) [NEW]
        ↓
4. AIService.generate_description(image_base64, camera_name, ...) → AIResult
        ↓
5. _store_protect_event(AIResult, SnapshotResult, ...) → Event [NEW]
        ↓
6. WebSocket broadcast EVENT_CREATED [NEW]
```

**Event Model Extensions:**
```python
# New columns in Event model
source_type: str = Column(Text, default='rtsp')  # 'rtsp', 'usb', 'protect'
protect_event_id: str = Column(Text, nullable=True)  # Protect's native event ID
smart_detection_type: str = Column(Text, nullable=True)  # person/vehicle/package/animal/motion
```

### Learnings from Previous Story

**From Story P2-3.2 (Status: done)**

- **SnapshotService** created at `backend/app/services/snapshot_service.py` - use `get_snapshot_service()` singleton
- **SnapshotResult** dataclass holds: `image_base64`, `thumbnail_path`, `width`, `height`, `camera_id`, `timestamp`
- **Integration Point**: `_retrieve_snapshot()` method in `protect_event_handler.py` (lines 431-501) returns `SnapshotResult`
- **TODO Comment**: Line 211-213 has placeholder for AI pipeline integration
- **Lazy imports**: Used to avoid circular imports - follow same pattern if needed
- **Tests**: 173 tests in `test_protect.py` - follow mock patterns

**Key Interfaces to REUSE (not recreate):**
- `SnapshotResult.image_base64` - Base64-encoded JPEG ready for AI
- `SnapshotResult.thumbnail_path` - Path to stored thumbnail
- `AIService.generate_description()` - Existing AI pipeline with fallback
- `AIResult` dataclass - Has description, confidence, objects_detected, provider info

[Source: docs/sprint-artifacts/p2-3-2-implement-snapshot-retrieval-from-protect-api.md#Completion-Notes-List]

### Project Structure Notes

**Files to Modify:**
- `backend/app/models/event.py` - Add source_type, protect_event_id, smart_detection_type columns
- `backend/app/schemas/event.py` - Update Pydantic schemas for new fields
- `backend/app/services/protect_event_handler.py` - Add AI pipeline and event storage methods
- `backend/tests/test_api/test_protect.py` - Add integration tests

**New Alembic Migration Required:**
- Add `source_type`, `protect_event_id`, `smart_detection_type` columns to events table

**Dependencies (already installed):**
- AIService from `app/services/ai_service.py`
- WebSocket manager from `app/core/websocket_manager.py` (if exists) or create broadcast helper

### Testing Standards

- Follow existing pytest patterns in `tests/test_api/test_protect.py`
- Use `@pytest.mark.asyncio` for async tests
- Mock AIService responses to avoid actual API calls
- Test database operations with test database session
- Verify existing RTSP tests still pass (regression)

### References

- [Source: docs/epics-phase2.md#Story-3.3] - Full acceptance criteria
- [Source: docs/architecture.md#Phase-2-Additions] - Event processing pipeline
- [Source: docs/PRD-phase2.md#FR19-FR20] - AI submission and event storage requirements
- [Source: backend/app/services/ai_service.py#AIService] - Existing AI service with generate_description()
- [Source: backend/app/services/event_processor.py] - Existing event pipeline patterns
- [Source: backend/app/services/protect_event_handler.py#_retrieve_snapshot] - Integration point from P2-3.2

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/stories/p2-3-3-integrate-protect-events-with-existing-ai-pipeline.context.xml`

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-01 | Story drafted from epics-phase2.md | SM Agent |
| 2025-12-01 | Story context assembled and validated | Story Context Workflow |
