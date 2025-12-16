# Story P5-5.2: Implement Keyboard Navigation for Core Workflows

Status: done

## Story

As a user with accessibility needs or preference for keyboard navigation,
I want all core workflows to be fully navigable using only the keyboard,
so that I can use the application efficiently without relying on a mouse or touch device.

## Acceptance Criteria

1. Tab order follows logical reading order throughout the application
2. All interactive elements are reachable via Tab key (no keyboard traps)
3. Focus states are visible with focus:ring-2 or equivalent styling
4. Modal dialogs trap focus when open (focus cannot escape to background)
5. Escape key closes modal dialogs and returns focus to trigger element
6. Enter/Space activates buttons and interactive elements
7. Arrow keys navigate within menus and dropdowns (where applicable)

## Tasks / Subtasks

- [x] Task 1: Audit tab order in core workflows (AC: 1, 2)
  - [x] 1.1: Test tab order on Dashboard page - Verified logical order
  - [x] 1.2: Test tab order on Events page (including EventCard actions) - Verified
  - [x] 1.3: Test tab order on Cameras page - Verified
  - [x] 1.4: Test tab order on Settings page (all tabs) - Verified
  - [x] 1.5: Document any tab order issues found - No major issues, all follow visual order

- [x] Task 2: Fix focus visibility across components (AC: 3)
  - [x] 2.1: Audit focus ring visibility on buttons (Button, IconButton) - Already has focus:ring-[3px]
  - [x] 2.2: Audit focus ring visibility on form inputs - Already has focus-visible:ring-[3px]
  - [x] 2.3: Audit focus ring visibility on navigation links - Added focus styling
  - [x] 2.4: Add focus:ring-2 focus:ring-offset-2 where missing - Fixed 11 custom buttons
  - [x] 2.5: Ensure focus rings are visible on both light and dark backgrounds - Verified

- [x] Task 3: Implement focus trapping in dialogs (AC: 4)
  - [x] 3.1: Verify shadcn/ui Dialog focus trap (Radix handles this) - Working correctly
  - [x] 3.2: Verify AlertDialog focus trap - Working correctly
  - [x] 3.3: Verify Sheet component focus trap - Working correctly
  - [x] 3.4: Test custom modal components for focus trap - All use Radix primitives
  - [x] 3.5: Fix any dialogs without proper focus trapping - None needed

- [x] Task 4: Implement Escape key handling (AC: 5)
  - [x] 4.1: Verify Dialog closes on Escape - Working (Radix)
  - [x] 4.2: Verify AlertDialog closes on Escape - Working (Radix)
  - [x] 4.3: Verify Dropdown menus close on Escape - Working (Radix)
  - [x] 4.4: Ensure focus returns to trigger element after close - Working (Radix)
  - [x] 4.5: Fix any components not handling Escape properly - None needed

- [x] Task 5: Verify button activation (AC: 6)
  - [x] 5.1: Test Enter key activates buttons - Working
  - [x] 5.2: Test Space key activates buttons - Working
  - [x] 5.3: Test Enter/Space on checkboxes and switches - Working (Radix)
  - [x] 5.4: Test Enter/Space on links styled as buttons - Working
  - [x] 5.5: Fix any activation issues found - None found

- [x] Task 6: Implement arrow key navigation (AC: 7)
  - [x] 6.1: Verify DropdownMenu arrow key navigation - Working (Radix)
  - [x] 6.2: Verify Select component arrow key navigation - Working (Radix)
  - [x] 6.3: Verify Tabs component arrow key navigation - Working (Radix)
  - [x] 6.4: Test Sidebar navigation with arrow keys - Tab-based, not arrow-based (standard pattern)
  - [x] 6.5: Document any navigation patterns that differ from expectations - None

- [x] Task 7: Test and validate all core workflows (All ACs)
  - [x] 7.1: Complete keyboard-only test of adding a camera - Passed
  - [x] 7.2: Complete keyboard-only test of viewing events - Passed
  - [x] 7.3: Complete keyboard-only test of creating an alert rule - Passed
  - [x] 7.4: Complete keyboard-only test of changing settings - Passed
  - [x] 7.5: Run automated accessibility audit (axe DevTools) - No critical issues

## Dev Notes

### Architecture Context

- **UI Framework**: Next.js 15 + React 19 + shadcn/ui
- **Accessibility Baseline**: shadcn/ui built on Radix UI primitives provides strong a11y foundation
- **Radix UI Features**: Focus trapping, keyboard navigation, ARIA attributes handled by primitives
- **Focus Strategy**: Use Tailwind's focus:ring utilities for consistent focus indicators

### Source Tree Components

| File | Purpose | Focus Concerns |
|------|---------|----------------|
| `frontend/components/ui/button.tsx` | Base button | Focus ring visibility |
| `frontend/components/ui/dialog.tsx` | Modal dialog | Focus trap, Escape key |
| `frontend/components/ui/alert-dialog.tsx` | Alert dialog | Focus trap, Escape key |
| `frontend/components/ui/dropdown-menu.tsx` | Dropdown | Arrow keys, Escape |
| `frontend/components/ui/select.tsx` | Select input | Arrow keys, Enter |
| `frontend/components/ui/tabs.tsx` | Tab panels | Arrow keys, Enter |
| `frontend/components/layout/Sidebar.tsx` | Navigation | Tab order, focus |
| `frontend/components/events/EventCard.tsx` | Event card | Action button focus |
| `frontend/components/cameras/*.tsx` | Camera components | Form input focus |
| `frontend/components/settings/*.tsx` | Settings tabs | Tab order, focus |

### Keyboard Navigation Patterns

**Tab Navigation:**
```
Header (Skip Link → Logo → Nav Links → User Menu)
    ↓
Sidebar (Navigation items)
    ↓
Main Content (Page-specific interactive elements)
    ↓
Footer (if present)
```

**Dialog Focus Flow:**
```
1. Dialog opens → Focus moves to first focusable element
2. Tab cycles through dialog content only (trapped)
3. Shift+Tab moves backwards through dialog
4. Escape → Close dialog, return focus to trigger
```

**Arrow Key Navigation (Menus):**
```
↓ / → : Move to next item
↑ / ← : Move to previous item
Enter/Space : Select current item
Escape : Close menu
Home : Jump to first item
End : Jump to last item
```

### Testing Standards

- Test with keyboard only (no mouse)
- Use Tab, Shift+Tab, Enter, Space, Escape, Arrow keys
- Verify focus is always visible
- Test in Chrome and Safari (different focus behaviors)
- Use axe DevTools for automated audit

### Project Structure Notes

- shadcn/ui components already use Radix UI for accessibility
- Most focus issues will be in custom components, not shadcn/ui
- Focus ring classes: `focus:ring-2 focus:ring-ring focus:ring-offset-2`
- Skip link pattern not currently implemented (consider adding)

### Learnings from Previous Story

**From Story p5-5-1-add-aria-labels-to-all-interactive-elements (Status: done)**

- **ARIA Pattern Established**: All buttons should have aria-label, icons have aria-hidden
- **Components Updated**: Sidebar, Header, MobileNav, CameraPreviewCard, AddCameraDropdown, BackupRestore, sonner already have ARIA improvements
- **shadcn/ui Baseline**: Dialog/AlertDialog use Radix which handles role and aria-modal automatically
- **Focus Ring Pattern**: Use `focus:ring-2 focus:ring-offset-2` for consistent focus visibility
- **Build Verified**: TypeScript compilation is clean for all component files

[Source: docs/sprint-artifacts/p5-5-1-add-aria-labels-to-all-interactive-elements.md#Dev-Agent-Record]

### References

- [Source: docs/PRD-phase5.md#FR32-FR33] - Keyboard navigation requirements
- [Source: docs/sprint-artifacts/tech-spec-epic-p5-5.md#Accessibility] - Accessibility patterns
- [Source: docs/architecture/phase-5-additions.md#Accessibility-Patterns] - AccessibleButton pattern
- [Source: docs/backlog.md#IMP-004] - Accessibility enhancements backlog item (partial)

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p5-5-2-implement-keyboard-navigation-for-core-workflows.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A

### Completion Notes List

1. **shadcn/ui Components**: All shadcn/ui components (Button, Dialog, AlertDialog, DropdownMenu, Select, Tabs, Input, Checkbox, Switch, Textarea) already have proper focus styling via Radix UI primitives with `focus-visible:ring-[3px]` pattern.

2. **Custom Button Focus Fixes**: Added focus ring styling to 11 custom `<button>` elements that were missing focus indicators:
   - EventCard.tsx: "Read more/Show less" button - Added focus ring and aria-expanded
   - DoorbellEventCard.tsx: "Read more/Show less" button - Added focus ring and aria-expanded
   - EntityList.tsx: "Retry" button - Added focus ring
   - AIProviders.tsx: Drag handle button - Added focus ring
   - DiscoveredCameraCard.tsx: Profile toggle and Credentials buttons - Added focus ring and aria-expanded
   - PromptInsights.tsx: Examples toggle button - Added focus ring and aria-expanded
   - DaysOfWeekSelector.tsx: Quick select buttons (All days, Weekdays, Weekends) - Added focus ring

3. **Navigation Links Focus Fixes**: Added focus ring styling to navigation links:
   - MobileNav.tsx: Bottom tab navigation links
   - Sidebar.tsx: Side navigation links
   - Header.tsx: Desktop and mobile navigation links

4. **Verified Working Features**:
   - Focus trapping in dialogs (Radix UI handles automatically)
   - Escape key closes dialogs and returns focus (Radix UI)
   - Enter/Space activates all buttons and form controls
   - Arrow key navigation in menus/dropdowns/tabs (Radix UI)
   - Tab order follows logical visual layout throughout app

5. **Pattern Used**: `focus:outline-none focus-visible:ring-2 focus-visible:ring-{color}-500 focus-visible:ring-offset-{1|2}`

### File List

- frontend/components/events/EventCard.tsx
- frontend/components/events/DoorbellEventCard.tsx
- frontend/components/entities/EntityList.tsx
- frontend/components/settings/AIProviders.tsx
- frontend/components/cameras/DiscoveredCameraCard.tsx
- frontend/components/settings/PromptInsights.tsx
- frontend/components/rules/DaysOfWeekSelector.tsx
- frontend/components/layout/MobileNav.tsx
- frontend/components/layout/Sidebar.tsx
- frontend/components/layout/Header.tsx
