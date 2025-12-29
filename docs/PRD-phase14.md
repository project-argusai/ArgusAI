# ArgusAI - Product Requirements Document

**Author:** Brent
**Date:** 2025-12-29
**Version:** 1.0
**Phase:** 14 - Technical Excellence & Quality Foundation

---

## Executive Summary

Phase 14 is ArgusAI's **quality renaissance** - a comprehensive technical debt paydown and quality infrastructure investment. After 13 phases of rapid feature development, the codebase has accumulated 56 open backlog items spanning security vulnerabilities, missing test coverage, code quality issues, and architectural improvements. This phase addresses them systematically.

This is not a feature phase. Phase 14 is about **building the foundation for sustainable, high-velocity development** by eliminating technical debt, establishing comprehensive test coverage, improving code consistency, and enhancing the MCP context system that powers AI accuracy.

### What Makes This Special

Phase 14 transforms ArgusAI from a "feature-complete but fragile" state to a **production-hardened, maintainable platform**. The investment in test coverage, security fixes, and code standardization will:

1. **Reduce bug escape rate** - Comprehensive tests catch regressions before production
2. **Accelerate future development** - Clean code patterns and shared utilities reduce boilerplate
3. **Improve AI accuracy** - MCP context system enhancements leverage 120 unused entity adjustments
4. **Eliminate security risks** - Critical debug endpoints and rate limiting issues resolved
5. **Enable confident refactoring** - Test coverage permits aggressive optimization

This phase represents **~3-4 weeks of focused technical work** across 56 items organized into 8 epics.

---

## Project Classification

**Technical Type:** Full-Stack Web Application (Python/FastAPI + Next.js)
**Domain:** Home Security / IoT / AI Vision
**Complexity:** High (cross-cutting concerns, security-sensitive changes, extensive testing)

This phase is **purely technical** - no new user-facing features. All work improves internal quality, security, performance, and maintainability.

---

## Success Criteria

### Primary Success Metrics

1. **Test Coverage**: Achieve 85%+ line coverage on backend services (currently ~60%)
2. **Zero Critical Issues**: All P1 security/code quality issues resolved
3. **CI Stability**: All tests pass consistently in CI (no flaky tests)
4. **Performance Baseline**: MCP context latency reduced from 12ms to <5ms via parallel queries
5. **Code Consistency**: 100% of singleton services use new `@singleton` decorator
6. **Security Audit**: Pass security review with no critical/high findings

### Quality Gates

- All 2 P1 critical issues (TD-011, TD-023) resolved before any other work
- Frontend test fixtures updated and all 806+ tests passing
- Backend services with 0% coverage achieve minimum 70% coverage
- All database session management uses context managers (TD-012)
- API rate limiting implemented on all public endpoints (TD-024)

---

## Product Scope

### MVP - Phase 14 Core Deliverables

Phase 14 addresses **56 open backlog items** organized into 8 epics:

**Epic P14-1: Critical Security & Code Fixes (P1)** - 2 items
- TD-011: Fix asyncio.run() misuse in MQTT service
- TD-023: Remove or secure debug endpoints exposing secrets

**Epic P14-2: Backend Code Quality (P2)** - 8 items
- TD-012: Standardize database session management (15+ instances)
- TD-015: Add missing FK constraint on WebhookLog
- TD-016: Add missing database indexes
- TD-020: Fix DELETE endpoints returning wrong status code
- TD-021: Add UUID validation on path parameters
- TD-024: Implement API rate limiting

**Epic P14-3: Backend Testing Infrastructure (P2-P3)** - 12 items
- TD-026: Add unit tests for protect_service.py
- TD-027: Add unit tests for protect_event_handler.py
- TD-028: Add unit tests for snapshot_service.py
- TD-029: Add unit tests for reprocessing_service.py
- TD-030: Add unit tests for websocket_manager.py
- TD-031: Add unit tests for api_key_service.py
- TD-032: Increase test parametrization adoption
- TD-033: Consolidate test fixture definitions
- TD-034: Add end-to-end integration tests
- TD-035: Add missing API route tests (12 modules)

**Epic P14-4: Frontend Code Quality (P2-P3)** - 8 items
- TD-006: Remove debug console.log in API client
- TD-007: Fix test type mismatches (30+ fixtures)
- TD-008: Fix failing TunnelSettings test
- TD-009: Create shared test fixtures factory
- TD-010: Clean up unused test imports
- IMP-040: Clean up unused component imports
- IMP-041: Fix setState-in-useEffect anti-patterns
- IMP-042: Extract SortIcon component outside render

**Epic P14-5: Code Standardization (P3)** - 10 items
- TD-013: Reduce singleton pattern boilerplate (50+ instances)
- TD-014: Consolidate exponential backoff logic (4 implementations)
- TD-017: Fix backref vs back_populates inconsistency
- TD-018: Add missing check constraints on float columns
- TD-019: Fix timestamp timezone handling inconsistency
- TD-022: Standardize API response wrapper format
- TD-025: Add missing relationship objects in Notification model
- IMP-050: Create @singleton decorator utility
- IMP-051: Create shared exponential backoff utility
- IMP-053: Improve JSON parse error handling

**Epic P14-6: MCP Context System Enhancement (P2-P3)** - 8 items
- IMP-055: Integrate entity adjustments context (120 unused records)
- IMP-056: Implement parallel query execution
- IMP-057: Fix async/sync database query mismatch
- IMP-058: Add query timeout enforcement (80ms)
- IMP-059: Investigate low cache hit ratio (9.5%)
- IMP-060: Improve pattern extraction algorithm
- IMP-061: Add VIP/blocked entity context
- IMP-062: Add context metrics dashboard

**Epic P14-7: Frontend Enhancements (P3-P4)** - 6 items
- IMP-043: Add alt text to images in BackupRestore
- IMP-044: Replace `<img>` with next/image component
- IMP-045: Add stricter TypeScript checks
- IMP-046: Increase test coverage for hooks (5/18 covered)
- IMP-047: Add React Query DevTools
- IMP-048: Add missing OpenAPI summaries and tags

**Epic P14-8: Testing & Documentation Polish (P3-P4)** - 2 items
- IMP-049: Add query parameter validation and constraints
- IMP-052: Add concurrency tests for critical services
- IMP-054: Improve mock quality and specifications

### Growth Features (Post-Phase 14)

- Full MCP Protocol (Phase 3) implementation with external client support
- A/B testing framework for context effectiveness
- Performance regression testing in CI
- Mutation testing for test quality validation
- API documentation portal with interactive examples

### Vision (Future)

- 95%+ test coverage with automated coverage gates
- Zero-downtime deployment pipeline
- Automated security scanning in CI
- Performance monitoring dashboard
- Self-healing infrastructure with auto-rollback

---

## Functional Requirements

### Critical Security (Epic P14-1)

- **FR1**: MQTT discovery service uses asyncio.create_task() or run_coroutine_threadsafe() instead of asyncio.run() in sync context
- **FR2**: Debug endpoints `/debug/ai-keys` and `/debug/network` are removed from production builds or require admin authentication
- **FR3**: Debug endpoints are disabled by default via environment variable `DEBUG_ENDPOINTS_ENABLED=false`

### Backend Code Quality (Epic P14-2)

- **FR4**: All database sessions use context manager pattern (`with SessionLocal() as db:`)
- **FR5**: WebhookLog.alert_rule_id has ForeignKey constraint with CASCADE delete
- **FR6**: Events table has compound index on (source_type, timestamp)
- **FR7**: RecognizedEntities.name column has index for LIKE queries
- **FR8**: Devices.pairing_confirmed column has index
- **FR9**: API keys table has indexes on created_by and revoked_by columns
- **FR10**: PairingCodes table has compound index on (device_id, expires_at)
- **FR11**: DELETE endpoints return 204 No Content instead of 200 OK with body
- **FR12**: All UUID path parameters are typed as UUID with proper validation
- **FR13**: Invalid UUIDs return 422 Unprocessable Entity with clear error message
- **FR14**: All API endpoints have rate limiting (configurable per-endpoint)
- **FR15**: Rate limit exceeded returns 429 Too Many Requests with Retry-After header

### Backend Testing (Epic P14-3)

- **FR16**: protect_service.py has unit tests covering test_connection(), WebSocket lifecycle, reconnection backoff, timeout handling, camera discovery caching
- **FR17**: protect_event_handler.py has unit tests covering event type parsing, filter chain evaluation, smart detection filtering, cooldown deduplication, HomeKit integration
- **FR18**: snapshot_service.py has unit tests covering semaphore concurrency, timeout handling, image resizing, base64 encoding, retry logic
- **FR19**: reprocessing_service.py has unit tests covering job status transitions, checkpoint/resume, cancellation, WebSocket progress
- **FR20**: websocket_manager.py has unit tests covering connection lifecycle, message delivery, broadcast routing, cleanup
- **FR21**: api_key_service.py has unit tests covering key generation, validation, encryption, expiration, revocation
- **FR22**: Test parametrization is used for data-driven tests (target: 50+ parametrized tests)
- **FR23**: Shared test fixtures exist in global conftest.py for sample_event, sample_camera, sample_rule, sample_entity
- **FR24**: End-to-end tests exist for: camera capture → motion → AI → alert → webhook flow
- **FR25**: API route tests exist for: auth, api_keys, notifications, mobile_auth modules (security-critical)

### Frontend Code Quality (Epic P14-4)

- **FR26**: API client has no console.log statements in production builds
- **FR27**: All test fixtures match current TypeScript interfaces (ICamera, IEntity, ICorrelatedEvent)
- **FR28**: TunnelSettings test passes with correct apiClient.tunnel.start mock
- **FR29**: Shared test utilities include complete mockCamera, mockEntity, mockController, mockApiClient factories
- **FR30**: No unused imports exist in test files
- **FR31**: No unused imports exist in component files
- **FR32**: No setState calls inside useEffect without proper dependency arrays
- **FR33**: SortIcon component is defined at module scope, not inside render function

### Code Standardization (Epic P14-5)

- **FR34**: @singleton decorator exists in app/utils/decorators.py
- **FR35**: All 50+ singleton services use @singleton decorator instead of manual pattern
- **FR36**: Shared exponential_backoff() utility exists in app/utils/retry.py
- **FR37**: All 4 backoff implementations use shared utility
- **FR38**: All relationship definitions use back_populates pattern (not backref)
- **FR39**: Float columns with ranges have CheckConstraints (ai_confidence, anomaly_score, audio_confidence, audio_threshold)
- **FR40**: All DateTime columns use consistent UTC defaults with timezone=True
- **FR41**: API response format is documented and consistent across all endpoints
- **FR42**: Notification model has event and rule relationship objects
- **FR43**: JSON parse errors are logged with context (rule_id, field name) instead of silently returning empty dict

### MCP Context Enhancement (Epic P14-6)

- **FR44**: EntityAdjustment data (120 records) is included in MCP context for AI prompts
- **FR45**: MCP context queries execute in parallel using asyncio.gather()
- **FR46**: MCP database queries use async SQLAlchemy session or run_in_executor()
- **FR47**: MCP context gathering has 80ms hard timeout with fail-open behavior
- **FR48**: MCP cache strategy is optimized for higher hit ratio (target: >50%)
- **FR49**: Pattern extraction uses improved algorithm (TF-IDF or domain-specific stop words)
- **FR50**: VIP and blocked entity flags are included in EntityContext
- **FR51**: Settings page includes Context Metrics tab showing hit rates, latency, component availability

### Frontend Enhancements (Epic P14-7)

- **FR52**: All `<img>` elements in BackupRestore.tsx have meaningful alt attributes
- **FR53**: Native `<img>` elements are replaced with next/image where appropriate (CameraForm, RecentActivity, EntityCreateModal, NotificationDropdown)
- **FR54**: TypeScript noUncheckedIndexedAccess and exactOptionalPropertyTypes are enabled (or documented as intentionally disabled)
- **FR55**: All 18 hooks have test coverage (currently 5/18)
- **FR56**: React Query DevTools is available in development builds
- **FR57**: All API endpoints have OpenAPI summary and tags for Swagger UI

### Testing & Documentation (Epic P14-8)

- **FR58**: Query parameters have validation constraints (limit >= 1, max limits, etc.)
- **FR59**: Concurrency tests exist for snapshot_service (semaphore), event_processor (queue), websocket_manager (broadcast)
- **FR60**: Test mocks validate against real API contracts (mock.spec usage)

---

## Non-Functional Requirements

### Security

- **NFR1**: All P1 security issues (TD-011, TD-023) are resolved before any other work begins
- **NFR2**: Debug endpoints return 404 in production (not 401/403 which confirms existence)
- **NFR3**: Rate limiting persists across server restarts (stored in Redis or similar)
- **NFR4**: Rate limit configuration is per-endpoint and per-authentication type (API key vs session)

### Performance

- **NFR5**: MCP context parallel queries reduce latency from 12ms to <5ms
- **NFR6**: Database indexes reduce query time for event filtering by 50%+
- **NFR7**: Rate limiting adds <5ms overhead per request
- **NFR8**: @singleton decorator has zero performance overhead vs manual pattern

### Reliability

- **NFR9**: All database session leaks are eliminated (verified by connection pool monitoring)
- **NFR10**: Context manager pattern prevents connection leaks on exceptions
- **NFR11**: MCP timeout ensures AI prompts are never blocked waiting for context

### Testing

- **NFR12**: Backend test coverage reaches 85%+ (up from ~60%)
- **NFR13**: Frontend test coverage reaches 80%+ for components
- **NFR14**: All hooks have minimum 70% test coverage
- **NFR15**: CI runs complete in <10 minutes
- **NFR16**: No flaky tests (zero failures in 10 consecutive runs)

### Code Quality

- **NFR17**: ESLint passes with zero warnings (not just errors)
- **NFR18**: TypeScript compiles with zero type errors
- **NFR19**: All singleton services follow identical pattern via decorator
- **NFR20**: All backoff implementations have identical behavior via shared utility

### Documentation

- **NFR21**: All API endpoints have OpenAPI documentation with examples
- **NFR22**: Code changes include inline documentation for complex logic
- **NFR23**: Architecture decisions are documented in ADRs

---

## Technical Architecture

### Epic Dependencies

```
P14-1 (Critical) ─────────────────────────────────────────────────────────────► MUST BE FIRST
         │
         ▼
P14-2 (Backend Quality) ◄──────────────────────────────────────────────────────┐
         │                                                                      │
         ├──────────► P14-3 (Backend Testing) ──► Depends on P14-2 fixtures     │
         │                                                                      │
         └──────────► P14-5 (Standardization) ──► Uses P14-2 patterns          │
                                                                                │
P14-4 (Frontend Quality) ◄─────────────────────────────────────────────────────┤
         │                                                                      │
         └──────────► P14-7 (Frontend Enhancements)                            │
                                                                                │
P14-6 (MCP Context) ◄───────────────────────────────────────────────────────────┘
         │                     (Independent but benefits from P14-2 patterns)
         ▼
P14-8 (Testing Polish) ──► Final validation after all other work
```

### Recommended Implementation Order

1. **P14-1: Critical Security** (Days 1-2) - BLOCKING for all other work
2. **P14-2: Backend Code Quality** (Days 3-5) - Establishes patterns
3. **P14-5: Code Standardization** (Days 6-8) - Uses P14-2 patterns
4. **P14-4: Frontend Quality** (Days 9-11) - Parallel track
5. **P14-6: MCP Context** (Days 12-15) - Major AI accuracy investment
6. **P14-3: Backend Testing** (Days 16-20) - Builds on clean code
7. **P14-7: Frontend Enhancements** (Days 21-23)
8. **P14-8: Testing Polish** (Days 24-25) - Final validation

**Estimated Duration:** 4-5 weeks (can be compressed with parallel work)

---

## Backlog Item Details

### P1 Critical (Must Fix First)

| ID | Title | Risk | Effort |
|----|-------|------|--------|
| TD-011 | Fix asyncio.run() Misuse | Runtime crashes in async context | 0.5 days |
| TD-023 | Remove Debug Endpoints | Credential exposure | 0.5 days |

### P2 High Priority

| ID | Title | Category | Effort |
|----|-------|----------|--------|
| TD-008 | Fix Failing TunnelSettings Test | Testing | 0.5 days |
| TD-012 | Standardize Database Session Management | Code Quality | 2 days |
| TD-015 | Add Missing FK Constraint | Data Integrity | 0.5 days |
| TD-016 | Add Missing Database Indexes | Performance | 1 day |
| TD-020 | Fix DELETE Status Codes | API Standards | 0.5 days |
| TD-021 | Add UUID Validation | Input Validation | 1 day |
| TD-024 | Implement Rate Limiting | Security | 2 days |
| TD-026 | Tests for protect_service.py | Testing | 1.5 days |
| TD-027 | Tests for protect_event_handler.py | Testing | 2 days |
| TD-028 | Tests for snapshot_service.py | Testing | 1.5 days |
| IMP-041 | Fix setState-in-useEffect | React Patterns | 1 day |
| IMP-042 | Extract SortIcon Component | React Patterns | 0.5 days |
| IMP-055 | MCP: Integrate Entity Adjustments | MCP/AI | 2 days |
| IMP-056 | MCP: Parallel Query Execution | Performance | 1 day |
| IMP-057 | MCP: Fix Async/Sync Mismatch | Code Quality | 1.5 days |

### P3 Medium Priority

| ID | Title | Category | Effort |
|----|-------|----------|--------|
| TD-006 | Remove Debug Console.log | Code Quality | 0.25 days |
| TD-007 | Fix Test Type Mismatches | Testing | 1.5 days |
| TD-009 | Create Shared Test Fixtures | Testing | 1 day |
| TD-010 | Clean Up Unused Test Imports | Code Quality | 0.25 days |
| TD-013 | Reduce Singleton Boilerplate | Code Quality | 2 days |
| TD-014 | Consolidate Backoff Logic | Code Quality | 1 day |
| TD-017 | Fix backref Inconsistency | Code Quality | 0.5 days |
| TD-018 | Add Check Constraints | Data Integrity | 0.5 days |
| TD-019 | Fix Timezone Handling | Code Quality | 1 day |
| TD-022 | Standardize API Response Format | API Standards | 1 day |
| TD-025 | Add Notification Relationships | Code Quality | 0.25 days |
| TD-029 | Tests for reprocessing_service.py | Testing | 1 day |
| TD-030 | Tests for websocket_manager.py | Testing | 1 day |
| TD-031 | Tests for api_key_service.py | Testing | 1 day |
| TD-032 | Increase Test Parametrization | Testing | 1.5 days |
| TD-033 | Consolidate Test Fixtures | Testing | 1 day |
| TD-035 | Add Missing API Route Tests | Testing | 3 days |
| IMP-040 | Clean Up Component Imports | Code Quality | 0.25 days |
| IMP-043 | Add Alt Text to Images | Accessibility | 0.25 days |
| IMP-044 | Replace img with next/image | Performance | 0.5 days |
| IMP-046 | Test Coverage for Hooks | Testing | 2 days |
| IMP-048 | Add OpenAPI Summaries | Documentation | 1 day |
| IMP-049 | Add Query Parameter Validation | Input Validation | 1 day |
| IMP-052 | Add Concurrency Tests | Testing | 1.5 days |
| IMP-054 | Improve Mock Quality | Testing | 1 day |
| IMP-058 | MCP: Query Timeout | Performance | 0.5 days |
| IMP-059 | MCP: Cache Hit Ratio | Performance | 1 day |
| IMP-060 | MCP: Pattern Extraction | MCP/AI | 1.5 days |
| IMP-061 | MCP: VIP/Blocked Context | MCP/AI | 0.5 days |

### P4 Low Priority

| ID | Title | Category | Effort |
|----|-------|----------|--------|
| TD-034 | Add E2E Integration Tests | Testing | 3 days |
| IMP-045 | Stricter TypeScript Checks | Code Quality | 1.5 days |
| IMP-047 | Add React Query DevTools | DevEx | 0.25 days |
| IMP-050 | Create @singleton Decorator | Code Quality | 0.5 days |
| IMP-051 | Create Backoff Utility | Code Quality | 0.5 days |
| IMP-053 | Improve JSON Error Handling | Logging | 0.5 days |
| IMP-062 | MCP: Context Metrics Dashboard | MCP/AI | 2 days |

---

## Epic Breakdown Summary

| Epic | Items | Priority | Effort | Dependencies |
|------|-------|----------|--------|--------------|
| P14-1: Critical Security | 2 | P1 | 1 day | None (FIRST) |
| P14-2: Backend Quality | 8 | P2 | 8 days | P14-1 |
| P14-3: Backend Testing | 12 | P2-P3 | 15 days | P14-2 |
| P14-4: Frontend Quality | 8 | P2-P3 | 5 days | P14-1 |
| P14-5: Standardization | 10 | P3 | 8 days | P14-2 |
| P14-6: MCP Context | 8 | P2-P3 | 10 days | P14-2 |
| P14-7: Frontend Enhancements | 6 | P3-P4 | 6 days | P14-4 |
| P14-8: Testing Polish | 3 | P3-P4 | 5 days | All others |

**Total: 56 items | ~58 days effort | 4-5 weeks with parallelization**

---

## Risk Assessment

### High Risks

1. **Scope Creep**: 56 items is ambitious; strict prioritization required
   - Mitigation: P1 and P2 items are non-negotiable; P3-P4 can be deferred

2. **Test Breakage**: Code changes may break existing tests
   - Mitigation: Run full test suite after each PR; no merging with failures

3. **Performance Regression**: Code standardization may impact performance
   - Mitigation: Benchmark critical paths before/after changes

### Medium Risks

1. **MCP Changes Impact AI Quality**: Context changes may affect descriptions
   - Mitigation: Compare description quality before/after on sample events

2. **Rate Limiting Too Aggressive**: May break legitimate use cases
   - Mitigation: Start with generous limits; monitor and adjust

---

## References

- MCP Architecture Review: docs/mcp-architecture-review.md
- Backlog: docs/backlog.md
- Architecture: docs/architecture.md
- Test Design: docs/test-design-system.md

---

## Summary

Phase 14 is ArgusAI's **technical excellence initiative**, addressing 56 accumulated technical debt items across 8 epics:

| Epic | Value Delivered |
|------|-----------------|
| P14-1: Critical Security | Eliminate credential exposure and runtime crash risks |
| P14-2: Backend Quality | Prevent connection leaks, add indexes, fix API standards |
| P14-3: Backend Testing | 85%+ test coverage on core services |
| P14-4: Frontend Quality | Clean tests, proper patterns, no debug code |
| P14-5: Standardization | Consistent patterns across 50+ services |
| P14-6: MCP Context | 4x faster context, entity adjustment learning |
| P14-7: Frontend Enhancements | Accessibility, performance, developer experience |
| P14-8: Testing Polish | Integration tests, concurrency tests, mock quality |

**60 Functional Requirements** | **23 Non-Functional Requirements** | **8 Epics** | **~56 Stories**

---

_This PRD captures Phase 14 of ArgusAI - Technical Excellence & Quality Foundation_

_Created through collaborative discovery between Brent and AI facilitator on 2025-12-29._
