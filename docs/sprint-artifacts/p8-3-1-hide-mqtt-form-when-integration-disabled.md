# Story P8-3.1: Hide MQTT Form When Integration Disabled

Status: done

## Story

As a **user**,
I want **MQTT configuration fields hidden when the integration is disabled**,
so that **the settings page is less cluttered and shows only relevant options**.

## Acceptance Criteria

| AC# | Acceptance Criteria |
|-----|---------------------|
| AC1.1 | Given MQTT toggle OFF, when viewing settings, then all MQTT config fields hidden |
| AC1.2 | Given MQTT toggle OFF, when toggling ON, then fields animate into view |
| AC1.3 | Given MQTT toggle ON, when toggling OFF, then fields animate out of view |
| AC1.4 | Given fields hidden, when re-enabling, then previously saved values preserved |
| AC1.5 | Given hidden fields, when saving settings, then MQTT config not cleared |

## Tasks / Subtasks

- [x] Task 1: Implement conditional rendering for MQTT form sections (AC: 1.1)
  - [x] 1.1: Wrap broker configuration section in conditional based on `enabled` state
  - [x] 1.2: Wrap topic configuration section in conditional based on `enabled` state
  - [x] 1.3: Wrap availability messages section in conditional based on `enabled` state
  - [x] 1.4: Wrap Home Assistant discovery section in conditional based on `enabled` state
  - [x] 1.5: Keep connection status display conditional on `enabled` (already done)
  - [x] 1.6: Keep Save button always visible regardless of toggle state

- [x] Task 2: Add smooth CSS transition animations (AC: 1.2, 1.3)
  - [x] 2.1: Wrap conditional sections in animation container component
  - [x] 2.2: Use CSS transitions for height and opacity (max 300ms per tech spec)
  - [x] 2.3: Add `overflow-hidden` during animation to prevent layout jumps
  - [x] 2.4: Test animation smoothness on toggle ON
  - [x] 2.5: Test animation smoothness on toggle OFF

- [x] Task 3: Preserve form values when toggling visibility (AC: 1.4, 1.5)
  - [x] 3.1: Verify form state management does not reset values when sections hidden
  - [x] 3.2: Test that saved values are restored when re-enabling toggle
  - [x] 3.3: Test that saving with hidden fields does not clear MQTT config
  - [x] 3.4: Test rapid toggle does not cause state issues

- [x] Task 4: Write frontend component tests (AC: 1.1-1.5)
  - [x] 4.1: Test `test_mqtt_fields_hidden_when_disabled`
  - [x] 4.2: Test `test_mqtt_fields_show_on_enable`
  - [x] 4.3: Test `test_mqtt_values_preserved_after_toggle`
  - [x] 4.4: Test `test_rapid_toggle_stability`

## Dev Notes

### Technical Context

This story improves the MQTT settings UX by hiding configuration fields when the integration toggle is OFF. The current `MQTTSettings.tsx` component shows all fields regardless of toggle state, creating unnecessary visual clutter.

Per the tech spec (P8-3.1), the solution should:
- Hide fields with smooth animation (< 300ms transition)
- Preserve form values in state even when hidden
- Not clear server-side config when saving with hidden fields

### Architecture Alignment

Per `docs/sprint-artifacts/tech-spec-epic-P8-3.md`:
- Component to modify: `frontend/components/settings/MQTTSettings.tsx`
- Use conditional rendering based on `enabled` state
- Add CSS transitions for smooth show/hide animation
- Form state preserved using existing react-hook-form pattern

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| MQTTSettings | `frontend/components/settings/MQTTSettings.tsx` | MODIFY - Add conditional visibility |

### Current Component Analysis

The `MQTTSettings.tsx` component (lines 84-700) has:
- Master enable toggle at line 307-321 (already exists, controls `enabled` state)
- Connection status display at line 324-359 (already conditional on `enabled`)
- Broker configuration section at lines 363-476 (currently always visible)
- Topic configuration section at lines 479-560 (currently always visible)
- Availability messages section at lines 563-615 (currently always visible)
- Home Assistant discovery section at lines 618-666 (currently always visible)
- Info alert at lines 669-677 (can remain visible as educational)
- Save button at lines 680-695 (should remain visible)

### Implementation Approach

1. Create a wrapper component or use CSS-based animation for sections
2. Keep form state using react-hook-form (already in place)
3. Conditionally render sections based on `form.watch('enabled')`
4. Use Tailwind CSS transitions: `transition-all duration-300 ease-in-out`
5. Animate height and opacity for smooth effect

### Testing Approach

- Use React Testing Library to verify visibility states
- Mock API calls with vitest
- Test form state preservation across toggle cycles
- Test that saving works correctly with hidden fields

### Learnings from Previous Story

**From Story p8-2-5-add-frame-sampling-strategy-selection-in-settings (Status: done)**

- Frontend component testing established in `frontend/__tests__/components/settings/`
- Use vitest + React Testing Library for component tests
- Settings page pattern established for radio button groups
- Follow existing form state management with react-hook-form

[Source: docs/sprint-artifacts/p8-2-5-add-frame-sampling-strategy-selection-in-settings.md#Dev-Agent-Record]

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P8-3.md#P8-3.1]
- [Source: docs/epics-phase8.md#Story P8-3.1]
- [Source: frontend/components/settings/MQTTSettings.tsx]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p8-3-1-hide-mqtt-form-when-integration-disabled.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

- All acceptance criteria verified via automated tests
- 46 tests passing (37 existing + 9 new for P8-3.1)
- CSS grid-rows animation provides smooth height transition with opacity
- Form state preserved via react-hook-form (no explicit state management needed)

### File List

- `frontend/components/settings/MQTTSettings.tsx` - Added collapsible wrapper with CSS transitions
- `frontend/__tests__/components/settings/MQTTSettings.test.tsx` - Added 9 new tests for P8-3.1

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-21 | Claude | Story drafted from Epic P8-3 |
| 2025-12-21 | Claude | Implementation complete - all tests passing |
