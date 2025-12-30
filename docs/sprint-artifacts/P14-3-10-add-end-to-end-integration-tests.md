# Story P14-3.10: Add End-to-End Integration Tests

Status: drafted

## Story

As a **developer**,
I want integration tests for complete flows,
So that component interactions are verified.

## Acceptance Criteria

1. Event processing pipeline E2E tests exist covering:
   - Camera event creation through AI description to database storage
   - WebSocket notifications are sent when events are processed
2. Alert flow E2E tests exist covering:
   - Event triggers alert rule matching
   - Webhook dispatch on rule match
   - Notification creation
3. Entity recognition E2E tests exist covering:
   - Event processing triggers entity matching
   - Entity updates are persisted correctly
4. Multi-camera event correlation tests exist
5. All E2E tests are marked with `@pytest.mark.e2e` for selective execution
6. Tests use mock services for AI providers and external webhooks

## Tasks / Subtasks

- [ ] Task 1: Create E2E test infrastructure (AC: 5, 6)
  - [ ] Create `backend/tests/test_e2e/` directory structure
  - [ ] Create `conftest.py` with E2E fixtures (mock AI, mock webhooks)
  - [ ] Configure pytest markers for E2E tests
  - [ ] Add E2E test dependencies if needed

- [ ] Task 2: Implement event pipeline E2E tests (AC: 1)
  - [ ] Create `test_event_pipeline.py`
  - [ ] Test: Protect event to AI description flow
  - [ ] Test: RTSP camera event to database storage
  - [ ] Test: WebSocket notification on event creation

- [ ] Task 3: Implement alert flow E2E tests (AC: 2)
  - [ ] Create `test_alert_flow.py`
  - [ ] Test: Event triggers alert rule matching
  - [ ] Test: Webhook dispatch with mock server
  - [ ] Test: Notification creation on alert

- [ ] Task 4: Implement entity recognition E2E tests (AC: 3)
  - [ ] Create `test_entity_flow.py`
  - [ ] Test: Event triggers entity matching
  - [ ] Test: Entity updates on match
  - [ ] Test: Unknown entity handling

- [ ] Task 5: Implement multi-camera correlation tests (AC: 4)
  - [ ] Create `test_correlation.py`
  - [ ] Test: Events from multiple cameras in time window
  - [ ] Test: Correlation group creation

- [ ] Task 6: Run and validate all E2E tests
  - [ ] Run full test suite
  - [ ] Verify no regressions

## Dev Notes

- Use FastAPI TestClient for HTTP testing
- Use SQLite in-memory for fast test execution
- Mock external services: AI providers, webhooks, Protect API
- E2E tests should cover critical user journeys end-to-end
- Consider test execution time - E2E tests can be slow

### Project Structure Notes

- Tests location: `backend/tests/test_e2e/`
- Follow existing test patterns from `test_api/` and `test_services/`
- Use existing fixtures from `conftest.py` where applicable

### References

- [Source: docs/epics-phase14.md#Story-P14-3.10]
- [Source: docs/sprint-artifacts/tech-spec-epic-P14-3.md#Story-P14-3.10]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

### File List
