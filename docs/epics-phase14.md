# ArgusAI - Epic Breakdown: Phase 14

**Author:** Brent
**Date:** 2025-12-29
**Phase:** 14 - Technical Excellence & Quality Foundation
**Project Level:** Brownfield Enhancement
**Target Scale:** Production Hardening

---

## Overview

This document provides the complete epic and story breakdown for Phase 14, decomposing 60 functional requirements from the [PRD](./PRD-phase14.md) into implementable stories organized across 8 epics.

**Living Document Notice:** This is the initial version focused on technical debt paydown. No UX design phase needed as this is purely backend/infrastructure work.

### Epic Summary

| Epic | Title | Stories | Priority | Effort |
|------|-------|---------|----------|--------|
| P14-1 | Critical Security & Code Fixes | 2 | P1 | 1 day |
| P14-2 | Backend Code Quality | 6 | P2 | 8 days |
| P14-3 | Backend Testing Infrastructure | 10 | P2-P3 | 15 days |
| P14-4 | Frontend Code Quality | 8 | P2-P3 | 5 days |
| P14-5 | Code Standardization | 10 | P3 | 8 days |
| P14-6 | MCP Context System Enhancement | 8 | P2-P3 | 10 days |
| P14-7 | Frontend Enhancements | 6 | P3-P4 | 6 days |
| P14-8 | Testing & Documentation Polish | 3 | P3-P4 | 5 days |

**Total: 53 Stories | ~58 days effort**

---

## Functional Requirements Inventory

### Critical Security (FR1-FR3)
- FR1: MQTT discovery service uses asyncio.create_task() instead of asyncio.run()
- FR2: Debug endpoints removed from production or require admin auth
- FR3: Debug endpoints disabled by default via DEBUG_ENDPOINTS_ENABLED=false

### Backend Code Quality (FR4-FR15)
- FR4: All database sessions use context manager pattern
- FR5: WebhookLog.alert_rule_id has ForeignKey constraint
- FR6: Events table has compound index on (source_type, timestamp)
- FR7: RecognizedEntities.name column has index
- FR8: Devices.pairing_confirmed column has index
- FR9: API keys table has indexes on created_by/revoked_by
- FR10: PairingCodes table has compound index on (device_id, expires_at)
- FR11: DELETE endpoints return 204 No Content
- FR12: All UUID path parameters typed as UUID
- FR13: Invalid UUIDs return 422 with clear error
- FR14: All API endpoints have rate limiting
- FR15: Rate limit exceeded returns 429 with Retry-After

### Backend Testing (FR16-FR25)
- FR16: protect_service.py has comprehensive unit tests
- FR17: protect_event_handler.py has comprehensive unit tests
- FR18: snapshot_service.py has comprehensive unit tests
- FR19: reprocessing_service.py has comprehensive unit tests
- FR20: websocket_manager.py has comprehensive unit tests
- FR21: api_key_service.py has comprehensive unit tests
- FR22: Test parametrization used (target: 50+ tests)
- FR23: Shared test fixtures in global conftest.py
- FR24: End-to-end tests for complete event flow
- FR25: API route tests for security-critical modules

### Frontend Code Quality (FR26-FR33)
- FR26: API client has no console.log in production
- FR27: All test fixtures match TypeScript interfaces
- FR28: TunnelSettings test passes
- FR29: Shared test utilities with complete factories
- FR30: No unused imports in test files
- FR31: No unused imports in component files
- FR32: No setState in useEffect without deps
- FR33: SortIcon defined at module scope

### Code Standardization (FR34-FR43)
- FR34: @singleton decorator exists
- FR35: All 50+ singletons use decorator
- FR36: exponential_backoff() utility exists
- FR37: All 4 backoff implementations use utility
- FR38: All relationships use back_populates
- FR39: Float columns have CheckConstraints
- FR40: DateTime columns use consistent UTC
- FR41: API response format documented/consistent
- FR42: Notification model has relationships
- FR43: JSON errors logged with context

### MCP Context Enhancement (FR44-FR51)
- FR44: EntityAdjustment data in MCP context
- FR45: MCP queries execute in parallel
- FR46: MCP uses async SQLAlchemy or executor
- FR47: MCP has 80ms timeout with fail-open
- FR48: MCP cache optimized (target: >50% hit)
- FR49: Pattern extraction uses TF-IDF
- FR50: VIP/blocked flags in EntityContext
- FR51: Context Metrics tab in Settings

### Frontend Enhancements (FR52-FR57)
- FR52: BackupRestore images have alt text
- FR53: Native img replaced with next/image
- FR54: Stricter TypeScript enabled/documented
- FR55: All 18 hooks have test coverage
- FR56: React Query DevTools available
- FR57: All endpoints have OpenAPI docs

### Testing & Documentation (FR58-FR60)
- FR58: Query params have validation
- FR59: Concurrency tests exist
- FR60: Mocks validate against contracts

---

## FR Coverage Map

| Epic | Functional Requirements Covered |
|------|--------------------------------|
| P14-1 | FR1, FR2, FR3 |
| P14-2 | FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR13, FR14, FR15 |
| P14-3 | FR16, FR17, FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25 |
| P14-4 | FR26, FR27, FR28, FR29, FR30, FR31, FR32, FR33 |
| P14-5 | FR34, FR35, FR36, FR37, FR38, FR39, FR40, FR41, FR42, FR43 |
| P14-6 | FR44, FR45, FR46, FR47, FR48, FR49, FR50, FR51 |
| P14-7 | FR52, FR53, FR54, FR55, FR56, FR57 |
| P14-8 | FR58, FR59, FR60 |

**Coverage: 60/60 FRs mapped (100%)**

---

## Epic P14-1: Critical Security & Code Fixes

**Goal:** Eliminate P1 critical security vulnerabilities and code defects that could cause runtime crashes or credential exposure. This epic MUST be completed before any other Phase 14 work begins.

**Backlog Items:** TD-011, TD-023

### Story P14-1.1: Fix asyncio.run() Misuse in MQTT Service

As a **developer**,
I want the MQTT discovery service to use proper async patterns,
So that the service doesn't crash when called from an existing async context.

**Acceptance Criteria:**

**Given** the MQTT service `_publish_discovery_on_connect` method at line 729
**When** called from an async context (e.g., during startup)
**Then** it uses `asyncio.create_task()` or `asyncio.run_coroutine_threadsafe()` instead of `asyncio.run()`

**And** the fix handles the case where no event loop is running (sync context)
**And** existing MQTT functionality continues to work (publish discovery, reconnect)
**And** unit tests verify both async and sync context behavior

**Prerequisites:** None (First story)

**Technical Notes:**
- File: `backend/app/services/mqtt_discovery_service.py:729`
- Current code: `asyncio.run(self._publish_discovery_on_connect())`
- Fix pattern: Check if loop is running, use `create_task()` if yes, `asyncio.run()` if no
- Alternative: Use `asyncio.run_coroutine_threadsafe()` with explicit loop reference
- Test with: `pytest tests/test_services/test_mqtt_discovery_service.py -v`

---

### Story P14-1.2: Remove or Secure Debug Endpoints

As a **security administrator**,
I want debug endpoints removed or secured,
So that API key structures and internal network information are not exposed.

**Acceptance Criteria:**

**Given** debug endpoints `/debug/ai-keys` and `/debug/network` in `system.py:53-119`
**When** the application runs in production (DEBUG=False or DEBUG_ENDPOINTS_ENABLED=false)
**Then** these endpoints return 404 Not Found (not 401/403 which confirms existence)

**And** a new environment variable `DEBUG_ENDPOINTS_ENABLED` controls endpoint availability
**And** default value is `false` (secure by default)
**And** when enabled, endpoints require admin authentication
**And** OpenAPI documentation excludes these endpoints in production

**Prerequisites:** None (Can run parallel to P14-1.1)

**Technical Notes:**
- File: `backend/app/api/v1/system.py:53-119`
- Options: (1) Delete entirely, (2) Add conditional registration, (3) Add auth + env check
- Recommended: Conditional registration based on `DEBUG_ENDPOINTS_ENABLED` env var
- Use `include_in_schema=False` when disabled to hide from OpenAPI
- Return 404 (not 401/403) to avoid confirming endpoint existence

---

## Epic P14-2: Backend Code Quality

**Goal:** Establish consistent backend code patterns including proper database session management, foreign key constraints, indexes, API standards, and rate limiting. These patterns will be used by subsequent epics.

**Backlog Items:** TD-012, TD-015, TD-016, TD-020, TD-021, TD-024

### Story P14-2.1: Standardize Database Session Management

As a **developer**,
I want all database operations to use context managers,
So that connection leaks are prevented even when exceptions occur.

**Acceptance Criteria:**

**Given** 15+ instances of manual `db = SessionLocal()` → `db.close()` pattern
**When** any exception occurs during database operations
**Then** the session is properly closed via context manager (`with SessionLocal() as db:`)

**And** all instances in `event_processor.py` (15+ occurrences) are converted
**And** all instances in `camera_service.py` are converted
**And** all instances in `protect_event_handler.py` are converted
**And** no manual `.close()` calls remain in service layer code
**And** connection pool monitoring shows no leaked connections under load

**Prerequisites:** P14-1.1, P14-1.2

**Technical Notes:**
- Pattern: Replace `db = SessionLocal(); try: ... finally: db.close()` with `with SessionLocal() as db:`
- Files to update: `event_processor.py`, `camera_service.py`, `protect_event_handler.py`
- Verify: `grep -r "SessionLocal()" backend/app/services/ | grep -v "with SessionLocal"`
- Test with connection pool exhaustion scenario to verify no leaks

---

### Story P14-2.2: Add Missing Foreign Key Constraint

As a **database administrator**,
I want WebhookLog.alert_rule_id to have a proper foreign key constraint,
So that orphaned webhook logs are automatically cleaned up when rules are deleted.

**Acceptance Criteria:**

**Given** `alert_rule.py:132-133` has `alert_rule_id` indexed but not a foreign key
**When** an alert rule is deleted
**Then** associated webhook logs are cascaded deleted automatically

**And** an Alembic migration adds `ForeignKey("alert_rules.id", ondelete="CASCADE")`
**And** existing orphaned webhook logs (if any) are cleaned up in migration
**And** the migration is reversible

**Prerequisites:** P14-2.1

**Technical Notes:**
- File: `backend/app/models/alert_rule.py:132-133`
- Create migration: `alembic revision --autogenerate -m "add_webhooklog_fk_constraint"`
- Handle existing orphans: Delete webhook logs where alert_rule_id not in alert_rules
- Test: Create rule, create webhook log, delete rule, verify log deleted

---

### Story P14-2.3: Add Missing Database Indexes

As a **performance engineer**,
I want frequently queried columns to have indexes,
So that query performance is optimized for common access patterns.

**Acceptance Criteria:**

**Given** the following columns are frequently queried without indexes
**When** Alembic migration adds the indexes
**Then** query performance improves by 50%+ for filtered queries

Indexes to add:
1. **Events table**: Compound index on `(source_type, timestamp)` for Protect queries
2. **RecognizedEntities**: Index on `name` for LIKE queries in alert rules
3. **Devices**: Index on `pairing_confirmed` for filtering inactive devices
4. **APIKeys**: Indexes on `created_by` and `revoked_by` columns
5. **PairingCodes**: Compound index on `(device_id, expires_at)` for cleanup queries

**And** migration is reversible with proper `op.drop_index()` in downgrade
**And** index creation uses `if_not_exists=True` for idempotency

**Prerequisites:** P14-2.2

**Technical Notes:**
- Create single migration with all indexes
- Use `Index('ix_events_source_timestamp', 'source_type', 'timestamp')` pattern
- For name LIKE queries, consider partial index or GIN index (PostgreSQL)
- Benchmark: Run EXPLAIN ANALYZE before/after on common queries

---

### Story P14-2.4: Fix DELETE Endpoint Status Codes

As an **API consumer**,
I want DELETE endpoints to return proper REST status codes,
So that my client code follows standard HTTP semantics.

**Acceptance Criteria:**

**Given** DELETE endpoints in `cameras.py:507`, `notifications.py:184,209`
**When** a resource is successfully deleted
**Then** the endpoint returns 204 No Content (not 200 OK)

**And** the response body is empty (no JSON)
**And** FastAPI response_class is set to `Response` with status_code 204
**And** client code (frontend api-client.ts) handles 204 responses correctly

**Prerequisites:** P14-2.1

**Technical Notes:**
- Change: `status_code=status.HTTP_200_OK` → `status_code=status.HTTP_204_NO_CONTENT`
- Remove return statement body or use `Response(status_code=204)`
- Update frontend: Check `response.ok` instead of parsing JSON for DELETE calls
- Files: `cameras.py`, `notifications.py`, scan for other DELETE endpoints

---

### Story P14-2.5: Add UUID Validation on Path Parameters

As an **API consumer**,
I want invalid UUIDs to return 422 errors with clear messages,
So that I can debug malformed requests easily.

**Acceptance Criteria:**

**Given** all UUID path parameters are currently typed as `str`
**When** an invalid UUID string is provided (e.g., "not-a-uuid", "123")
**Then** the endpoint returns 422 Unprocessable Entity with clear error message

**And** all entity IDs (camera_id, event_id, rule_id, etc.) are typed as `UUID`
**And** FastAPI's built-in UUID validation provides the error message
**And** Path parameters have descriptions for OpenAPI documentation

**Prerequisites:** P14-2.1

**Technical Notes:**
- Change: `camera_id: str` → `camera_id: UUID` (from `uuid` module)
- Add Path description: `camera_id: UUID = Path(..., description="Camera UUID")`
- Files to update: `cameras.py`, `events.py`, `alert_rules.py`, `notifications.py`, etc.
- Scan: `grep -r "def.*_id: str" backend/app/api/`

---

### Story P14-2.6: Implement API Rate Limiting

As a **security administrator**,
I want all API endpoints to have rate limiting,
So that the system is protected from DoS attacks and abuse.

**Acceptance Criteria:**

**Given** no rate limiting exists on API endpoints
**When** a client exceeds the configured request limit
**Then** the endpoint returns 429 Too Many Requests with Retry-After header

**And** rate limiting uses `slowapi` library with configurable limits
**And** default limits: 100 req/min for reads, 20 req/min for writes
**And** rate limits are configurable per-endpoint via decorator
**And** API key authenticated requests have separate (higher) limits
**And** rate limit state persists across server restarts (Redis or database)
**And** `/api/v1/health` endpoint is exempt from rate limiting

**Prerequisites:** P14-2.5

**Technical Notes:**
- Install: `pip install slowapi`
- Configure: Create `app/middleware/rate_limit.py` with limiter setup
- Use Redis backend if available, fall back to in-memory for development
- Decorator pattern: `@limiter.limit("100/minute")` on endpoints
- Add to main.py: `app.state.limiter = limiter; app.add_middleware(...)`

---

## Epic P14-3: Backend Testing Infrastructure

**Goal:** Achieve 85%+ backend test coverage by adding comprehensive unit tests for core services with 0% coverage, improving test organization, and adding integration tests.

**Backlog Items:** TD-026, TD-027, TD-028, TD-029, TD-030, TD-031, TD-032, TD-033, TD-034, TD-035

### Story P14-3.1: Add Unit Tests for protect_service.py

As a **developer**,
I want comprehensive tests for the Protect service,
So that WebSocket connection management is regression-tested.

**Acceptance Criteria:**

**Given** `protect_service.py` (122 LOC) has 0% test coverage
**When** test suite runs
**Then** coverage reaches minimum 80% for this file

Test scenarios:
1. `test_connection()` method success and failure paths
2. WebSocket lifecycle (connect, disconnect, reconnect)
3. Exponential backoff delays (1, 2, 4, 8, 16, 30 seconds)
4. Connection timeout handling (10 second timeout per NFR3)
5. Camera discovery caching (60 second TTL)
6. Error handling for BadRequest, NotAuthorized, NvrError exceptions

**And** tests use mocked uiprotect library (no real controller needed)
**And** tests are parametrized for different error scenarios

**Prerequisites:** P14-2.1 (needs clean session management)

**Technical Notes:**
- Create: `tests/test_services/test_protect_service.py`
- Mock: `uiprotect.ProtectApiClient`
- Use `pytest-asyncio` for async test functions
- Parametrize backoff tests: `@pytest.mark.parametrize("attempt,expected_delay", [...])`

---

### Story P14-3.2: Add Unit Tests for protect_event_handler.py

As a **developer**,
I want comprehensive tests for the event handler,
So that event filtering and processing logic is regression-tested.

**Acceptance Criteria:**

**Given** `protect_event_handler.py` (250+ LOC) has 0% test coverage
**When** test suite runs
**Then** coverage reaches minimum 80% for this file

Test scenarios:
1. Event type parsing (motion, smart_detect_person, smart_detect_vehicle, ring)
2. Filter chain evaluation with multiple conditions
3. Smart detection type filtering (person, vehicle, package, animal)
4. Cooldown deduplication logic (events within cooldown window)
5. HomeKit doorbell integration (Story P5-1.7)
6. Snapshot triggering coordination

**And** tests cover edge cases (null fields, malformed events)
**And** tests verify correct event flow to AI service

**Prerequisites:** P14-3.1

**Technical Notes:**
- Create: `tests/test_services/test_protect_event_handler.py`
- Mock: ProtectService, AIService, SnapshotService
- Create fixture: `make_protect_event()` factory for test events
- Test cooldown: Use `freezegun` to control time

---

### Story P14-3.3: Add Unit Tests for snapshot_service.py

As a **developer**,
I want comprehensive tests for the snapshot service,
So that concurrent image processing is regression-tested.

**Acceptance Criteria:**

**Given** `snapshot_service.py` (180+ LOC) has 0% test coverage
**When** test suite runs
**Then** coverage reaches minimum 80% for this file

Test scenarios:
1. Semaphore-based concurrency limiting (max 3 concurrent per controller)
2. Timeout handling (1 second timeout)
3. Image resizing and thumbnail generation
4. Resize dimension validation (max 1920x1080)
5. Base64 encoding pipeline
6. Retry logic with 0.5s delays

**And** concurrency tests verify semaphore exhaustion behavior
**And** tests use mock images (not real camera snapshots)

**Prerequisites:** P14-3.2

**Technical Notes:**
- Create: `tests/test_services/test_snapshot_service.py`
- Mock: uiprotect camera.get_snapshot()
- Create test images: Use PIL to generate small test images
- Test concurrency: Use `asyncio.gather()` with multiple requests

---

### Story P14-3.4: Add Unit Tests for reprocessing_service.py

As a **developer**,
I want comprehensive tests for the reprocessing service,
So that background job handling is regression-tested.

**Acceptance Criteria:**

**Given** `reprocessing_service.py` (180+ LOC) has 0% test coverage
**When** test suite runs
**Then** coverage reaches minimum 70% for this file

Test scenarios:
1. Job status transitions (PENDING → RUNNING → COMPLETED)
2. Checkpoint/resume logic (NFR14)
3. Job cancellation during processing
4. WebSocket progress updates
5. Progress broadcast frequency

**And** tests verify resumability after simulated restart
**And** tests verify progress WebSocket messages

**Prerequisites:** P14-3.3

**Technical Notes:**
- Create: `tests/test_services/test_reprocessing_service.py`
- Mock: WebSocket manager, database session
- Test cancellation: Set cancel flag mid-processing
- Verify progress: Capture WebSocket broadcasts

---

### Story P14-3.5: Add Unit Tests for websocket_manager.py

As a **developer**,
I want comprehensive tests for the WebSocket manager,
So that real-time update delivery is regression-tested.

**Acceptance Criteria:**

**Given** `websocket_manager.py` (181 LOC) has 0% test coverage
**When** test suite runs
**Then** coverage reaches minimum 70% for this file

Test scenarios:
1. Connection lifecycle (connect, disconnect, reconnect)
2. Message delivery reliability
3. Broadcast message routing and ordering
4. Connection cleanup on errors/disconnects

**And** tests verify message delivery to multiple clients
**And** tests verify cleanup after disconnect

**Prerequisites:** P14-3.4

**Technical Notes:**
- Create: `tests/test_services/test_websocket_manager.py`
- Use: `starlette.testclient.TestClient` with WebSocket support
- Test broadcast: Connect multiple mock clients, send message, verify all receive

---

### Story P14-3.6: Add Unit Tests for api_key_service.py

As a **developer**,
I want comprehensive tests for the API key service,
So that authentication/authorization logic is regression-tested.

**Acceptance Criteria:**

**Given** `api_key_service.py` (262 LOC) has 0% test coverage
**When** test suite runs
**Then** coverage reaches minimum 80% for this file (security-critical)

Test scenarios:
1. Key generation (format, uniqueness, prefix)
2. Key hashing and validation against hash
3. Encryption/decryption of stored keys
4. Key expiration checking
5. Key revocation
6. Prefix-based lookup

**And** tests verify key is shown only once at creation
**And** tests verify revoked keys fail authentication

**Prerequisites:** P14-3.5

**Technical Notes:**
- Create: `tests/test_services/test_api_key_service.py`
- Test hashing: Generate key, verify bcrypt/argon2 hash validates
- Test expiration: Use `freezegun` to test expired keys
- Test prefix lookup: Verify `argus_DZ1c...` prefix matches correctly

---

### Story P14-3.7: Increase Test Parametrization

As a **developer**,
I want data-driven tests to use parametrization,
So that test isolation and failure messages are improved.

**Acceptance Criteria:**

**Given** only 11 `@pytest.mark.parametrize` instances exist in 3,424 tests
**When** loop-based test cases are converted to parametrization
**Then** at least 50 parametrized tests exist

**And** `test_ai_service.py` object extraction tests are parametrized
**And** each parameter set runs as isolated test
**And** failure messages show which parameter set failed

**Prerequisites:** P14-3.6

**Technical Notes:**
- Pattern: Convert `for case in cases: assert...` to `@pytest.mark.parametrize`
- Focus files: `test_ai_service.py`, `test_event_processor.py`
- Benefits: Better isolation, clearer failures, easier to add cases
- Example: `@pytest.mark.parametrize("input,expected", [("person", True), ("tree", False)])`

---

### Story P14-3.8: Consolidate Test Fixture Definitions

As a **developer**,
I want shared test fixtures in global conftest.py,
So that test setup is consistent and not duplicated.

**Acceptance Criteria:**

**Given** multiple test modules redefine `test_db`, `sample_event`, etc.
**When** fixtures are consolidated
**Then** global `conftest.py` contains all shared fixtures

Fixtures to create/consolidate:
1. `sample_event` factory with all Event fields
2. `sample_camera` factory with all Camera fields
3. `sample_rule` factory with all AlertRule fields
4. `sample_entity` factory with all RecognizedEntity fields

**And** individual test files import from conftest (not redefine)
**And** fixtures use factory pattern for customization

**Prerequisites:** P14-3.7

**Technical Notes:**
- File: `tests/conftest.py`
- Pattern: `def make_event(**overrides) -> Event`
- Remove duplicates from: `test_api/conftest.py`, individual test files
- Use `pytest-factoryboy` or simple factory functions

---

### Story P14-3.9: Add Missing API Route Tests

As a **developer**,
I want all API routes to have test coverage,
So that endpoint behavior is verified.

**Acceptance Criteria:**

**Given** 12 API route modules (26%) have no test coverage
**When** tests are added
**Then** security-critical modules have 80%+ coverage

Priority modules to test:
1. `auth.py` - Login, logout, session management
2. `api_keys.py` - Key CRUD, authentication
3. `notifications.py` - User-facing notifications
4. `mobile_auth.py` - Device pairing, token exchange

Secondary modules:
5. `audio.py`, `voice.py`, `motion_events.py`, `system_notifications.py`, `logs.py`, `websocket.py`

**And** tests use TestClient with proper authentication
**And** tests cover success and error paths

**Prerequisites:** P14-3.8

**Technical Notes:**
- Create: `tests/test_api/test_auth.py`, `test_api_keys.py`, etc.
- Use: `fastapi.testclient.TestClient`
- Mock: Database, external services
- Priority: auth and api_keys first (security-critical)

---

### Story P14-3.10: Add End-to-End Integration Tests

As a **developer**,
I want integration tests for complete flows,
So that component interactions are verified.

**Acceptance Criteria:**

**Given** no composite flow tests exist
**When** integration tests are added
**Then** critical user journeys are covered

Test scenarios:
1. Camera capture → motion detection → AI description → alert → webhook
2. Protect event → entity matching → notification
3. Event correlation across multiple cameras
4. Reprocessing job with entity matching

**And** tests use real database (test database, not mocks)
**And** tests run in isolated transactions (rollback after each)
**And** external services (AI providers, cameras) are mocked

**Prerequisites:** P14-3.9

**Technical Notes:**
- Create: `tests/test_integration/`
- Use: TestClient with real database session
- Pattern: Fixture creates test data, test runs flow, assertions verify state
- This is P4 priority - can be deferred if time-constrained

---

## Epic P14-4: Frontend Code Quality

**Goal:** Fix frontend test infrastructure issues, clean up code quality problems, and establish proper React patterns.

**Backlog Items:** TD-006, TD-007, TD-008, TD-009, TD-010, IMP-040, IMP-041, IMP-042

### Story P14-4.1: Remove Debug Console.log

As a **developer**,
I want production builds to have no debug logging,
So that the browser console is clean for users.

**Acceptance Criteria:**

**Given** `console.log('[API] Request to:', endpoint, ...)` at `lib/api-client.ts:203`
**When** the application runs in production
**Then** no debug console.log statements execute

**And** the specific log at line 203 is removed
**And** any other debug console.log statements are removed
**And** error logging (console.error) is preserved for genuine errors

**Prerequisites:** P14-1.1, P14-1.2

**Technical Notes:**
- File: `frontend/lib/api-client.ts:203`
- Remove line or wrap in `if (process.env.NODE_ENV === 'development')`
- Scan: `grep -r "console.log" frontend/lib/ frontend/components/`
- Keep: `console.error` for actual errors

---

### Story P14-4.2: Fix Test Type Mismatches

As a **developer**,
I want test fixtures to match current TypeScript interfaces,
So that tests compile without type errors.

**Acceptance Criteria:**

**Given** 30+ test fixtures have type mismatches
**When** fixtures are updated
**Then** all tests compile with zero type errors

Fixtures to fix:
1. `ICamera` - Add `homekit_stream_quality` (required field)
2. `IEntity` - Add `thumbnail_path` (required field)
3. `ICorrelatedEvent` - Add `thumbnail_url`, `timestamp`
4. Mock `apiClient` - Fix type mismatches

Files affected: CameraForm.test.tsx, CameraPreview.test.tsx, VirtualCameraList.test.tsx, EntityCard.test.tsx, EntityAlertModal.test.tsx, DeleteEntityDialog.test.tsx, AnalysisModeFilter.test.tsx, EventCard.test.tsx, EventDetailModal.test.tsx

**And** `npx tsc --noEmit` passes with zero errors
**And** all 806+ tests pass

**Prerequisites:** P14-4.1

**Technical Notes:**
- Run: `npm run test` to identify failures
- Update each fixture to include missing required fields
- Use `Partial<ICamera>` pattern if some fields are optional in tests
- Consider creating `makeMockCamera()` factory function

---

### Story P14-4.3: Fix Failing TunnelSettings Test

As a **developer**,
I want the TunnelSettings test to pass,
So that CI is green.

**Acceptance Criteria:**

**Given** test "starts tunnel with new token when Save is clicked" fails at line 456
**When** the mock is fixed
**Then** `apiClient.tunnel.start` mock is called correctly

**And** the test verifies tunnel starts with the entered token
**And** the test passes reliably (not flaky)

**Prerequisites:** P14-4.2

**Technical Notes:**
- File: `frontend/__tests__/components/settings/TunnelSettings.test.tsx:456`
- Debug: Add console.log to see what mock is being called
- Likely issue: Mock setup or async timing
- Use `waitFor()` if action is async

---

### Story P14-4.4: Create Shared Test Fixtures Factory

As a **developer**,
I want complete mock factories in test utilities,
So that test setup is consistent across files.

**Acceptance Criteria:**

**Given** current mockEvent and mockCamera factories are incomplete
**When** factories are updated
**Then** all required fields are included

Create/update in `__tests__/test-utils.tsx`:
1. `mockCamera` - All `ICamera` fields with sensible defaults
2. `mockEntity` - All `IEntity` fields
3. `mockController` - For Protect tests
4. `mockApiClient` - Properly typed mock functions

**And** factories accept partial overrides: `mockCamera({ name: 'Custom' })`
**And** TypeScript infers correct types from factories

**Prerequisites:** P14-4.3

**Technical Notes:**
- File: `frontend/__tests__/test-utils.tsx`
- Pattern: `export const mockCamera = (overrides?: Partial<ICamera>): ICamera => ({...defaults, ...overrides})`
- Import and use across all test files
- Remove duplicate mock definitions from individual test files

---

### Story P14-4.5: Clean Up Unused Test Imports

As a **developer**,
I want test files to have no unused imports,
So that ESLint passes with zero warnings.

**Acceptance Criteria:**

**Given** 9 unused imports in test files
**When** imports are removed
**Then** ESLint shows zero unused import warnings in tests

Imports to remove:
1. `vi` in AudioSettingsSection.test.tsx:7
2. `container` in Sidebar.test.tsx:165
3. `within` in AccuracyDashboard.test.tsx:21
4. `userEvent` in CostDashboard.test.tsx:15
5. `FrameSamplingStrategy` in FrameSamplingStrategySelector.test.tsx:8
6. `fireEvent` in MQTTSettings.test.tsx:18
7. `fireEvent` in GenerateSummaryDialog.test.tsx:14
8. `waitFor` in useWebSocket.test.ts:13
9. `ConnectionStatus` in useWebSocket.test.ts:14

**And** `npm run lint` passes with zero warnings

**Prerequisites:** P14-4.4

**Technical Notes:**
- Simply remove the unused imports from each file
- Run: `npm run lint -- --fix` may auto-fix some

---

### Story P14-4.6: Clean Up Unused Component Imports

As a **developer**,
I want component files to have no unused imports,
So that bundle size is minimized and code is clean.

**Acceptance Criteria:**

**Given** 12 unused imports in component files
**When** imports are removed
**Then** ESLint shows zero unused import warnings in components

Imports to remove:
1. `FormLabel` in AnalysisModeSelector.tsx:18
2. `hasOvernightRange` in DetectionScheduleEditor.tsx:204
3. `formatDateLabel` in SummaryCard.tsx:131
4. `error` in SummaryCard.tsx:150
5. `Checkbox` in EntityCard.tsx:17
6. `useEntityEvents` in EntityDetail.tsx:22
7. `entityName` in EventCard.tsx:82
8. `AnalysisMode` in ReAnalyzeButton.tsx:22
9. `getFilterCount` in EventTypeFilter.tsx:141
10. `BarChart3` in APIKeySettings.tsx:26
11. `getAccuracyBadgeVariant` in CameraAccuracyTable.tsx:35
12. `ICostCapStatus`, `Progress` in CostCapSettings.tsx:27,34

**And** tree-shaking removes dead code from production build

**Prerequisites:** P14-4.5

**Technical Notes:**
- Remove each import listed above
- Some may be commented code that needs deletion too
- Run: `npm run build` to verify no build errors

---

### Story P14-4.7: Fix setState-in-useEffect Anti-patterns

As a **developer**,
I want proper React state patterns,
So that unnecessary re-renders are prevented.

**Acceptance Criteria:**

**Given** 5 components call setState synchronously inside useEffect
**When** refactored
**Then** state is derived or initialized properly

Components to fix:
1. `EntityMergeDialog.tsx:143` - Use initializer function or useMemo
2. `FrameGalleryModal.tsx:63` - Reset state in open handler
3. `ReAnalyzeModal.tsx:239` - Use onOpenChange callback
4. `AnalysisModePopover.tsx:87` - Use controlled state pattern
5. `EventTypeFilter.tsx:78` - Compute from props instead of derived state

**And** no ESLint warnings for exhaustive-deps
**And** component behavior is unchanged

**Prerequisites:** P14-4.6

**Technical Notes:**
- Pattern 1: Use `useState(() => initialValue)` for computed initial state
- Pattern 2: Move state reset to event handler, not useEffect
- Pattern 3: Derive state from props with useMemo instead of storing
- Test each component after refactor

---

### Story P14-4.8: Extract SortIcon Component

As a **developer**,
I want SortIcon defined at module scope,
So that component state is not reset on every render.

**Acceptance Criteria:**

**Given** `SortIcon` is defined inside `CameraAccuracyTable` render at line 89
**When** extracted to module scope
**Then** ESLint warnings are eliminated

**And** SortIcon is defined as `const SortIcon = ({ ... }) => ...` at module scope
**And** or uses `useMemo` to memoize the render function
**And** sorting functionality continues to work correctly

**Prerequisites:** P14-4.7

**Technical Notes:**
- File: `frontend/components/settings/CameraAccuracyTable.tsx:89`
- Move `const SortIcon = ...` outside the component function
- Pass any needed props explicitly
- This eliminates 5 ESLint warnings

---

## Epic P14-5: Code Standardization

**Goal:** Establish consistent code patterns across the codebase by creating shared utilities and enforcing standards for singletons, backoff logic, database patterns, and API formats.

**Backlog Items:** TD-013, TD-014, TD-017, TD-018, TD-019, TD-022, TD-025, IMP-050, IMP-051, IMP-053

### Story P14-5.1: Create @singleton Decorator

As a **developer**,
I want a @singleton decorator utility,
So that singleton pattern boilerplate is eliminated.

**Acceptance Criteria:**

**Given** 50+ services use identical manual singleton pattern
**When** decorator is created
**Then** services can use `@singleton` instead

Create `app/utils/decorators.py`:
```python
def singleton(cls):
    """Decorator to make a class a singleton."""
    instances = {}
    lock = threading.Lock()

    def get_instance(*args, **kwargs):
        if cls not in instances:
            with lock:
                if cls not in instances:
                    instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance
```

**And** decorator handles thread-safety with lock
**And** decorator works with both sync and async classes
**And** tests verify singleton behavior

**Prerequisites:** P14-2.1

**Technical Notes:**
- File: `backend/app/utils/decorators.py`
- Pattern replaces: `_instance = None; def get_service(): ...`
- Usage: `@singleton` above class definition
- Test: Multiple calls return same instance

---

### Story P14-5.2: Create Exponential Backoff Utility

As a **developer**,
I want a shared exponential backoff utility,
So that retry logic is consistent.

**Acceptance Criteria:**

**Given** 4 separate backoff implementations with different delays
**When** utility is created
**Then** all services use the shared implementation

Create `app/utils/retry.py`:
```python
async def exponential_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True
) -> float:
    """Calculate delay with exponential backoff."""
    delay = min(base_delay * (2 ** attempt), max_delay)
    if jitter:
        delay *= (0.5 + random.random())
    await asyncio.sleep(delay)
    return delay
```

**And** utility supports configurable base/max delays
**And** optional jitter prevents thundering herd
**And** tests verify delay calculations

**Prerequisites:** P14-5.1

**Technical Notes:**
- Files to update: `camera_service.py:542`, `protect_service.py:35`, `webhook_service.py:49`, `mqtt_service.py:42`
- Replace inline delay calculation with utility call
- Keep service-specific max delays if different

---

### Story P14-5.3: Migrate Services to @singleton Decorator

As a **developer**,
I want all singleton services to use the decorator,
So that code is consistent and reduced by ~150 lines.

**Acceptance Criteria:**

**Given** 50+ services use manual singleton pattern
**When** migrated to decorator
**Then** all use `@singleton` consistently

Services to migrate (sample):
- `camera_service.py:773-787`
- `snapshot_service.py:538-545`
- `entity_service.py:1959-1966`
- And 37+ more...

**And** `get_service()` functions are removed or become simple wrappers
**And** all existing functionality continues to work
**And** ~150 lines of boilerplate removed

**Prerequisites:** P14-5.1, P14-5.2

**Technical Notes:**
- Find all: `grep -r "_instance: Optional" backend/app/services/`
- Replace pattern file by file
- Run tests after each file to catch issues early
- This is P3 priority - can be done incrementally

---

### Story P14-5.4: Migrate Services to Backoff Utility

As a **developer**,
I want all retry logic to use the shared utility,
So that behavior is consistent.

**Acceptance Criteria:**

**Given** 4 services have separate backoff implementations
**When** migrated to utility
**Then** all use `exponential_backoff()` from utils

Services to migrate:
1. `camera_service.py:542` - Camera reconnection
2. `protect_service.py:35` - Controller reconnection
3. `webhook_service.py:49` - Webhook delivery retry
4. `mqtt_service.py:42` - MQTT reconnection

**And** delay behavior is unchanged (or improved with jitter)
**And** tests verify retry behavior

**Prerequisites:** P14-5.2

**Technical Notes:**
- Import: `from app.utils.retry import exponential_backoff`
- Replace inline delay with: `await exponential_backoff(attempt, base_delay=1.0, max_delay=30.0)`
- Preserve service-specific delay configurations

---

### Story P14-5.5: Fix backref vs back_populates Inconsistency

As a **developer**,
I want all relationships to use back_populates,
So that SQLAlchemy patterns are consistent.

**Acceptance Criteria:**

**Given** `face_embedding.py:95` and `vehicle_embedding.py:101` use legacy `backref`
**When** updated
**Then** all relationships use bidirectional `back_populates`

**And** FaceEmbedding has: `entity = relationship("RecognizedEntity", back_populates="face_embeddings")`
**And** RecognizedEntity has corresponding `face_embeddings = relationship(...)`
**And** same pattern for VehicleEmbedding

**Prerequisites:** P14-5.3

**Technical Notes:**
- Files: `face_embedding.py`, `vehicle_embedding.py`, `recognized_entity.py`
- Pattern: Replace `backref="..."` with `back_populates="..."`
- Add reverse relationship on parent model if missing
- Test: Verify bidirectional navigation works

---

### Story P14-5.6: Add Check Constraints on Float Columns

As a **database administrator**,
I want float columns to have range constraints,
So that invalid data cannot be stored.

**Acceptance Criteria:**

**Given** several float columns lack constraints
**When** constraints are added
**Then** database rejects out-of-range values

Constraints to add:
1. `event.ai_confidence` - CheckConstraint: 0 <= value <= 100
2. `event.anomaly_score` - CheckConstraint: 0 <= value <= 1
3. `event.audio_confidence` - CheckConstraint: 0 <= value <= 1
4. `camera.audio_threshold` - CheckConstraint: 0 <= value <= 1

**And** Alembic migration adds constraints
**And** existing data is validated (migration fails if invalid data exists)

**Prerequisites:** P14-5.5

**Technical Notes:**
- Add to `__table_args__`: `CheckConstraint('ai_confidence >= 0 AND ai_confidence <= 100')`
- Create migration: `alembic revision -m "add_float_check_constraints"`
- Handle existing invalid data in migration (update or error)

---

### Story P14-5.7: Fix Timestamp Timezone Handling

As a **developer**,
I want consistent UTC timestamp handling,
So that time-based queries work correctly across timezones.

**Acceptance Criteria:**

**Given** `system_setting.py:21` uses `server_default=func.now()` (server time)
**When** standardized
**Then** all timestamps use Python UTC with timezone=True

**And** `system_setting.py` uses `default=lambda: datetime.now(timezone.utc)`
**And** `activity_summary.py` (period_start/end) has timezone=True
**And** `homekit.py` DateTime columns have timezone=True
**And** `user.py` DateTime columns have timezone=True
**And** Alembic migration updates column definitions

**Prerequisites:** P14-5.6

**Technical Notes:**
- Pattern: `Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))`
- Migration: May need to convert existing timestamps
- Be careful: Changing timezone handling can break queries

---

### Story P14-5.8: Standardize API Response Format

As an **API consumer**,
I want consistent response formats,
So that client code is predictable.

**Acceptance Criteria:**

**Given** Protect API uses `{data: {...}, meta: {...}}` while others return models directly
**When** documented and standardized
**Then** API response format is consistent or clearly documented

Options:
1. Add wrapper to all APIs
2. Remove wrapper from Protect API
3. Document the difference

**And** chosen approach is documented in OpenAPI/README
**And** frontend api-client handles both patterns (if keeping difference)
**And** new endpoints follow the chosen standard

**Prerequisites:** P14-5.7

**Technical Notes:**
- Recommendation: Document the difference, keep both patterns
- Protect API uses wrapper for pagination metadata
- Other APIs return models directly for simplicity
- Update API documentation to clarify

---

### Story P14-5.9: Add Notification Model Relationships

As a **developer**,
I want Notification model to have relationship objects,
So that related data can be accessed efficiently.

**Acceptance Criteria:**

**Given** `notification.py:30-31` has FKs but no relationships
**When** relationships are added
**Then** `notification.event` and `notification.rule` are accessible

**And** add: `event = relationship("Event", back_populates="notifications")`
**And** add: `rule = relationship("AlertRule", back_populates="notifications")`
**And** add corresponding back_populates on Event and AlertRule models

**Prerequisites:** P14-5.8

**Technical Notes:**
- File: `backend/app/models/notification.py`
- Add relationships at model class level
- Update Event and AlertRule models with reverse relationships
- Test: `notification.event.description` works

---

### Story P14-5.10: Improve JSON Parse Error Handling

As a **developer**,
I want JSON errors to be logged with context,
So that data issues can be debugged.

**Acceptance Criteria:**

**Given** `alert_engine.py:73-75,83-85` silently returns empty dict on parse error
**When** logging is added
**Then** warnings are logged with rule_id and field name

**And** `webhook_service.py` has same improvement
**And** log format: `JSON parse error in rule {rule_id}, field {field_name}: {error}`
**And** empty dict is still returned (fail-safe behavior preserved)

**Prerequisites:** P14-5.9

**Technical Notes:**
- Files: `alert_engine.py`, `webhook_service.py`
- Pattern: Add `logger.warning(f"JSON parse error...")` before return {}
- Don't change behavior (still return empty dict), just add visibility

---

## Epic P14-6: MCP Context System Enhancement

**Goal:** Improve the MCP context system to deliver faster, more accurate AI descriptions by implementing parallel queries, integrating entity adjustments, and adding performance monitoring.

**Backlog Items:** IMP-055, IMP-056, IMP-057, IMP-058, IMP-059, IMP-060, IMP-061, IMP-062

### Story P14-6.1: Integrate Entity Adjustments Context

As an **AI system**,
I want entity adjustment data in the context,
So that AI descriptions learn from manual corrections.

**Acceptance Criteria:**

**Given** EntityAdjustment model has 120 records unused in MCP context
**When** integrated
**Then** AI prompts include correction history

**And** `MCPContextProvider._get_entity_context()` queries EntityAdjustment
**And** corrections format: "Previously corrected: [original] → [corrected]"
**And** most recent 5-10 corrections per entity are included
**And** tests verify correction context appears in formatted prompt

**Prerequisites:** P14-2.1

**Technical Notes:**
- File: `backend/app/services/mcp_context.py`
- Query: Join EntityAdjustment with RecognizedEntity
- Format for prompt: Include original vs corrected entity info
- Reference: docs/mcp-architecture-review.md Section 3.1

---

### Story P14-6.2: Implement Parallel Query Execution

As a **performance engineer**,
I want MCP context queries to run in parallel,
So that latency is reduced from 12ms to <5ms.

**Acceptance Criteria:**

**Given** 4 context queries run sequentially (~12ms total)
**When** parallelized with asyncio.gather()
**Then** latency is max of queries (~4ms), not sum

**And** `get_context()` uses: `await asyncio.gather(*tasks, return_exceptions=True)`
**And** failed queries don't block successful ones (fail-open)
**And** metrics show latency reduction

**Prerequisites:** P14-6.1

**Technical Notes:**
- File: `backend/app/services/mcp_context.py:288-300`
- Pattern:
```python
tasks = [
    self._safe_get_feedback_context(session, camera_id),
    self._safe_get_entity_context(session, entity_id),
    self._safe_get_camera_context(session, camera_id),
    self._safe_get_time_pattern_context(session, camera_id, event_time),
]
results = await asyncio.gather(*tasks, return_exceptions=True)
```
- Handle exceptions in results list

---

### Story P14-6.3: Fix Async/Sync Database Query Mismatch

As a **developer**,
I want MCP database queries to not block the event loop,
So that concurrency is not reduced.

**Acceptance Criteria:**

**Given** async methods perform synchronous `query.all()` calls
**When** fixed
**Then** queries use async session or run_in_executor

Options:
1. Use SQLAlchemy async session with `await session.execute()`
2. Run sync queries in executor: `await loop.run_in_executor(None, sync_query)`

**And** event loop is not blocked during queries
**And** query performance is unchanged or improved

**Prerequisites:** P14-6.2

**Technical Notes:**
- File: `backend/app/services/mcp_context.py` (all `_get_*_context` methods)
- Option 1 requires async SQLAlchemy setup (more work)
- Option 2 is simpler: wrap sync query in `run_in_executor`
- Benchmark both approaches

---

### Story P14-6.4: Add Query Timeout Enforcement

As a **reliability engineer**,
I want MCP context gathering to have a timeout,
So that AI prompts are never blocked waiting for context.

**Acceptance Criteria:**

**Given** research doc specifies 80ms hard timeout
**When** implemented
**Then** context gathering times out gracefully

**And** `TIMEOUT_MS = 80` constant is defined
**And** `get_context()` is wrapped in `asyncio.wait_for()`
**And** timeout logs warning but returns partial context (fail-open)
**And** metrics track timeout frequency

**Prerequisites:** P14-6.3

**Technical Notes:**
- Pattern:
```python
try:
    context = await asyncio.wait_for(self._gather_context(...), timeout=0.08)
except asyncio.TimeoutError:
    logger.warning("MCP context timeout, using partial context")
    context = self._get_partial_context()
```
- Return whatever context was gathered before timeout

---

### Story P14-6.5: Investigate and Optimize Cache Hit Ratio

As a **performance engineer**,
I want higher MCP cache hit ratio,
So that repeated queries are fast.

**Acceptance Criteria:**

**Given** current hit ratio is 9.5% (2/21 requests)
**When** optimized
**Then** hit ratio reaches >50%

Investigation areas:
1. Analyze event distribution across camera:hour combinations
2. Consider shorter TTL with higher granularity keys
3. Evaluate Redis for cross-restart persistence
4. Add cache analytics metrics

**And** cache key strategy is documented
**And** metrics show improved hit ratio
**And** recommendations are implemented

**Prerequisites:** P14-6.4

**Technical Notes:**
- Current key: `{camera_id}:{event_time.hour}`
- Alternative: `{camera_id}` with shorter TTL
- Add logging to track cache key distribution
- Consider: If events are spread evenly, 9.5% may be expected

---

### Story P14-6.6: Improve Pattern Extraction Algorithm

As an **AI accuracy engineer**,
I want better pattern extraction,
So that meaningful patterns are identified.

**Acceptance Criteria:**

**Given** current extraction uses simple word frequency
**When** improved
**Then** patterns are more meaningful

Improvements:
1. Add domain-specific stop words (security camera terminology)
2. Use TF-IDF instead of raw frequency
3. Consider n-gram extraction for multi-word patterns
4. Add minimum frequency threshold

**And** production patterns like "frame, left, scene" are filtered out
**And** meaningful patterns like "package delivery", "person at door" are captured
**And** tests verify pattern quality

**Prerequisites:** P14-6.5

**Technical Notes:**
- File: `backend/app/services/mcp_context.py:845-882`
- Add stop words: "frame", "left", "right", "scene", "camera", etc.
- Consider: `sklearn.feature_extraction.text.TfidfVectorizer`
- Or simple: Increase min frequency from 1 to 3

---

### Story P14-6.7: Add VIP/Blocked Entity Context

As an **AI system**,
I want VIP and blocked entity flags in context,
So that descriptions can prioritize or ignore appropriately.

**Acceptance Criteria:**

**Given** RecognizedEntity has `is_vip` and `is_blocked` boolean fields
**When** included in EntityContext
**Then** AI prompts can reference these flags

**And** EntityContext dataclass has `is_vip: bool` and `is_blocked: bool`
**And** Entity query includes these fields
**And** Prompt format: "VIP: John - prioritize mentions" or "Blocked: ignore this person"
**And** tests verify flags appear in formatted prompt

**Prerequisites:** P14-6.6

**Technical Notes:**
- File: `backend/app/services/mcp_context.py`
- Update `EntityContext` dataclass
- Update `_get_entity_context()` query
- Update `format_for_prompt()` to include VIP/blocked info

---

### Story P14-6.8: Add Context Metrics Dashboard

As an **administrator**,
I want to see MCP context performance metrics,
So that I can monitor and optimize AI accuracy.

**Acceptance Criteria:**

**Given** only Prometheus metrics exist for MCP context
**When** dashboard is added
**Then** Settings page shows context metrics

Dashboard shows:
1. Cache hit/miss rates (current: 9.5% hit)
2. Average latency (current: 11.8ms uncached)
3. Component availability (feedback, entity, camera, time)
4. Most common corrections and entity matches

**And** tab added to Settings > AI
**And** metrics update in real-time (or on refresh)
**And** historical data for trend analysis (optional)

**Prerequisites:** P14-6.7

**Technical Notes:**
- This is P4 priority - can be deferred
- Create: `frontend/components/settings/ContextMetrics.tsx`
- API: Add `GET /api/v1/system/mcp-metrics` endpoint
- Use existing Prometheus metrics as data source

---

## Epic P14-7: Frontend Enhancements

**Goal:** Improve frontend accessibility, performance, and developer experience through targeted enhancements.

**Backlog Items:** IMP-043, IMP-044, IMP-045, IMP-046, IMP-047, IMP-048

### Story P14-7.1: Add Alt Text to BackupRestore Images

As a **screen reader user**,
I want images to have alt text,
So that I understand what they represent.

**Acceptance Criteria:**

**Given** `BackupRestore.tsx:335` and `BackupRestore.tsx:580` have images without alt
**When** alt text is added
**Then** images are accessible to screen readers

**And** meaningful alt text describes image content
**And** or `alt=""` for purely decorative images
**And** accessibility audit passes for this component

**Prerequisites:** P14-4.8

**Technical Notes:**
- File: `frontend/components/settings/BackupRestore.tsx`
- Add `alt="Backup file preview"` or similar
- If decorative: `alt="" role="presentation"`
- Test with screen reader or accessibility devtools

---

### Story P14-7.2: Replace img with next/image

As a **performance engineer**,
I want optimized image loading,
So that page load is faster.

**Acceptance Criteria:**

**Given** 4 native `<img>` elements exist
**When** replaced with `<Image>`
**Then** images are automatically optimized

Files to update:
1. `CameraForm.tsx:562`
2. `RecentActivity.tsx:113`
3. `EntityCreateModal.tsx:395`
4. `NotificationDropdown.tsx:179`

**And** images use lazy loading
**And** images use responsive sizing
**And** WebP format is served where supported

**Prerequisites:** P14-7.1

**Technical Notes:**
- Import: `import Image from 'next/image'`
- Replace: `<img src={url} />` → `<Image src={url} width={...} height={...} alt="..." />`
- For external images: Add domain to `next.config.js` images.domains
- Note: May need `unoptimized` prop for dynamic URLs

---

### Story P14-7.3: Enable Stricter TypeScript Checks

As a **developer**,
I want stricter type safety,
So that more bugs are caught at compile time.

**Acceptance Criteria:**

**Given** TypeScript has additional strict options available
**When** evaluated
**Then** decision is made and documented

Options to evaluate:
1. `noUncheckedIndexedAccess` - Catches undefined array/object access
2. `exactOptionalPropertyTypes` - Stricter optional property handling

**And** if enabled: Fix resulting type errors (~20-30 estimated)
**And** if not enabled: Document reason in tsconfig.json comments
**And** CI enforces the chosen configuration

**Prerequisites:** P14-7.2

**Technical Notes:**
- File: `frontend/tsconfig.json`
- Enable one at a time to assess impact
- `noUncheckedIndexedAccess` will require many `?.` operators
- This is P4 priority - can document as "not enabled" with reason

---

### Story P14-7.4: Increase Hook Test Coverage

As a **developer**,
I want all hooks to have test coverage,
So that hook behavior is regression-tested.

**Acceptance Criteria:**

**Given** 5/18 hooks have tests (27% coverage)
**When** tests are added
**Then** all 18 hooks have minimum 70% coverage

Hooks needing tests:
1. useCameraDetail.ts
2. useCameras.ts
3. useFeedback.ts
4. useFeedbackStats.ts
5. useHomekitStatus.ts
6. useInstallPrompt.ts
7. useNotificationPreferences.ts
8. usePromptInsights.ts
9. usePushNotifications.ts
10. useServiceWorker.ts
11. useSummaries.ts
12. useSummaryFeedback.ts
13. useToast.ts

**And** tests use `@testing-library/react-hooks` or `renderHook`
**And** tests mock API calls appropriately

**Prerequisites:** P14-7.3

**Technical Notes:**
- Create: `frontend/__tests__/hooks/use*.test.ts` for each
- Use: `renderHook(() => useCamera(...))` pattern
- Mock: API client, WebSocket, localStorage as needed
- This is significant effort (2 days)

---

### Story P14-7.5: Add React Query DevTools

As a **developer**,
I want React Query DevTools in development,
So that I can debug query states.

**Acceptance Criteria:**

**Given** TanStack Query v5.90+ is already in use
**When** DevTools are added
**Then** query cache state is visible in development

**And** `@tanstack/react-query-devtools` is installed
**And** DevTools only appear in development builds
**And** DevTools show: query status, cache data, refetch triggers

**Prerequisites:** P14-7.4

**Technical Notes:**
- Install: `npm install @tanstack/react-query-devtools`
- Add to `app/providers.tsx`:
```tsx
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
// In QueryClientProvider:
{process.env.NODE_ENV === 'development' && <ReactQueryDevtools />}
```
- Quick win - 15 minutes implementation

---

### Story P14-7.6: Add OpenAPI Summaries and Tags

As an **API consumer**,
I want Swagger UI to have good navigation,
So that I can find endpoints easily.

**Acceptance Criteria:**

**Given** most endpoints lack `summary` and `tags` parameters
**When** added
**Then** Swagger UI is well-organized

**And** all endpoints have `summary="Create camera"` style descriptions
**And** all endpoints have `tags=["cameras"]` for grouping
**And** Swagger UI groups endpoints by tag
**And** summaries are concise (1-5 words)

**Prerequisites:** P14-7.5

**Technical Notes:**
- Pattern: `@router.post("/", summary="Create camera", tags=["cameras"])`
- Files: All routers in `backend/app/api/v1/`
- This is documentation improvement - no behavior change
- Estimated: 30+ endpoints to update

---

## Epic P14-8: Testing & Documentation Polish

**Goal:** Final polish on testing infrastructure and documentation to complete the phase.

**Backlog Items:** IMP-049, IMP-052, IMP-054

### Story P14-8.1: Add Query Parameter Validation

As an **API consumer**,
I want query parameters to be validated,
So that I get clear errors for invalid inputs.

**Acceptance Criteria:**

**Given** several query parameter issues exist
**When** validation is added
**Then** clear error messages are returned

Issues to fix:
1. Missing min validation on `limit` (should be >= 1)
2. Inconsistent defaults (`notifications.py:64` limit=20, others vary)
3. Date filtering uses `fromisoformat()` without helpful errors
4. No sorting parameters on list endpoints

**And** `Query(ge=1, le=100)` constraints are added
**And** defaults are standardized (limit=50 everywhere)
**And** date parsing errors return helpful messages

**Prerequisites:** P14-6.8, P14-7.6

**Technical Notes:**
- Pattern: `limit: int = Query(default=50, ge=1, le=100, description="...")`
- Standardize: Pick default limit (50) and apply everywhere
- Date errors: Catch ValueError, return 422 with format hint

---

### Story P14-8.2: Add Concurrency Tests

As a **developer**,
I want concurrency tests for thread-safe services,
So that race conditions are caught.

**Acceptance Criteria:**

**Given** services use semaphores/locks but lack concurrency tests
**When** tests are added
**Then** concurrent access is verified

Services to test:
1. `snapshot_service.py` - Semaphore exhaustion, queue blocking, timeout under load
2. `event_processor.py` - Async queue stress, contention
3. `websocket_manager.py` - Broadcast ordering, race conditions

**And** tests use `pytest-asyncio` with `asyncio.gather()`
**And** tests verify correct behavior under concurrent load
**And** tests catch potential deadlocks or race conditions

**Prerequisites:** P14-8.1

**Technical Notes:**
- Pattern: Launch 10+ concurrent tasks, verify all complete correctly
- For semaphore: Verify max concurrent = semaphore limit
- For queue: Verify FIFO ordering under load
- Use: `asyncio.gather(*[task() for _ in range(10)])`

---

### Story P14-8.3: Improve Mock Quality

As a **developer**,
I want mocks to validate against real contracts,
So that tests catch API changes.

**Acceptance Criteria:**

**Given** test mocks don't validate against real API contracts
**When** improved
**Then** mocks use `spec` parameter

Issues to fix:
1. `test_protect.py` `make_smart_detect_enum()` - Partial enums
2. AI provider mocks - Missing edge cases
3. Integration tests - Over-mocking

**And** mocks use `Mock(spec=RealClass)` to catch attribute errors
**And** mocks verify method signatures match real implementations
**And** tests fail if real API changes but mock doesn't

**Prerequisites:** P14-8.2

**Technical Notes:**
- Pattern: `mock_client = Mock(spec=RealApiClient)`
- This catches typos in attribute names
- This catches signature changes
- Update existing mocks incrementally

---

## FR Coverage Matrix

| FR | Description | Epic | Story |
|----|-------------|------|-------|
| FR1 | asyncio pattern fix | P14-1 | P14-1.1 |
| FR2 | Debug endpoints removed/secured | P14-1 | P14-1.2 |
| FR3 | Debug endpoints env var | P14-1 | P14-1.2 |
| FR4 | Session context managers | P14-2 | P14-2.1 |
| FR5 | WebhookLog FK constraint | P14-2 | P14-2.2 |
| FR6 | Events compound index | P14-2 | P14-2.3 |
| FR7 | Entities name index | P14-2 | P14-2.3 |
| FR8 | Devices index | P14-2 | P14-2.3 |
| FR9 | APIKeys indexes | P14-2 | P14-2.3 |
| FR10 | PairingCodes index | P14-2 | P14-2.3 |
| FR11 | DELETE 204 status | P14-2 | P14-2.4 |
| FR12 | UUID validation | P14-2 | P14-2.5 |
| FR13 | UUID 422 errors | P14-2 | P14-2.5 |
| FR14 | Rate limiting | P14-2 | P14-2.6 |
| FR15 | 429 Retry-After | P14-2 | P14-2.6 |
| FR16 | protect_service tests | P14-3 | P14-3.1 |
| FR17 | protect_event_handler tests | P14-3 | P14-3.2 |
| FR18 | snapshot_service tests | P14-3 | P14-3.3 |
| FR19 | reprocessing_service tests | P14-3 | P14-3.4 |
| FR20 | websocket_manager tests | P14-3 | P14-3.5 |
| FR21 | api_key_service tests | P14-3 | P14-3.6 |
| FR22 | Test parametrization | P14-3 | P14-3.7 |
| FR23 | Shared fixtures | P14-3 | P14-3.8 |
| FR24 | E2E tests | P14-3 | P14-3.10 |
| FR25 | API route tests | P14-3 | P14-3.9 |
| FR26 | No console.log | P14-4 | P14-4.1 |
| FR27 | Test fixture types | P14-4 | P14-4.2 |
| FR28 | TunnelSettings test | P14-4 | P14-4.3 |
| FR29 | Shared test factories | P14-4 | P14-4.4 |
| FR30 | No unused test imports | P14-4 | P14-4.5 |
| FR31 | No unused component imports | P14-4 | P14-4.6 |
| FR32 | setState patterns | P14-4 | P14-4.7 |
| FR33 | SortIcon extraction | P14-4 | P14-4.8 |
| FR34 | @singleton decorator | P14-5 | P14-5.1 |
| FR35 | Singletons migrated | P14-5 | P14-5.3 |
| FR36 | Backoff utility | P14-5 | P14-5.2 |
| FR37 | Backoff migrated | P14-5 | P14-5.4 |
| FR38 | back_populates pattern | P14-5 | P14-5.5 |
| FR39 | Float constraints | P14-5 | P14-5.6 |
| FR40 | Timezone consistency | P14-5 | P14-5.7 |
| FR41 | API response format | P14-5 | P14-5.8 |
| FR42 | Notification relationships | P14-5 | P14-5.9 |
| FR43 | JSON error logging | P14-5 | P14-5.10 |
| FR44 | Entity adjustments context | P14-6 | P14-6.1 |
| FR45 | Parallel queries | P14-6 | P14-6.2 |
| FR46 | Async DB queries | P14-6 | P14-6.3 |
| FR47 | 80ms timeout | P14-6 | P14-6.4 |
| FR48 | Cache optimization | P14-6 | P14-6.5 |
| FR49 | Pattern extraction | P14-6 | P14-6.6 |
| FR50 | VIP/blocked context | P14-6 | P14-6.7 |
| FR51 | Context metrics | P14-6 | P14-6.8 |
| FR52 | BackupRestore alt text | P14-7 | P14-7.1 |
| FR53 | next/image component | P14-7 | P14-7.2 |
| FR54 | Stricter TypeScript | P14-7 | P14-7.3 |
| FR55 | Hook test coverage | P14-7 | P14-7.4 |
| FR56 | React Query DevTools | P14-7 | P14-7.5 |
| FR57 | OpenAPI docs | P14-7 | P14-7.6 |
| FR58 | Query validation | P14-8 | P14-8.1 |
| FR59 | Concurrency tests | P14-8 | P14-8.2 |
| FR60 | Mock quality | P14-8 | P14-8.3 |

**Coverage: 60/60 FRs mapped to stories (100%)**

---

## Summary

Phase 14 decomposes into **53 stories** across **8 epics**:

| Epic | Stories | Effort | Focus |
|------|---------|--------|-------|
| P14-1: Critical Security | 2 | 1 day | MUST BE FIRST |
| P14-2: Backend Quality | 6 | 8 days | Patterns & standards |
| P14-3: Backend Testing | 10 | 15 days | 85% coverage target |
| P14-4: Frontend Quality | 8 | 5 days | Clean tests & patterns |
| P14-5: Standardization | 10 | 8 days | Consistent code |
| P14-6: MCP Context | 8 | 10 days | AI accuracy boost |
| P14-7: Frontend Enhancements | 6 | 6 days | A11y, perf, DX |
| P14-8: Testing Polish | 3 | 5 days | Final validation |

**Total: 53 stories | ~58 days effort | 4-5 weeks with parallelization**

### Implementation Order

1. **P14-1** (Days 1-2) - Critical security fixes FIRST
2. **P14-2** (Days 3-5) - Backend patterns (enables P14-3, P14-5)
3. **P14-4** (Days 6-8) - Frontend quality (parallel track)
4. **P14-5** (Days 9-13) - Standardization
5. **P14-6** (Days 14-18) - MCP enhancements
6. **P14-3** (Days 19-25) - Backend testing
7. **P14-7** (Days 26-28) - Frontend enhancements
8. **P14-8** (Days 29-30) - Final polish

---

_For implementation: Use the `create-story` workflow to generate individual story implementation plans from this epic breakdown._

_This is a technical debt phase - no UX design needed. Architecture decisions are already documented in the backlog items and MCP architecture review._
