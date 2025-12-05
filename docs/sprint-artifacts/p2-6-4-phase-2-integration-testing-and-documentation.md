# Story P2-6.4: Phase 2 Integration Testing and Documentation

Status: ready-for-dev

## Story

As a **developer and user**,
I want **comprehensive testing and documentation for Phase 2 features**,
so that **the release is production-ready and users can self-serve**.

## Acceptance Criteria

1. **AC1**: Integration tests cover controller connection lifecycle (connect, reconnect, disconnect)
2. **AC2**: Integration tests cover camera discovery and enable/disable
3. **AC3**: Integration tests cover event flow from Protect to dashboard
4. **AC4**: Integration tests cover doorbell ring detection and display
5. **AC5**: Integration tests cover multi-camera correlation
6. **AC6**: Integration tests cover Grok provider configuration and fallback
7. **AC7**: Integration tests cover RTSP/Protect coexistence
8. **AC8**: Performance test: Camera discovery < 10 seconds (NFR1)
9. **AC9**: Performance test: Event latency < 2 seconds (NFR2)
10. **AC10**: Performance test: WebSocket reconnect < 5 seconds (NFR3)
11. **AC11**: Performance test: Snapshot retrieval < 1 second (NFR4)
12. **AC12**: README updated with Phase 2 features
13. **AC13**: CLAUDE.md updated with new endpoints and services
14. **AC14**: Settings page help text for UniFi Protect section
15. **AC15**: Troubleshooting guide for common Protect issues
16. **AC16**: Release checklist: All acceptance criteria verified
17. **AC17**: Release checklist: No critical bugs
18. **AC18**: Release checklist: Performance targets met
19. **AC19**: Release checklist: Documentation complete

## Tasks / Subtasks

- [ ] **Task 1: Create Integration Test Suite** (AC: 1-7)
  - [ ] 1.1 Create `tests/integration/test_protect_controller.py` - Controller lifecycle tests
  - [ ] 1.2 Create `tests/integration/test_protect_cameras.py` - Camera discovery and enable/disable
  - [ ] 1.3 Create `tests/integration/test_protect_events.py` - Event flow from Protect to dashboard
  - [ ] 1.4 Create `tests/integration/test_doorbell.py` - Doorbell ring detection tests
  - [ ] 1.5 Create `tests/integration/test_correlation.py` - Multi-camera correlation tests
  - [ ] 1.6 Create `tests/integration/test_grok_provider.py` - Grok configuration and fallback
  - [ ] 1.7 Create `tests/integration/test_coexistence.py` - RTSP/Protect coexistence

- [ ] **Task 2: Create Performance Test Suite** (AC: 8-11)
  - [ ] 2.1 Create `tests/performance/test_nfr_performance.py` - All NFR performance tests
  - [ ] 2.2 Test camera discovery timing (< 10 seconds)
  - [ ] 2.3 Test event processing latency (< 2 seconds)
  - [ ] 2.4 Test WebSocket reconnect timing (< 5 seconds)
  - [ ] 2.5 Test snapshot retrieval timing (< 1 second)

- [ ] **Task 3: Update README Documentation** (AC: 12)
  - [ ] 3.1 Add UniFi Protect Integration section
  - [ ] 3.2 Add xAI Grok provider section
  - [ ] 3.3 Update feature list with Phase 2 capabilities
  - [ ] 3.4 Add setup instructions for Protect controller

- [ ] **Task 4: Update CLAUDE.md** (AC: 13)
  - [ ] 4.1 Add Phase 2 API endpoints documentation
  - [ ] 4.2 Add new services documentation (ProtectService, ProtectEventListener)
  - [ ] 4.3 Update architecture section with Phase 2 components
  - [ ] 4.4 Add new database models (protect_controller, event.description_retry_needed)

- [ ] **Task 5: Add Settings Page Help Text** (AC: 14)
  - [ ] 5.1 Add tooltips/help text for UniFi Protect configuration fields
  - [ ] 5.2 Add contextual help for camera event type filtering
  - [ ] 5.3 Add help text for Grok provider configuration

- [ ] **Task 6: Create Troubleshooting Guide** (AC: 15)
  - [ ] 6.1 Create `docs/troubleshooting-protect.md`
  - [ ] 6.2 Document common connection issues and solutions
  - [ ] 6.3 Document camera discovery issues
  - [ ] 6.4 Document WebSocket connection issues

- [ ] **Task 7: Release Verification** (AC: 16-19)
  - [ ] 7.1 Run full integration test suite and document results
  - [ ] 7.2 Run performance test suite and verify NFR targets
  - [ ] 7.3 Verify no critical bugs in bug tracker / test results
  - [ ] 7.4 Complete documentation checklist verification

## Dev Notes

### Technical Context

**Testing Framework:**
- Backend: pytest with pytest-asyncio for async tests
- Integration tests in `tests/integration/`
- Performance tests in `tests/performance/`
- Existing test patterns in `tests/test_api/` and `tests/test_services/`

**Documentation Locations:**
- README.md at project root
- CLAUDE.md at project root
- docs/ folder for detailed documentation

**Phase 2 Components to Test:**
- `/api/v1/protect/*` endpoints
- `ProtectService` in `backend/app/services/protect_service.py`
- `ProtectEventListener` in `backend/app/services/protect_event_listener.py`
- WebSocket manager with auto-reconnect
- Event correlation service
- Grok AI provider

### Learnings from Previous Story

**From Story p2-6-3-implement-phase-2-error-handling-and-edge-cases (Status: done)**

- **New Components Created**:
  - `frontend/components/protect/ConnectionErrorBanner.tsx` - Reuse for error state testing
  - `frontend/components/common/ErrorBoundary.tsx` - React error boundary
  - `frontend/lib/hooks/useWebSocketWithNotifications.ts` - WebSocket toast notifications

- **Database Changes**:
  - Migration 016: `description_retry_needed` column added to events table
  - Event model updated with retry flag for AI failures

- **Error Handling Patterns Established**:
  - Yellow banners for recoverable errors (AC1-4 patterns)
  - Red banners for user action required
  - Toast notifications via sonner library
  - WebSocket reconnect with exponential backoff (1s → 2s → 4s → 8s → 16s → 30s cap)

- **Testing Considerations**:
  - 545 backend tests passed in p2-6-3
  - Frontend TypeScript build verified
  - Test coverage for error scenarios deferred (7 test subtasks)

[Source: docs/sprint-artifacts/p2-6-3-implement-phase-2-error-handling-and-edge-cases.md#Dev-Agent-Record]

### Project Structure Notes

**Test Directory Structure:**
```
tests/
├── integration/           # New for this story
│   ├── test_protect_controller.py
│   ├── test_protect_cameras.py
│   ├── test_protect_events.py
│   ├── test_doorbell.py
│   ├── test_correlation.py
│   ├── test_grok_provider.py
│   └── test_coexistence.py
├── performance/           # New for this story
│   └── test_nfr_performance.py
├── test_api/              # Existing API tests
└── test_services/         # Existing service tests
```

### References

- [Source: docs/epics-phase2.md#Story-6.4]
- [Source: docs/PRD-phase2.md#NFR1-NFR4]
- [Source: docs/architecture.md#Testing-Strategy]
- [Source: CLAUDE.md]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p2-6-4-phase-2-integration-testing-and-documentation.context.xml (generated 2025-12-05)

### Agent Model Used

TBD

### Debug Log References

N/A

### Completion Notes List

TBD

### File List

TBD

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-05 | Story drafted from epics-phase2.md | SM Agent |
