# Story P15-3.4: Navigation Warning for Unsaved Changes

**Epic:** P15-3 - Settings UX Consolidation
**Status:** Done
**Priority:** Medium

## Story

As a user, I want to be warned before navigating away with unsaved settings so that I don't lose my changes.

## Acceptance Criteria

- [x] AC1: `useUnsavedChangesWarning` hook created
- [x] AC2: Shows browser warning on page refresh/close when dirty
- [x] AC3: Warning can be customized with message
- [x] AC4: Can be enabled/disabled
- [x] AC5: Cleans up event listeners on unmount

## Technical Implementation

### File: `frontend/hooks/useUnsavedChangesWarning.ts`

**Interface:**
```typescript
interface UseUnsavedChangesWarningOptions {
  isDirty: boolean;
  message?: string;
  enabled?: boolean;
}
```

**Features:**
- Browser beforeunload event handling
- Standard browser confirmation dialog
- Proper cleanup on unmount
- Enable/disable toggle

## Usage Example

```tsx
const { isDirty } = useSettingsForm({ ... });

useUnsavedChangesWarning({ isDirty });
```

## Dev Notes

The hook focuses on browser-level navigation warning (beforeunload). For SPA navigation within Next.js, components should handle this at the route level if needed, but the browser warning covers the most important case (accidental tab close/refresh).

Note: Modern browsers show their own standard message regardless of the custom message provided, for security reasons.
