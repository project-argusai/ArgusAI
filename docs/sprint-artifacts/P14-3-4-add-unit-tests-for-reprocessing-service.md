# Story P14-3.4: Add Unit Tests for reprocessing_service.py

Status: drafted

## Story

As a **developer**,
I want comprehensive unit tests for the ReprocessingService,
so that background job handling, progress tracking, and entity reprocessing are regression-tested.

## Acceptance Criteria

1. **AC-1**: Test file `tests/test_services/test_reprocessing_service.py` exists with 15+ tests
2. **AC-2**: Line coverage for `reprocessing_service.py` reaches minimum 70%
3. **AC-3**: `ReprocessingJob` dataclass tested for initialization and `to_dict()` serialization
4. **AC-4**: `ReprocessingStatus` enum tested for all status values (PENDING, RUNNING, COMPLETED, CANCELLED, FAILED)
5. **AC-5**: `estimate_event_count()` tested with various filter combinations
6. **AC-6**: `start_reprocessing()` tested for success, duplicate job rejection, and zero events case
7. **AC-7**: `cancel_reprocessing()` tested for cancellation during processing
8. **AC-8**: `_process_events()` tested for batch processing, progress updates, and error handling
9. **AC-9**: WebSocket progress broadcasts verified (`_broadcast_progress` and `_broadcast_completion`)
10. **AC-10**: All tests use mocked dependencies (WebSocketManager, EmbeddingService, EntityService, database)

## Tasks / Subtasks

- [ ] Task 1: Set up test file structure (AC: 1, 10)
  - [ ] 1.1: Create `backend/tests/test_services/test_reprocessing_service.py`
  - [ ] 1.2: Add pytest-asyncio imports and test class structure
  - [ ] 1.3: Create mock fixtures for WebSocketManager, EmbeddingService, EntityService
  - [ ] 1.4: Create database fixture with Event, EntityEvent models

- [ ] Task 2: Implement ReprocessingStatus tests (AC: 4)
  - [ ] 2.1: `test_reprocessing_status_values` - Verify all enum values
  - [ ] 2.2: `test_reprocessing_status_string_values` - Verify string representations

- [ ] Task 3: Implement ReprocessingJob tests (AC: 3)
  - [ ] 3.1: `test_reprocessing_job_initialization` - Default values and required fields
  - [ ] 3.2: `test_reprocessing_job_to_dict` - Full serialization
  - [ ] 3.3: `test_reprocessing_job_to_dict_with_dates` - Date serialization
  - [ ] 3.4: `test_reprocessing_job_percent_complete_zero_events` - Edge case handling

- [ ] Task 4: Implement ReprocessingService initialization tests (AC: 1)
  - [ ] 4.1: `test_reprocessing_service_init` - Instance creation
  - [ ] 4.2: `test_get_reprocessing_service_singleton` - Returns same instance
  - [ ] 4.3: `test_is_running_property` - False when no job, True when running

- [ ] Task 5: Implement estimate_event_count tests (AC: 5, 10)
  - [ ] 5.1: `test_estimate_event_count_all_events` - No filters
  - [ ] 5.2: `test_estimate_event_count_date_range` - Start/end date filters
  - [ ] 5.3: `test_estimate_event_count_camera_filter` - Camera ID filter
  - [ ] 5.4: `test_estimate_event_count_only_unmatched` - Exclude already matched
  - [ ] 5.5: `test_estimate_event_count_requires_thumbnail` - Events without thumbnails excluded

- [ ] Task 6: Implement start_reprocessing tests (AC: 6, 10)
  - [ ] 6.1: `test_start_reprocessing_success` - Job created and returned
  - [ ] 6.2: `test_start_reprocessing_job_already_running` - Raises ValueError
  - [ ] 6.3: `test_start_reprocessing_no_events` - Raises ValueError when zero events
  - [ ] 6.4: `test_start_reprocessing_creates_task` - Background task started
  - [ ] 6.5: `test_start_reprocessing_sets_job_filters` - Filters stored in job

- [ ] Task 7: Implement cancel_reprocessing tests (AC: 7)
  - [ ] 7.1: `test_cancel_reprocessing_no_job` - Returns None when no job
  - [ ] 7.2: `test_cancel_reprocessing_sets_flag` - Sets cancel_requested = True
  - [ ] 7.3: `test_cancel_reprocessing_waits_for_task` - Waits with timeout
  - [ ] 7.4: `test_cancel_reprocessing_returns_job` - Returns cancelled job

- [ ] Task 8: Implement _process_events tests (AC: 8, 10)
  - [ ] 8.1: `test_process_events_success_flow` - Complete processing
  - [ ] 8.2: `test_process_events_respects_batch_size` - Processes in batches of 100
  - [ ] 8.3: `test_process_events_cancellation` - Stops on cancel_requested
  - [ ] 8.4: `test_process_events_handles_errors` - Continues after event error
  - [ ] 8.5: `test_process_events_updates_job_stats` - Processed/matched/errors counts

- [ ] Task 9: Implement _process_single_event tests (AC: 8, 10)
  - [ ] 9.1: `test_process_single_event_with_existing_embedding` - Uses cached embedding
  - [ ] 9.2: `test_process_single_event_generates_embedding` - Creates new embedding
  - [ ] 9.3: `test_process_single_event_entity_matching` - Links to entity
  - [ ] 9.4: `test_process_single_event_vehicle_detection` - Uses vehicle matching
  - [ ] 9.5: `test_process_single_event_no_thumbnail` - Returns early

- [ ] Task 10: Implement WebSocket broadcast tests (AC: 9)
  - [ ] 10.1: `test_broadcast_progress_format` - Correct message structure
  - [ ] 10.2: `test_broadcast_progress_timing` - Respects PROGRESS_UPDATE_INTERVAL
  - [ ] 10.3: `test_broadcast_completion_on_success` - Completion message sent
  - [ ] 10.4: `test_broadcast_completion_on_cancel` - Completion message on cancel
  - [ ] 10.5: `test_broadcast_completion_on_failure` - Completion message on error

- [ ] Task 11: Implement get_status tests (AC: 1)
  - [ ] 11.1: `test_get_status_no_job` - Returns None
  - [ ] 11.2: `test_get_status_with_job` - Returns current job

- [ ] Task 12: Run coverage and verify (AC: 2)
  - [ ] 12.1: Run `pytest tests/test_services/test_reprocessing_service.py --cov=app/services/reprocessing_service --cov-report=term-missing`
  - [ ] 12.2: Verify 70%+ line coverage achieved
  - [ ] 12.3: Add any missing tests for uncovered lines

## Dev Notes

### Architecture and Patterns

The `ReprocessingService` class (~570 lines) is a singleton service that manages:
1. **Job Lifecycle**: `start_reprocessing()`, `cancel_reprocessing()`, `get_status()`
2. **Event Processing**: `_process_events()` background task with batch processing
3. **Entity Matching**: `_process_single_event()` generates embeddings and matches entities
4. **Progress Updates**: WebSocket broadcasts for progress and completion
5. **Concurrency Control**: Single job at a time via `_lock` and `is_running` property

### Key Constants to Test

```python
BATCH_SIZE = 100
PROGRESS_UPDATE_INTERVAL = 1.0  # seconds
```

### ReprocessingStatus Enum Values

```python
PENDING = "pending"
RUNNING = "running"
COMPLETED = "completed"
CANCELLED = "cancelled"
FAILED = "failed"
```

### Mock Dependencies

- **WebSocketManager**: Mock `broadcast()` method
- **EmbeddingService**: Mock `generate_embedding_from_file()` and `store_embedding()`
- **EntityService**: Mock `match_or_create_entity()` and `match_or_create_vehicle_entity()`
- **Database Session**: Use test database with Event, EntityEvent fixtures

### Learnings from Previous Story

**From Story P14-3.3 (snapshot_service.py tests):**

- Created 59 tests with 87% coverage (exceeds 80% target)
- Used `@pytest.mark.asyncio` for all async methods
- Organized tests into logical test classes by functionality
- Used parametrization for input variations
- Used temp directories and mock fixtures for isolation

### Project Structure Notes

- Test file goes in: `backend/tests/test_services/test_reprocessing_service.py`
- Follows existing pattern in `test_snapshot_service.py`
- Uses conftest.py fixtures for database session

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P14-3.md#Story-P14-3.4]
- [Source: docs/epics-phase14.md#Story-P14-3.4]
- [Source: backend/app/services/reprocessing_service.py] - Target service (~570 lines)
- [Source: docs/sprint-artifacts/P14-3-3-add-unit-tests-for-snapshot-service.md] - Previous story patterns

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
