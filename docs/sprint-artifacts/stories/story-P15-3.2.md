# Story P15-3.2: Settings Form State Management Hook

**Epic:** P15-3 - Settings UX Consolidation
**Status:** Done
**Priority:** High

## Story

As a developer, I need a reusable hook for settings form state management so that all settings sections can have consistent save/reset behavior.

## Acceptance Criteria

- [x] AC1: `useSettingsForm` hook created with TypeScript generics
- [x] AC2: Hook provides `formData`, `updateField`, `isDirty`, `save`, `reset` functions
- [x] AC3: `isDirty` computed via deep comparison of current vs initial state
- [x] AC4: `save` calls provided save function and shows success toast
- [x] AC5: `reset` restores form to initial values
- [x] AC6: Hook integrates with TanStack Query for cache invalidation
- [x] AC7: Loading and error states exposed

## Technical Implementation

### File: `frontend/hooks/useSettingsForm.ts`

**Interface:**
```typescript
interface UseSettingsFormReturn<T> {
  formData: T;
  setFormData: React.Dispatch<React.SetStateAction<T>>;
  updateField: <K extends keyof T>(field: K, value: T[K]) => void;
  isDirty: boolean;
  save: () => Promise<void>;
  reset: () => void;
  isSaving: boolean;
  isLoading: boolean;
  error: Error | null;
  clearError: () => void;
}
```

**Features:**
- Deep equality comparison for dirty detection
- Deep cloning to prevent reference mutations
- TanStack Query mutation for save with cache invalidation
- Toast notifications on save success/error
- Callback hooks for success/error handling

## Dev Notes

Hook implemented with full TypeScript support. Ready for use in settings components.
