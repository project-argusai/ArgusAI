# Story P15-3.3: Unsaved Changes Indicator

**Epic:** P15-3 - Settings UX Consolidation
**Status:** Done
**Priority:** Medium

## Story

As a user, I want to see a visual indicator when settings have unsaved changes so that I don't accidentally navigate away without saving.

## Acceptance Criteria

- [x] AC1: `UnsavedIndicator` component created
- [x] AC2: Shows orange pulsing dot when `isDirty` is true
- [x] AC3: Hidden when `isDirty` is false
- [x] AC4: Optional "Unsaved" text label
- [x] AC5: Accessible with proper aria attributes
- [x] AC6: Size variants (sm, md)

## Technical Implementation

### File: `frontend/components/settings/UnsavedIndicator.tsx`

**Interface:**
```typescript
interface UnsavedIndicatorProps {
  isDirty: boolean;
  className?: string;
  showLabel?: boolean;
  size?: 'sm' | 'md';
}
```

**Features:**
- Conditional rendering (null when not dirty)
- Orange pulsing dot animation
- Optional text label
- ARIA label for accessibility
- Size variants

## Usage Example

```tsx
<CardTitle className="flex items-center gap-2">
  Settings
  <UnsavedIndicator isDirty={isDirty} />
</CardTitle>
```

## Dev Notes

Component is simple and focused. Animation uses Tailwind's `animate-pulse` for subtle attention-drawing effect.
