# Epic Technical Specification: Settings UX Consolidation

Date: 2025-12-30
Author: Brent
Epic ID: P15-3
Status: Draft

---

## Overview

Epic P15-3 standardizes settings save patterns across all settings pages in ArgusAI. Currently, some settings auto-save while others require explicit save actions, creating user confusion. This epic implements a consistent explicit save pattern with unsaved changes detection and navigation warnings, improving the predictability of the settings experience.

## Objectives and Scope

**In Scope:**
- Audit all settings sections for current save behavior (FR28)
- Create reusable settings form state management hook
- Add visual indicator for unsaved changes (FR29)
- Warn before navigating away with unsaved changes (FR30)
- Show confirmation toast on successful save (FR31)
- Add Cancel/Reset button to discard changes (FR32)
- Standardize all settings sections to explicit Save pattern

**Out of Scope:**
- Adding new settings fields
- Settings page layout redesign
- Real-time validation beyond existing patterns
- Backend settings API changes

## System Architecture Alignment

This epic focuses on frontend architecture improvements:

- **useSettingsForm hook** - Centralized form state management (ADR-P15-005)
- **useUnsavedChangesWarning hook** - Browser/SPA navigation protection
- **UnsavedIndicator component** - Visual dirty state indicator
- **Consistent button placement** - Save/Cancel at bottom of each section

Reference: [Phase 15 Architecture](../architecture/phase-15-additions.md#settings-form-hook-p15-32)

## Detailed Design

### Services and Modules

| Component | Responsibility | File |
|-----------|---------------|------|
| useSettingsForm | Form state, dirty detection, save/reset | `frontend/hooks/useSettingsForm.ts` |
| useUnsavedChangesWarning | beforeunload + SPA navigation | `frontend/hooks/useUnsavedChangesWarning.ts` |
| UnsavedIndicator | Visual dot/badge for dirty state | `frontend/components/settings/UnsavedIndicator.tsx` |
| SettingsSection | Wrapper with Save/Cancel buttons | `frontend/components/settings/SettingsSection.tsx` |

### Data Models and Contracts

No new data models. The hook uses TypeScript generics:

```typescript
// useSettingsForm return type
interface UseSettingsFormReturn<T> {
  formData: T;
  setFormData: React.Dispatch<React.SetStateAction<T>>;
  updateField: <K extends keyof T>(field: K, value: T[K]) => void;
  isDirty: boolean;
  save: () => Promise<void>;
  reset: () => void;
  isLoading: boolean;
  error: Error | null;
}

// Usage pattern
const { formData, updateField, isDirty, save, reset, isLoading } = useSettingsForm(
  initialSettings,
  (data) => api.updateSettings(data),
  ['settings', 'general']
);
```

### APIs and Interfaces

No new API endpoints. Existing settings endpoints used:

- `GET /api/v1/system/settings` - Fetch current settings
- `PUT /api/v1/system/settings` - Update settings
- Various section-specific endpoints (AI, MQTT, etc.)

### Workflows and Sequencing

**Settings Edit Flow:**

```
User opens settings page
       │
       ▼
┌─────────────────────────────┐
│  Load initial data          │
│  useSettingsForm(initial)   │
│  isDirty = false            │
└─────────────────────────────┘
       │
User modifies field
       │
       ▼
┌─────────────────────────────┐
│  updateField(key, value)    │
│  isDirty = true             │
│  UnsavedIndicator shows     │
│  Save button enabled        │
└─────────────────────────────┘
       │
       ├──► User clicks Save
       │         │
       │         ▼
       │    ┌─────────────────────────────┐
       │    │  save() → API call          │
       │    │  isLoading = true           │
       │    │  On success: toast + reset  │
       │    │  isDirty = false            │
       │    └─────────────────────────────┘
       │
       └──► User clicks Cancel/Reset
                 │
                 ▼
            ┌─────────────────────────────┐
            │  reset() → restore initial  │
            │  isDirty = false            │
            │  UnsavedIndicator hides     │
            └─────────────────────────────┘
```

**Navigation Warning Flow:**

```
isDirty = true
       │
User attempts navigation (link click, back button, tab close)
       │
       ▼
┌─────────────────────────────┐
│  Show confirmation dialog   │
│  "You have unsaved changes" │
│  [Stay] [Discard]           │
└─────────────────────────────┘
       │
       ├──► Stay: Cancel navigation
       │
       └──► Discard: Allow navigation, changes lost
```

## Non-Functional Requirements

### Performance

| Metric | Target | Notes |
|--------|--------|-------|
| Settings save | < 1 second | NFR9 |
| Dirty detection | Instant | JSON.stringify comparison |
| Form update | < 16ms | No blocking renders |

### Security

No security implications - frontend-only UX changes.

### Reliability/Availability

- Hook handles unmount during save (cancel pending mutation)
- beforeunload works even if React crashes
- Graceful fallback if browser blocks confirm dialog

### Observability

- Console warning if save fails
- React Query DevTools shows mutation state
- Toast messages for user feedback

## Dependencies and Integrations

| Dependency | Version | Purpose | Status |
|------------|---------|---------|--------|
| @tanstack/react-query | ^5.x | Data fetching/mutations | Existing |
| sonner | ^1.x | Toast notifications | Existing |
| radix-ui/dialog | ^1.x | Confirmation dialogs | Existing |

No new dependencies required.

## Acceptance Criteria (Authoritative)

1. **AC1:** All settings sections have explicit Save and Cancel buttons at section bottom
2. **AC2:** Save button disabled when no changes exist (isDirty = false)
3. **AC3:** Save button shows loading spinner during save operation
4. **AC4:** Success toast appears after save completes (e.g., "Settings saved successfully")
5. **AC5:** Orange dot or indicator appears near section title when changes are unsaved
6. **AC6:** Cancel button resets form to original values
7. **AC7:** Browser close/refresh with unsaved changes shows native warning dialog
8. **AC8:** SPA navigation with unsaved changes shows custom confirmation dialog
9. **AC9:** Clicking "Discard" in dialog allows navigation
10. **AC10:** Clicking "Stay" in dialog prevents navigation and keeps changes
11. **AC11:** Indicator clears after successful save
12. **AC12:** Indicator clears after cancel/reset

## Traceability Mapping

| AC | FR | Spec Section | Component | Test Idea |
|----|-----|--------------|-----------|-----------|
| AC1 | FR28 | Button Placement | SettingsSection | Verify buttons in all sections |
| AC2 | FR28 | Form State | useSettingsForm | Test isDirty false → disabled |
| AC3 | FR31 | Save Loading | useSettingsForm | Verify spinner during mutation |
| AC4 | FR31 | Save Feedback | SettingsSection | Check toast on save success |
| AC5 | FR29 | Dirty Indicator | UnsavedIndicator | Verify visibility when dirty |
| AC6 | FR32 | Reset | useSettingsForm | Click cancel, verify values reset |
| AC7 | FR30 | Browser Warning | useUnsavedChangesWarning | beforeunload event test |
| AC8 | FR30 | SPA Warning | useUnsavedChangesWarning | Router navigation test |
| AC9 | FR30 | Discard Action | Navigation Dialog | Click discard, verify navigation |
| AC10 | FR30 | Stay Action | Navigation Dialog | Click stay, verify no navigation |
| AC11 | FR29 | Indicator Clear | UnsavedIndicator | Save, verify indicator gone |
| AC12 | FR29 | Indicator Clear | UnsavedIndicator | Cancel, verify indicator gone |

## Risks, Assumptions, Open Questions

**Risks:**
- **Risk:** Some settings sections may have complex nested state
  - *Mitigation:* useSettingsForm supports generic objects, audit each section

- **Risk:** Next.js App Router navigation interception differs from Pages Router
  - *Mitigation:* Use combination of beforeunload + Link onClick prevention

**Assumptions:**
- Assumption: All settings sections already use React state (not uncontrolled inputs)
- Assumption: Existing toast system (sonner) is consistent across app
- Assumption: Settings API returns 200 on success with updated data

**Open Questions:**
- Q: Should auto-save be available as user preference?
  - *Recommendation:* No, explicit save is more predictable for security settings

- Q: How to handle form validation errors?
  - *Recommendation:* Show inline errors, keep save disabled until valid

## Test Strategy Summary

**Unit Tests:**
- useSettingsForm: isDirty calculation, reset, updateField
- useUnsavedChangesWarning: beforeunload setup/teardown
- UnsavedIndicator: visibility based on isDirty prop

**Integration Tests:**
- Full form flow: load → edit → save → verify reset
- Cancel flow: edit → cancel → verify original values
- Error handling: save failure → verify no reset

**E2E Tests (Playwright):**
- Navigate away with unsaved changes → verify dialog
- Browser back button with unsaved changes
- Successful save flow with toast verification

**Manual Testing:**
- Visual inspection of indicator across themes
- Tab key navigation through form and buttons
- Browser refresh during edit
- Mobile touch interactions

## Settings Sections Audit

The following settings sections need to be updated:

| Section | Current Pattern | Target Pattern |
|---------|-----------------|----------------|
| General Settings | Mixed | Explicit Save |
| AI Provider Settings | Auto-save toggle | Explicit Save |
| Camera Settings | Save button (existing) | Standardize button placement |
| Alert Rules | Save per rule | Keep (list CRUD pattern) |
| Notifications | Mixed | Explicit Save |
| MQTT Integration | Save button | Standardize button placement |
| HomeKit Settings | Save button | Standardize button placement |
| Data/Retention | Auto-save | Explicit Save |
| Security Settings | Save button | Standardize button placement |
| Tunnel Settings | Test + Save | Keep (special test flow) |

**Note:** Alert Rules use a list/CRUD pattern where each rule has its own save action - this is appropriate and should not change.
