# Story P2-3.1: Implement Protect Event Listener and Event Handler

Status: done

## Story

As a **backend service**,
I want **to receive and process real-time events from the Protect WebSocket**,
So that **motion detections trigger AI analysis immediately**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| AC1 | Given a WebSocket connection to Protect is established, when motion or smart detection occurs on an enabled camera, then the system receives the event within 1 second | Integration test |
| AC2 | Event handler identifies event type: motion, smart_detect_person, smart_detect_vehicle, smart_detect_package, smart_detect_animal, ring (doorbell) | Unit test |
| AC3 | Event handler looks up camera by `protect_camera_id` and checks if enabled for AI analysis | Unit test |
| AC4 | If camera not enabled, event is discarded silently (no error, no processing) | Unit test |
| AC5 | Event filtering loads camera's `smart_detection_types` configuration | Unit test |
| AC6 | If event type matches configured types, event proceeds to next stage | Unit test |
| AC7 | If event type not in configured types, event is discarded silently | Unit test |
| AC8 | "All Motion" configuration (empty array or `["motion"]`) processes all event types | Unit test |
| AC9 | Event deduplication tracks last event time per camera | Unit test |
| AC10 | Cooldown logic (default 60 seconds) prevents duplicate events | Unit test |
| AC11 | All events logged with camera name, event type, timestamp (no PII/credentials) | Log inspection |
| AC12 | Filter decisions logged (passed/filtered with reason) | Log inspection |

## Tasks / Subtasks

- [x] **Task 1: Create ProtectEventHandler service** (AC: 2, 3, 4, 11)
  - [x] 1.1 Create `backend/app/services/protect_event_handler.py`
  - [x] 1.2 Define `ProtectEventHandler` class with initialization
  - [x] 1.3 Implement `handle_event(controller_id: str, event: WSMessage)` method
  - [x] 1.4 Parse event type from uiprotect WSMessage (motion, smart_detect_*, ring)
  - [x] 1.5 Look up camera record by `protect_camera_id` from database
  - [x] 1.6 Check `camera.is_enabled` and `camera.source_type == 'protect'`
  - [x] 1.7 Return early if camera not enabled (log debug message)

- [x] **Task 2: Implement event filtering logic** (AC: 5, 6, 7, 8)
  - [x] 2.1 Load `smart_detection_types` from camera record (JSON array)
  - [x] 2.2 Implement `_should_process_event(event_type: str, filters: List[str]) -> bool`
  - [x] 2.3 Handle "motion" or empty array as "all motion" mode
  - [x] 2.4 Map Protect event types to filter types (smart_detect_person → person)
  - [x] 2.5 Return False if event type not in filters (log filtered reason)

- [x] **Task 3: Implement event deduplication** (AC: 9, 10)
  - [x] 3.1 Create `_last_event_times: Dict[str, datetime]` tracking dictionary
  - [x] 3.2 Implement `_is_duplicate_event(camera_id: str) -> bool`
  - [x] 3.3 Use configurable cooldown period (default 60 seconds from settings)
  - [x] 3.4 Update last event time when event passes deduplication
  - [x] 3.5 Log when event is skipped due to cooldown

- [x] **Task 4: Wire handler to WebSocket listener** (AC: 1)
  - [x] 4.1 Update `protect_service.py` `_websocket_listener()` to call handler
  - [x] 4.2 Pass event to `ProtectEventHandler.handle_event()`
  - [x] 4.3 Ensure async execution doesn't block WebSocket loop
  - [x] 4.4 Handle exceptions gracefully (log and continue)

- [x] **Task 5: Add structured logging** (AC: 11, 12)
  - [x] 5.1 Log event received: camera name, event type, timestamp
  - [x] 5.2 Log filter decision: passed/filtered with reason
  - [x] 5.3 Log deduplication decision: processed/skipped with time since last
  - [x] 5.4 Ensure no PII or credentials in logs

- [x] **Task 6: Testing** (AC: all)
  - [x] 6.1 Unit tests for event type parsing
  - [x] 6.2 Unit tests for filter logic (various combinations)
  - [x] 6.3 Unit tests for deduplication logic
  - [x] 6.4 Unit tests for "all motion" mode
  - [x] 6.5 Integration test for full event flow

## Dev Notes

### Architecture Patterns

**Event Handler Flow:**
```
uiprotect WebSocket Event
        ↓
ProtectEventHandler.handle_event()
        ↓
1. Parse event type (motion, smart_detect_*, ring)
        ↓
2. Look up camera by protect_camera_id
        ↓
3. Check camera.is_enabled
        ↓ (if not enabled → discard)
4. Load smart_detection_types filter
        ↓
5. Check event type matches filter
        ↓ (if not matching → discard)
6. Check deduplication cooldown
        ↓ (if duplicate → discard)
7. Pass to next stage (snapshot retrieval - Story P2-3.2)
```

**Event Type Mapping:**
| Protect Event | Filter Type |
|---------------|-------------|
| `motion` | `motion` |
| `smart_detect_person` | `person` |
| `smart_detect_vehicle` | `vehicle` |
| `smart_detect_package` | `package` |
| `smart_detect_animal` | `animal` |
| `ring` | `ring` (doorbell) |

**uiprotect Event Structure:**
```python
# WSMessage from uiprotect
event.action  # WSAction.ADD or WSAction.UPDATE
event.new_obj  # The camera/event object
event.new_obj.id  # Camera ID
event.new_obj.is_connected  # For status changes

# Smart detection events come via:
event.new_obj.smart_detect_types  # List of detected types
event.new_obj.is_motion_detected  # Boolean for motion
```

### Learnings from Previous Story

**From Story P2-2.4 (Status: done)**

- **WebSocket Infrastructure**: Camera status handling already implemented in `protect_service.py:903-1063`
  - `_handle_websocket_event()` method exists - extend for motion events
  - `CAMERA_STATUS_CHANGED` constant pattern - add similar for events
- **Debounce Pattern**: `_should_broadcast_camera_status()` demonstrates debounce logic at `protect_service.py:1020-1040`
- **TanStack Query Cache Updates**: Frontend pattern for optimistic updates established
- **Database Query Pattern**: Camera lookup by `protect_camera_id` already implemented

**Key Files to Reuse/Extend:**
- `backend/app/services/protect_service.py` - Add motion event handling alongside status handling
- `backend/app/models/camera.py` - Camera model with `smart_detection_types` field
- `backend/tests/test_api/test_protect.py` - Follow existing test patterns (104 tests pass)

**Interfaces Created in Previous Stories:**
- `ProtectService._handle_websocket_event(controller_id, msg)` - Hook point for events
- `ProtectService._connections` dict - Active controller connections
- `Camera.smart_detection_types` - JSON field for filter configuration

[Source: docs/sprint-artifacts/p2-2-4-add-camera-status-sync-and-refresh-functionality.md#Completion-Notes-List]

### Project Structure Notes

**New File:**
- `backend/app/services/protect_event_handler.py` - New event handler service

**Files to Modify:**
- `backend/app/services/protect_service.py` - Wire handler to WebSocket listener
- `backend/tests/test_api/test_protect.py` - Add event handler tests

### Testing Standards

- Follow existing pytest patterns in `tests/test_api/test_protect.py`
- Use `@pytest.mark.asyncio` for async tests
- Mock uiprotect WebSocket messages
- Test all filter combinations (person only, all motion, mixed, etc.)
- Test deduplication with time mocking

### References

- [Source: docs/epics-phase2.md#Story-3.1] - Full acceptance criteria
- [Source: docs/architecture.md#Phase-2-Additions] - WebSocket architecture
- [Source: docs/PRD-phase2.md#FR16-FR17] - Event reception and filtering requirements
- [Source: backend/app/services/protect_service.py#_handle_websocket_event] - Existing event handling pattern

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p2-3-1-implement-protect-event-listener-and-event-handler.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

None

### Completion Notes List

**Story P2-3.1 Implementation Complete**

All 12 acceptance criteria implemented and verified:

1. **AC1 (Event Reception)**: WebSocket listener in `protect_service.py` calls `ProtectEventHandler.handle_event()` via `asyncio.create_task()` for non-blocking execution
2. **AC2 (Event Type Identification)**: `_parse_event_types()` parses motion, smart_detect_person, smart_detect_vehicle, smart_detect_package, smart_detect_animal, and ring events
3. **AC3 (Camera Lookup)**: `_get_camera_by_protect_id()` looks up camera by protect_camera_id and checks is_enabled
4. **AC4 (Disabled Camera Discard)**: Events from disabled cameras or non-protect source_type are discarded with debug logging
5. **AC5 (Filter Loading)**: `_load_smart_detection_types()` parses JSON array from camera.smart_detection_types
6. **AC6 (Filter Match)**: `_should_process_event()` returns True when event type matches configured filters
7. **AC7 (Filter Mismatch)**: Events not matching configured filters are discarded with debug logging
8. **AC8 (All Motion Mode)**: Empty array or ["motion"] configuration processes all event types
9. **AC9 (Deduplication Tracking)**: `_last_event_times` dict tracks last event timestamp per camera
10. **AC10 (Cooldown Logic)**: `_is_duplicate_event()` enforces 60-second cooldown per camera
11. **AC11 (Event Logging)**: Structured logging with camera name, event type, timestamp (no PII)
12. **AC12 (Filter Decision Logging)**: Filter decisions logged with passed/filtered reason

**Test Coverage**: 41 new unit tests added to `tests/test_api/test_protect.py` - all 145 tests pass

### File List

**Backend Created:**
- `backend/app/services/protect_event_handler.py` - New ProtectEventHandler service with event parsing, filtering, and deduplication

**Backend Modified:**
- `backend/app/services/protect_service.py` - Added import and wired handler to WebSocket listener (lines 24, 597-601)
- `backend/tests/test_api/test_protect.py` - Added 41 tests for Story P2-3.1 (lines 2208-2908)

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-01 | Story drafted from epics-phase2.md | SM Agent |
| 2025-12-01 | Story context generated, status -> ready-for-dev | SM Agent |
| 2025-12-01 | Story implemented, all ACs met, 145 tests pass, status -> done | Dev Agent |
