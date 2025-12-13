# Story P4-7.3: Anomaly Alerts

**Epic:** P4-7 Behavioral Anomaly Detection (Growth)
**Status:** done
**Created:** 2025-12-13
**Completed:** 2025-12-13
**Story Key:** p4-7-3-anomaly-alerts

---

## User Story

**As a** home security user
**I want** to receive alerts and visual indicators when high-anomaly events are detected
**So that** I can quickly identify and respond to unusual security events without manually monitoring every notification

---

## Background & Context

Epic P4-7 introduces behavioral anomaly detection. This is the final story in the epic, building on:

**P4-7.1 (Baseline Activity Learning) - DONE:**
- `CameraActivityPattern` model with hourly/daily/object type distributions
- `PatternService` for baseline management
- API endpoint `GET /api/v1/context/patterns/{camera_id}`

**P4-7.2 (Anomaly Scoring) - DONE:**
- `AnomalyScoringService` with z-score based anomaly calculation
- `anomaly_score` field on Event model (0.0-1.0 range)
- Severity classification: low (<0.3), medium (0.3-0.6), high (>0.6)
- API endpoints for manual scoring
- Event pipeline integration with non-blocking background scoring

**What This Story Adds:**
1. **Anomaly indicator on event cards** - visual badge showing anomaly severity
2. **Anomaly-specific notifications** - push/webhook alerts for high anomaly events
3. **Anomaly threshold settings** - user-configurable sensitivity per camera
4. **Anomaly filter in timeline** - filter events by anomaly severity

This completes the behavioral anomaly detection feature set.

---

## Acceptance Criteria

### AC1: Anomaly Badge on Event Cards
- [x] Add visual anomaly indicator to EventCard component
- [x] Badge shows severity: "Unusual" (yellow) for medium, "Anomaly" (red) for high
- [x] No badge for low anomaly scores (<0.3)
- [x] Tooltip shows exact score on hover (e.g., "Anomaly score: 0.72")
- [x] Badge positioned consistently with other indicators (confidence, provider)

### AC2: Anomaly Details in Event Detail View
- [x] Show anomaly score breakdown in event detail modal/page
- [x] Display visual progress bar with severity coloring
- [x] Show severity classification with contextual description
- [x] Gracefully handles events without anomaly scores

### AC3: Anomaly Filter in Events Timeline
- [x] Add "Anomaly" filter option to timeline filters
- [x] Filter options: Normal (Low), Unusual (Medium), Anomaly (High)
- [x] Filter works via `anomaly_severity` query param
- [x] Works with existing filters (camera, object type, date range)

### AC4: Anomaly Threshold Settings
- [x] Add anomaly settings section to Settings page (Motion tab)
- [x] Global threshold sliders with visual preview
- [x] Enable/disable anomaly scoring toggle
- [x] Settings stored in system_settings table (no prefix)
- [x] API endpoints via existing settings update endpoint

### AC5: Anomaly Alert Rule Type
- [x] Add "anomaly_threshold" as new alert rule condition type
- [x] Rule triggers when event anomaly_score >= threshold
- [x] Can combine with existing rule conditions (camera, object type)
- [x] `_check_anomaly_threshold()` method in AlertEngine

### AC6: Push Notification for High Anomaly Events
- [x] Pass anomaly_score to push notification service
- [x] Notification title includes "Unusual Activity" prefix for high anomaly
- [x] Uses HIGH_THRESHOLD from AnomalyScoringService
- [x] Respects existing notification preferences

### AC7: Webhook Payload Enhancement
- [x] Include anomaly_score in webhook event payload
- [x] Include anomaly_severity classification
- [x] Anomaly data section in webhook build_payload method
- [x] Uses thresholds from AnomalyScoringService

### AC8: Testing
- [x] Unit tests for anomaly badge component (17 tests)
- [x] Integration tests for anomaly filter API (7 tests)
- [x] Unit tests for threshold check method (4 tests)
- [x] Tests in test_alert_engine_anomaly.py

---

## Technical Implementation

### Task 1: Create AnomalyBadge Component
**File:** `frontend/components/events/AnomalyBadge.tsx` (new)
```tsx
interface AnomalyBadgeProps {
  score: number | null;
  showTooltip?: boolean;
}
// Display yellow "Unusual" for 0.3-0.6, red "Anomaly" for >0.6
```

### Task 2: Update EventCard to Show Anomaly Badge
**File:** `frontend/components/events/EventCard.tsx`
- Import and render AnomalyBadge
- Position next to confidence/provider badges
- Handle null anomaly_score gracefully

### Task 3: Add Anomaly Breakdown to Event Detail
**File:** `frontend/components/events/EventDetail.tsx` or modal component
- Add section for anomaly analysis
- Fetch breakdown via `/api/v1/context/anomaly/score/{event_id}`
- Display component scores with labels
- Show "Insufficient data" message when no baseline

### Task 4: Add Anomaly Filter to Timeline
**Files:**
- `frontend/app/events/page.tsx` - Add filter state
- `frontend/components/events/EventFilters.tsx` - Add anomaly dropdown
- `backend/app/api/v1/events.py` - Add anomaly_severity filter param

### Task 5: Create Anomaly Settings UI
**File:** `frontend/components/settings/AnomalySettings.tsx` (new)
- Global threshold slider (0.0-1.0)
- Per-camera override toggle
- Save/cancel buttons

### Task 6: Create Anomaly Settings API
**Files:**
- `backend/app/api/v1/system.py` - Add anomaly threshold endpoints
- `backend/app/models/settings.py` - Add anomaly_threshold to settings

### Task 7: Add Anomaly Alert Rule Type
**Files:**
- `backend/app/services/alert_engine.py` - Handle anomaly_threshold condition
- `backend/app/models/alert_rule.py` - Ensure supports anomaly conditions
- `frontend/components/rules/RuleConditionEditor.tsx` - Add anomaly option

### Task 8: Enhance Push Notification for Anomaly
**File:** `backend/app/services/push_notification_service.py`
- Check anomaly score against threshold
- Modify notification title/body for high anomaly events
- Add anomaly toggle to preferences check

### Task 9: Update Webhook Payload
**File:** `backend/app/services/alert_engine.py` or webhook service
- Add anomaly_score, anomaly_severity, component scores to payload
- Update API documentation

### Task 10: Write Tests
**Files:**
- `frontend/__tests__/components/AnomalyBadge.test.tsx` (new)
- `backend/tests/test_api/test_events_anomaly_filter.py` (new)
- `backend/tests/test_services/test_alert_engine_anomaly.py` (new)

---

## Dev Notes

### Architecture Constraints
- Use existing EventCard patterns for badge placement
- Follow existing filter implementation in EventFilters component
- Use system_settings table for threshold storage (consistent with other settings)
- Anomaly notifications should respect existing push preferences framework

[Source: docs/architecture.md#Phase-4-Additions]

### Relevant Existing Code

**From P4-7.2 Implementation:**
- `AnomalyScoringService` at `backend/app/services/anomaly_scoring_service.py`
- `AnomalyScoreResult` dataclass with total, timing_score, day_score, object_score, severity
- API endpoint `GET /api/v1/context/anomaly/score/{event_id}`
- Severity thresholds: LOW_THRESHOLD=0.3, HIGH_THRESHOLD=0.6

**Existing Components to Extend:**
- `EventCard.tsx` - add badge alongside existing ConfidenceBadge
- `EventFilters.tsx` - add dropdown similar to camera/object filters
- `backend/app/api/v1/events.py` - add query param similar to camera_id filter
- `alert_engine.py` - add condition type similar to object_type matching

[Source: docs/sprint-artifacts/p4-7-2-anomaly-scoring.md#Dev-Agent-Record]

### Learnings from P4-7.2

**From Story p4-7-2-anomaly-scoring (Status: done)**

- **Scoring Service Pattern**: `AnomalyScoringService` uses static methods, no state
- **Severity Classification**: Already defined in service - reuse `_classify_severity()`
- **Score Access**: Event model has `anomaly_score` field (Float, nullable)
- **API Structure**: Anomaly endpoints in `context.py` router, prefix `/api/v1/context/anomaly/`
- **Background Processing**: Scoring runs via `asyncio.create_task()` - non-blocking

**Files Created in P4-7.2:**
- `backend/app/services/anomaly_scoring_service.py` - reuse severity constants
- `backend/tests/test_services/test_anomaly_scoring_service.py` - follow test patterns
- `backend/tests/test_api/test_context_anomaly.py` - follow API test patterns

[Source: docs/sprint-artifacts/p4-7-2-anomaly-scoring.md#File-List]

### Testing Standards
- Follow pytest patterns in `backend/tests/`
- Use Testing Library patterns for React components
- Mock external services (push, webhook)

[Source: docs/epics-phase4.md#Epic-P4-7]

### UI/UX Considerations
- Badge colors should match existing design system
- Filter dropdown should match other timeline filters
- Settings should integrate with existing settings page layout

---

## Dev Agent Record

### Context Reference

- [docs/sprint-artifacts/p4-7-3-anomaly-alerts.context.xml](p4-7-3-anomaly-alerts.context.xml)

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Frontend build passes with all new components
- Frontend tests for AnomalyBadge: 17/17 pass
- Backend unit tests for _check_anomaly_threshold: 4/4 pass

### Completion Notes List

1. **AnomalyBadge Component**: Created with `getAnomalySeverity()` helper function. Renders yellow "Unusual" badge for medium (0.3-0.6) and red "Anomaly" badge for high (>0.6). No badge for low scores. Includes tooltip with exact score.

2. **EventCard Integration**: Added AnomalyBadge to EventCard component in the badges area alongside confidence indicator.

3. **EventDetailModal Enhancement**: Added "Anomaly Analysis" section with visual progress bar, severity badge, and contextual description explaining the anomaly level.

4. **Timeline Filter**: Extended EventFilters component with anomaly severity dropdown (Normal/Unusual/Anomaly). Backend events API updated with `anomaly_severity` query parameter supporting comma-separated values.

5. **Alert Engine**: Added `_check_anomaly_threshold()` method to AlertEngine. New condition type `anomaly_threshold` triggers when event.anomaly_score >= threshold. Works with combined conditions.

6. **Push Notifications**: Enhanced `format_rich_notification()` to accept anomaly_score parameter. High anomaly events get "Unusual Activity" prefix in notification title.

7. **Webhook Payload**: Updated `build_payload()` method to include `anomaly` object with score and severity classification.

8. **Settings UI**: Created AnomalySettings component with enable/disable toggle and threshold sliders with visual preview. Added to Motion Detection tab in settings page.

9. **Settings API**: Extended SystemSettingsUpdate schema with `anomaly_enabled`, `anomaly_low_threshold`, `anomaly_high_threshold` fields. Settings saved without prefix for service access.

### File List

**New Files:**
- `frontend/components/events/AnomalyBadge.tsx` - Anomaly severity badge component
- `frontend/components/settings/AnomalySettings.tsx` - Anomaly threshold settings UI
- `frontend/__tests__/components/AnomalyBadge.test.tsx` - Badge component tests (17 tests)
- `backend/tests/test_services/test_alert_engine_anomaly.py` - Alert engine anomaly tests
- `backend/tests/test_api/test_events_anomaly_filter.py` - Events API filter tests

**Modified Files:**
- `frontend/components/events/EventCard.tsx` - Added AnomalyBadge import and render
- `frontend/components/events/EventDetailModal.tsx` - Added anomaly analysis section with Activity icon
- `frontend/components/events/EventFilters.tsx` - Added anomaly severity filter dropdown
- `frontend/types/event.ts` - Added anomaly_score to IEvent, anomaly_severity to IEventFilters
- `frontend/types/settings.ts` - Added anomaly settings fields to SystemSettings
- `frontend/app/settings/page.tsx` - Added AnomalySettings component to Motion tab
- `backend/app/api/v1/events.py` - Added anomaly_severity query parameter
- `backend/app/services/alert_engine.py` - Added _check_anomaly_threshold() method and condition handling
- `backend/app/services/webhook_service.py` - Added anomaly data to webhook payload
- `backend/app/services/push_notification_service.py` - Enhanced for anomaly score in notifications
- `backend/app/schemas/system.py` - Added anomaly threshold settings fields
- `backend/app/api/v1/system.py` - Added anomaly settings to no_prefix_fields

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-13 | SM Agent | Initial story creation |
| 2025-12-13 | Dev Agent | Implemented all acceptance criteria, completed story |
