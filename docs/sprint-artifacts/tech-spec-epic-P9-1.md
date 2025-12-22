# Epic Technical Specification: Critical Bug Fixes

Date: 2025-12-22
Author: Brent
Epic ID: P9-1
Status: Draft

---

## Overview

Epic P9-1 addresses critical bugs that have accumulated in the backlog, focusing on stability and reliability fixes. This epic is P1 priority as it unblocks development work (CI pipeline) and resolves user-impacting issues (push notifications, filter persistence, re-analyse functionality, prompt refinement, and entity separation).

The bugs span multiple system components: GitHub Actions CI, service worker push notifications, Protect camera filter settings, AI re-analysis endpoint, AI-assisted prompt refinement UI, and entity extraction logic for vehicles.

## Objectives and Scope

**In Scope:**
- Fix GitHub Actions CI test failures (BUG-010)
- Fix push notifications only working once (BUG-007)
- Fix Protect camera filter settings not persisting (BUG-008)
- Fix re-analyse function returning error (BUG-005)
- Fix AI-assisted prompt refinement not functional (BUG-009)
- Add save/replace button to prompt refinement modal
- Show AI model in prompt refinement modal
- Fix vehicle entities not separating by make/model (BUG-011)

**Out of Scope:**
- New feature development
- Architecture changes
- Performance optimizations beyond bug fixes
- UI redesigns

## System Architecture Alignment

This epic touches several architectural components from the existing system:

| Component | Files Affected | Changes |
|-----------|---------------|---------|
| CI Pipeline | `.github/workflows/ci.yml` | Fix test configuration |
| Push Service | `backend/app/services/push_service.py` | Fix subscription persistence |
| Service Worker | `frontend/public/sw.js` | Fix notification handling |
| Protect API | `backend/app/api/v1/protect.py` | Fix filter persistence |
| Protect Models | `backend/app/models/protect.py` | Verify filter fields |
| AI Service | `backend/app/services/ai_service.py` | Fix re-analyse, add refinement |
| AI API | `backend/app/api/v1/ai.py` | Fix endpoints |
| Entity Service | `backend/app/services/entity_service.py` | Fix vehicle extraction |
| Settings UI | `frontend/components/settings/` | Fix prompt refinement modal |

---

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Inputs | Outputs |
|---------------|----------------|--------|---------|
| CI Workflow | Run tests on PRs | Push/PR events | Pass/fail status |
| PushService | Send push notifications | Event data | Notification delivery |
| ProtectService | Manage camera filters | Filter settings | Persisted filters |
| AIService | Process AI requests | Event images, prompts | Descriptions |
| EntityService | Extract/match entities | AI descriptions | Entity records |
| PromptRefinementModal | AI-assisted prompt editing | Current prompt, feedback | Refined prompt |

### Data Models and Contracts

**ProtectCameraFilter (verify existing fields):**
```python
class ProtectCameraFilter:
    camera_id: str
    controller_id: UUID
    person_enabled: bool = True
    vehicle_enabled: bool = True
    package_enabled: bool = True
    animal_enabled: bool = True
    ring_enabled: bool = True  # Doorbell ring events
```

**Entity Vehicle Extraction (enhanced):**
```python
class VehicleEntity:
    type: str = "vehicle"
    color: Optional[str]  # white, black, red, blue, silver, gray, green
    make: Optional[str]   # Toyota, Ford, Honda, etc.
    model: Optional[str]  # Camry, F-150, Civic, etc.
    signature: str        # "white-toyota-camry" for matching
```

**PushSubscription (verify persistence):**
```python
class PushSubscription:
    id: UUID
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str
    created_at: datetime
    last_used: datetime  # Should update on each send
```

### APIs and Interfaces

**Existing Endpoints (to fix):**

| Method | Path | Issue | Fix |
|--------|------|-------|-----|
| PUT | `/api/v1/protect/controllers/{id}/cameras/{cam}/filters` | Not persisting | Ensure DB commit |
| POST | `/api/v1/events/{id}/reanalyse` | Returns error | Debug and fix |
| POST | `/api/v1/ai/refine-prompt` | Not being called | Verify frontend calls API |

**Response Contract for Prompt Refinement:**
```json
{
  "suggested_prompt": "string",
  "provider_used": "OpenAI GPT-4o",
  "changes_summary": "string",
  "feedback_samples_used": 25
}
```

### Workflows and Sequencing

**Bug Fix Investigation Flow:**
```
1. Reproduce bug locally
2. Add logging/debugging
3. Identify root cause
4. Implement fix
5. Write regression test
6. Verify fix in staging
7. Deploy
```

**CI Fix Flow:**
```
1. Review failing tests in GitHub Actions logs
2. Run tests locally to reproduce
3. Check for environment differences (versions, env vars)
4. Fix flaky tests or configuration
5. Push fix and verify green build
```

---

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| CI pipeline duration | <10 minutes | GitHub Actions timing |
| Push notification delivery | <2 seconds | Time from event to notification |
| Filter save latency | <500ms | API response time |
| Re-analyse latency | <30 seconds | API response time (AI-dependent) |

### Security

- Push notification subscription tokens must be stored securely
- Filter settings tied to authenticated sessions only
- API endpoints require authentication
- No sensitive data in CI logs

### Reliability/Availability

- Push notifications must work reliably after service worker updates
- Filter settings must survive server restarts
- CI pipeline should have <5% flaky test rate
- Re-analyse should handle AI provider failures gracefully

### Observability

- Add logging for push subscription lifecycle events
- Log filter save operations with before/after values
- Log CI test failures with detailed stack traces
- Log entity extraction with confidence scores

---

## Dependencies and Integrations

### Backend Dependencies (requirements.txt)

```
# Existing - no new dependencies for bug fixes
fastapi>=0.115.0
sqlalchemy>=2.0.0
pywebpush>=1.14.0
openai>=1.3.0
anthropic>=0.17.0
google-generativeai>=0.3.0
```

### Frontend Dependencies (package.json)

```json
{
  "dependencies": {
    "next": "^15.0.0",
    "@tanstack/react-query": "^5.0.0",
    "react-hook-form": "^7.0.0"
  }
}
```

### External Services

| Service | Purpose | Impact |
|---------|---------|--------|
| GitHub Actions | CI/CD | Must fix for PR workflow |
| Web Push (VAPID) | Notifications | Reliability critical |
| OpenAI/Anthropic/etc. | AI analysis | Re-analyse depends on |

---

## Acceptance Criteria (Authoritative)

### P9-1.1: Fix GitHub Actions CI Tests

**AC-1.1.1:** Given a PR is created, when CI runs, then all backend tests pass
**AC-1.1.2:** Given a PR is created, when CI runs, then all frontend tests pass
**AC-1.1.3:** Given a PR is created, when CI runs, then ESLint passes
**AC-1.1.4:** Given a PR is created, when CI runs, then TypeScript check passes
**AC-1.1.5:** Given CI completes, when viewing results, then total time is under 10 minutes

### P9-1.2: Fix Push Notifications Persistence

**AC-1.2.1:** Given push is enabled, when first event occurs, then notification is received
**AC-1.2.2:** Given push is enabled, when second event occurs, then notification is received
**AC-1.2.3:** Given push is enabled, when 10th event occurs, then notification is received
**AC-1.2.4:** Given page is refreshed, when event occurs, then notification still works
**AC-1.2.5:** Given browser is restarted, when event occurs, then notification still works

### P9-1.3: Fix Protect Camera Filter Settings

**AC-1.3.1:** Given I toggle filter settings, when I click Save, then success toast appears
**AC-1.3.2:** Given I save filter settings, when I refresh page, then settings are preserved
**AC-1.3.3:** Given I save filter settings, when server restarts, then settings are preserved
**AC-1.3.4:** Given person filter is disabled, when person event occurs, then event is filtered

### P9-1.4: Fix Re-Analyse Function

**AC-1.4.1:** Given an event with description, when I click Re-Analyse, then loading shows
**AC-1.4.2:** Given re-analysis completes, when successful, then new description appears
**AC-1.4.3:** Given re-analysis completes, when successful, then success toast appears
**AC-1.4.4:** Given re-analysis fails, when error occurs, then error toast appears
**AC-1.4.5:** Given re-analysis fails, when error occurs, then original description preserved

### P9-1.5: Fix Prompt Refinement API Submission

**AC-1.5.1:** Given I click Refine Prompt, when modal opens, then loading indicator shows
**AC-1.5.2:** Given refinement request sent, when AI responds, then suggestion displays
**AC-1.5.3:** Given AI timeout, when 30 seconds passes, then timeout error shows

### P9-1.6: Show AI Model in Prompt Refinement Modal

**AC-1.6.1:** Given modal opens, when AI is configured, then model name displays (e.g., "Using: OpenAI GPT-4o")
**AC-1.6.2:** Given no AI configured, when modal opens, then error message displays

### P9-1.7: Add Save/Replace Button to Prompt Refinement

**AC-1.7.1:** Given AI suggestion displays, when viewing modal, then "Accept & Save" button visible
**AC-1.7.2:** Given I click Accept & Save, when successful, then prompt setting updates
**AC-1.7.3:** Given I click Accept & Save, when successful, then modal closes
**AC-1.7.4:** Given I click Accept & Save, when successful, then success toast appears

### P9-1.8: Fix Vehicle Entity Make/Model Separation

**AC-1.8.1:** Given "white Toyota Camry" in description, when entity extracted, then color=white, make=Toyota, model=Camry
**AC-1.8.2:** Given "black Ford F-150" in description, when entity extracted, then separate entity from Toyota
**AC-1.8.3:** Given same vehicle in multiple events, when matching, then events grouped together
**AC-1.8.4:** Given different vehicles, when viewing Entities page, then shown as separate entities

---

## Traceability Mapping

| AC | Spec Section | Component(s) | Test Idea |
|----|--------------|--------------|-----------|
| AC-1.1.1-5 | CI Workflow | ci.yml, pytest, vitest | Run CI, verify green |
| AC-1.2.1-5 | Push Service | push_service.py, sw.js | Sequential event test |
| AC-1.3.1-4 | Filter Settings | protect.py, ProtectCameraFilter | CRUD test with refresh |
| AC-1.4.1-5 | Re-Analyse | ai_service.py, events API | Manual + unit test |
| AC-1.5.1-3 | Prompt Refinement | ai.py, ai_service.py | Integration test |
| AC-1.6.1-2 | Settings UI | PromptRefinementModal | Component test |
| AC-1.7.1-4 | Settings UI | PromptRefinementModal, settings API | E2E test |
| AC-1.8.1-4 | Entity Service | entity_service.py | Unit test with samples |

---

## Risks, Assumptions, Open Questions

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| CI flakiness hard to reproduce | Medium | Medium | Add detailed logging, run multiple times |
| Push notification browser differences | Medium | High | Test Chrome, Firefox, Safari explicitly |
| Vehicle extraction regex misses edge cases | Medium | Medium | Build comprehensive test suite |

### Assumptions

- GitHub Actions environment is consistent with local dev
- Service worker API behaves consistently across browsers
- AI providers return consistent response formats
- Vehicle descriptions follow predictable patterns (color make model)

### Open Questions

- **Q1:** Should we cache push subscriptions in Redis for multi-instance?
  - **A:** Defer to future phase, current single-instance is sufficient

- **Q2:** Should vehicle entity matching use fuzzy matching for typos?
  - **A:** Start with exact match, add fuzzy if needed based on data

- **Q3:** Should re-analyse increment AI usage stats?
  - **A:** Yes, track in existing cost tracking service

---

## Test Strategy Summary

### Test Levels

| Level | Scope | Tools | Coverage |
|-------|-------|-------|----------|
| Unit | Individual functions | pytest, vitest | Entity extraction, filter logic |
| Integration | API endpoints | pytest, supertest | All fixed endpoints |
| E2E | User workflows | Manual | Push notifications, prompt refinement |
| Regression | CI pipeline | GitHub Actions | Automated on every PR |

### Test Cases by Story

**P9-1.1 (CI):**
- Verify all existing tests pass locally
- Verify CI configuration matches local environment
- Add test for any previously missing coverage

**P9-1.2 (Push):**
- Unit: Subscription save/retrieve
- Integration: Push endpoint delivery
- E2E: Multiple sequential notifications

**P9-1.3 (Filters):**
- Unit: Filter model CRUD
- Integration: Filter API endpoint
- E2E: Save, refresh, verify

**P9-1.4 (Re-Analyse):**
- Unit: AI service re-analyse method
- Integration: Re-analyse API endpoint
- E2E: UI button → new description

**P9-1.5-7 (Prompt Refinement):**
- Unit: Refinement service logic
- Integration: Refinement API endpoint
- Component: Modal renders correctly
- E2E: Full refinement flow

**P9-1.8 (Vehicle Entities):**
- Unit: Vehicle extraction regex
- Unit: Entity signature generation
- Integration: Entity matching logic
- E2E: Multiple vehicles → multiple entities

### Edge Cases

- Empty AI response for re-analyse
- Network timeout during push
- Filter save during database maintenance
- Vehicle description without model (just "white Toyota")
- Non-English vehicle names

---

_Generated by BMAD Epic Tech Context Workflow_
_Date: 2025-12-22_
_For: Brent_
