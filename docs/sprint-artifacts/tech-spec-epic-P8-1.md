# Epic Technical Specification: Bug Fixes & Stability

Date: 2025-12-20
Author: Brent
Epic ID: P8-1
Status: Draft

---

## Overview

Epic P8-1 addresses three critical bugs affecting core ArgusAI functionality: the re-analyse function throwing errors, the installation script failing on non-ARM64 systems, and push notifications only working once. These bugs were identified through user reports and tracked in the backlog (BUG-005, BUG-006, BUG-007). Resolving these issues is essential for system reliability and user trust before proceeding with Phase 8 feature enhancements.

This epic has no dependencies on other Phase 8 work and should be completed first to establish a stable foundation for subsequent development.

## Objectives and Scope

### In Scope

- **P8-1.1**: Debug and fix the re-analyse endpoint/frontend call that triggers AI re-analysis of event descriptions
- **P8-1.2**: Update installation script to detect CPU architecture and use appropriate paths/dependencies for x86_64/amd64 systems
- **P8-1.3**: Investigate and fix push notification service worker/subscription persistence to enable notifications for all events

### Out of Scope

- New features or enhancements (covered in P8-2 through P8-4)
- Performance optimizations beyond fixing the bugs
- Refactoring unrelated code
- Adding new tests beyond those needed to verify bug fixes

## System Architecture Alignment

### Components Referenced

| Component | Location | Bug Affected |
|-----------|----------|--------------|
| Re-analyse API endpoint | `backend/app/api/v1/events.py` | P8-1.1 |
| AI Service | `backend/app/services/ai_service.py` | P8-1.1 |
| API Client | `frontend/lib/api-client.ts` | P8-1.1 |
| Installation Script | `install.sh` | P8-1.2 |
| Service Worker | `frontend/public/sw.js` | P8-1.3 |
| Push Notification Service | `backend/app/services/push_notification_service.py` | P8-1.3 |
| Event Processor | `backend/app/services/event_processor.py` | P8-1.3 |

### Architecture Constraints

- No changes to database schema required
- No new dependencies required
- Must maintain backwards compatibility
- Must work with existing FastAPI + Next.js stack

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Changes Required |
|----------------|----------------|------------------|
| `events.py` (API) | Handle `/api/v1/events/{id}/reanalyze` endpoint | Debug error handling, verify thumbnail passing |
| `ai_service.py` | Process images through AI providers | Verify image preprocessing for re-analysis |
| `api-client.ts` | Frontend API calls | Fix error handling, async/await issues |
| `install.sh` | System installation | Add architecture detection, conditional paths |
| `sw.js` | Service worker for push | Fix subscription persistence |
| `push_notification_service.py` | Send push notifications | Verify subscription handling, VAPID consistency |
| `event_processor.py` | Process events pipeline | Ensure push called for every qualifying event |

### Data Models and Contracts

**No schema changes required.** Existing models are sufficient:

```python
# Existing Event model fields used
class Event:
    id: UUID
    thumbnail_path: Optional[str]
    description: Optional[str]
    description_retry_needed: bool  # Flag for re-analysis
```

```typescript
// Existing PushSubscription interface
interface PushSubscription {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}
```

### APIs and Interfaces

#### P8-1.1: Re-analyse Endpoint

**Existing Endpoint (to be debugged):**
```
POST /api/v1/events/{event_id}/reanalyze

Request: None (event_id in path)

Response (Success - 200):
{
  "id": "uuid",
  "description": "New AI-generated description...",
  "confidence_score": 0.92,
  "updated_at": "2025-12-20T12:00:00Z"
}

Response (Error - 4xx/5xx):
{
  "detail": "Error message explaining failure"
}
```

**Investigation Points:**
1. Check if thumbnail exists and is accessible
2. Verify AI service receives valid image data
3. Check for timeout issues with AI providers
4. Verify response parsing and database update

#### P8-1.2: Installation Script

**No API changes.** Script modifications:

```bash
# Architecture detection (to be added)
ARCH=$(uname -m)
OS=$(uname -s)

# Conditional Homebrew paths
if [ "$OS" = "Darwin" ]; then
  if [ "$ARCH" = "arm64" ]; then
    BREW_PREFIX="/opt/homebrew"
  else
    BREW_PREFIX="/usr/local"
  fi
fi
```

#### P8-1.3: Push Notification Flow

**Existing flow (to be debugged):**
```
1. User subscribes → POST /api/v1/push/subscribe
2. Subscription stored in database
3. Event created → event_processor.py
4. Push service called → push_notification_service.py
5. Notification sent via WebPush
```

**Investigation Points:**
1. Subscription validity after first notification
2. Service worker registration persistence
3. VAPID key consistency between sends
4. Browser throttling limits

### Workflows and Sequencing

#### P8-1.1: Re-analyse Flow (Current → Fixed)

```
Current (Broken):
User clicks "Re-analyse" → Frontend call → [ERROR] → User sees error

Fixed:
User clicks "Re-analyse"
  → Show loading indicator
  → POST /api/v1/events/{id}/reanalyze
  → Backend loads event + thumbnail
  → Send to AI service
  → Update event description
  → Return success response
  → Frontend updates event card
  → Show success toast
```

#### P8-1.3: Push Notification Flow (Current → Fixed)

```
Current (Broken):
Event 1 → Push sent ✓
Event 2 → Push NOT sent ✗
Event 3 → Push NOT sent ✗

Fixed:
Event 1 → Validate subscription → Send push ✓
Event 2 → Validate subscription → Send push ✓
Event 3 → Validate subscription → Send push ✓
(Subscription persists across all events)
```

---

## Non-Functional Requirements

### Performance

| Requirement | Target | Source |
|-------------|--------|--------|
| Re-analyse response time | <10 seconds (AI processing) | PRD: <5s p95 latency |
| Installation script | <5 minutes total | User expectation |
| Push notification delivery | <2 seconds from event | PRD: Real-time alerts |

### Security

- **P8-1.1**: No security changes; existing authentication applies
- **P8-1.2**: Installation script must not store credentials; use environment variables
- **P8-1.3**: VAPID keys must remain consistent; push subscriptions encrypted at rest

### Reliability/Availability

- **P8-1.1**: Re-analyse must handle AI provider failures gracefully with clear error messages
- **P8-1.2**: Installation must detect failures and provide rollback guidance
- **P8-1.3**: Push failures should be logged and retried (up to 3 attempts)

### Observability

| Signal | Type | Purpose |
|--------|------|---------|
| `reanalyze_request_count` | Counter | Track re-analyse usage |
| `reanalyze_error_count` | Counter | Track failures |
| `push_notification_sent` | Counter | Track successful pushes |
| `push_notification_failed` | Counter | Track push failures |
| `installation_arch` | Log | Track platform distribution |

---

## Dependencies and Integrations

### Backend Dependencies (No Changes)

```
# requirements.txt - existing
fastapi>=0.115.0
sqlalchemy>=2.0.0
opencv-python>=4.12.0
pywebpush>=1.14.0  # Push notifications
```

### Frontend Dependencies (No Changes)

```json
// package.json - existing
{
  "next": "15.x",
  "react": "19.x",
  "@tanstack/react-query": "5.x"
}
```

### External Integrations

| Integration | Purpose | Bug Affected |
|-------------|---------|--------------|
| OpenAI/Grok/Claude/Gemini | AI re-analysis | P8-1.1 |
| Web Push (VAPID) | Push notifications | P8-1.3 |
| Homebrew (macOS) | Installation | P8-1.2 |
| apt-get (Linux) | Installation | P8-1.2 |

---

## Acceptance Criteria (Authoritative)

### P8-1.1: Fix Re-Analyse Function Error

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| AC1.1 | Given an event with a thumbnail, when user clicks re-analyse, then AI generates new description | Yes |
| AC1.2 | Given re-analysis in progress, when processing, then loading indicator is displayed | Yes |
| AC1.3 | Given successful re-analysis, then event card updates with new description | Yes |
| AC1.4 | Given successful re-analysis, then success toast notification is shown | Yes |
| AC1.5 | Given re-analysis failure, then clear error message is displayed | Yes |
| AC1.6 | Given re-analysis failure, then error is logged with stack trace | Yes |
| AC1.7 | Given previous failure, when user retries, then retry works without page refresh | Yes |

### P8-1.2: Fix Installation Script for Non-ARM64 Systems

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| AC2.1 | Given x86_64 macOS system, when running install.sh, then script completes successfully | Yes |
| AC2.2 | Given x86_64 Linux system, when running install.sh, then script completes successfully | Yes |
| AC2.3 | Given ARM64 system, when running install.sh, then existing behavior preserved | Yes |
| AC2.4 | Given any system, when script runs, then correct Homebrew/pip paths used | Yes |
| AC2.5 | Given architecture detection, when script starts, then architecture logged | Yes |

### P8-1.3: Fix Push Notifications Only Working Once

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| AC3.1 | Given push enabled, when first event occurs, then notification received | Yes |
| AC3.2 | Given push enabled, when second event occurs, then notification received | Yes |
| AC3.3 | Given push enabled, when tenth event occurs, then notification received | Yes |
| AC3.4 | Given subscription, when notification sent, then subscription remains valid | Yes |
| AC3.5 | Given push failure, when retry attempted, then notification eventually delivered | Yes |
| AC3.6 | Given any notification, when sent, then delivery status logged | Yes |

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC1.1 | APIs: Re-analyse | events.py, ai_service.py | Integration test with mock AI |
| AC1.2 | Workflows: Re-analyse | EventCard.tsx | Component test for loading state |
| AC1.3 | Workflows: Re-analyse | EventCard.tsx, api-client.ts | E2E test re-analyse flow |
| AC1.4 | Workflows: Re-analyse | toast component | Component test for success toast |
| AC1.5 | APIs: Re-analyse | events.py | Unit test error responses |
| AC1.6 | Observability | events.py | Verify log output on error |
| AC1.7 | Workflows: Re-analyse | EventCard.tsx | Manual test retry after failure |
| AC2.1 | APIs: Install | install.sh | Run on x86_64 Mac (CI or manual) |
| AC2.2 | APIs: Install | install.sh | Run on x86_64 Linux (CI) |
| AC2.3 | APIs: Install | install.sh | Run on ARM64 Mac (existing CI) |
| AC2.4 | APIs: Install | install.sh | Assert paths based on arch |
| AC2.5 | Observability | install.sh | Check log output for arch |
| AC3.1-3.3 | Workflows: Push | push_notification_service.py | Integration test multiple events |
| AC3.4 | Data Models | push_notification_service.py | Unit test subscription persistence |
| AC3.5 | Reliability | push_notification_service.py | Unit test retry logic |
| AC3.6 | Observability | push_notification_service.py | Verify log output |

---

## Risks, Assumptions, Open Questions

### Risks

| ID | Risk | Impact | Mitigation |
|----|------|--------|------------|
| R1 | Re-analyse bug may be in AI provider, not our code | High | Test with multiple providers |
| R2 | Push issue may be browser-specific | Medium | Test Chrome, Firefox, Safari |
| R3 | Installation script may have edge cases on specific distros | Medium | Document supported platforms |

### Assumptions

| ID | Assumption |
|----|------------|
| A1 | Re-analyse endpoint exists at `/api/v1/events/{id}/reanalyze` |
| A2 | Push subscriptions are stored in database |
| A3 | Service worker is at `frontend/public/sw.js` |
| A4 | Installation script is `install.sh` in project root |

### Open Questions

| ID | Question | Owner | Status |
|----|----------|-------|--------|
| Q1 | Is re-analyse error consistent or intermittent? | Dev | To investigate |
| Q2 | Which browsers have push notification issues? | Dev | To investigate |
| Q3 | Are there any x86_64 users currently blocked? | PM | To confirm |

---

## Test Strategy Summary

### Test Levels

| Level | Scope | Framework |
|-------|-------|-----------|
| Unit | Individual functions | pytest (backend), vitest (frontend) |
| Integration | API endpoints | pytest with TestClient |
| Component | React components | React Testing Library |
| E2E | Full user flows | Manual testing (Playwright future) |

### Coverage Requirements

- All acceptance criteria must have at least one test
- Bug fixes must include regression tests
- Error paths must be tested

### Test Cases by Story

**P8-1.1 (Re-analyse):**
- Unit: `test_reanalyze_endpoint_success`
- Unit: `test_reanalyze_endpoint_no_thumbnail`
- Unit: `test_reanalyze_endpoint_ai_failure`
- Integration: `test_reanalyze_updates_event`
- Component: `test_reanalyze_button_loading_state`

**P8-1.2 (Installation):**
- Manual: Run on x86_64 macOS
- Manual: Run on x86_64 Ubuntu
- CI: Add matrix build for multiple architectures

**P8-1.3 (Push):**
- Unit: `test_push_subscription_persists`
- Unit: `test_push_retry_on_failure`
- Integration: `test_multiple_events_trigger_push`
- Manual: Verify in browser DevTools

### Edge Cases

- Re-analyse with no thumbnail
- Re-analyse when AI provider is down
- Push when subscription expired
- Installation on unsupported platform
- Installation with missing dependencies
