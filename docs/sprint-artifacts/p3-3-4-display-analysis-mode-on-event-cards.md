# Story P3-3.4: Display Analysis Mode on Event Cards

Status: done

## Story

As a **user**,
I want **to see which analysis mode was used for each event**,
So that **I understand why description quality varies**.

## Acceptance Criteria

1. **AC1:** Given an event card in the timeline, when event has analysis_mode stored, then small badge shows mode: "SF" / "MF" / "VN" with appropriate icon

2. **AC2:** Given event used fallback (e.g., multi_frame -> single_frame), when event card is displayed, then badge shows actual mode used (single_frame) and subtle indicator shows fallback occurred, with tooltip explaining: "Fell back to Single Frame: {fallback_reason}"

3. **AC3:** Given event has no analysis_mode (legacy events), when displayed, then no badge shown or shows "---" placeholder

4. **AC4:** Given user clicks/hovers analysis mode badge, when interaction occurs, then shows popover/tooltip with full details:
   - Mode used (full name)
   - Frame count (if multi-frame)
   - Fallback reason (if any)

## Tasks / Subtasks

- [x] **Task 1: Add analysis_mode fields to frontend Event type** (AC: 1, 2, 3)
  - [x] 1.1 Add `AnalysisMode` type to `frontend/types/event.ts` ('single_frame' | 'multi_frame' | 'video_native')
  - [x] 1.2 Add `analysis_mode` field to `IEvent` interface (optional, can be null for legacy events)
  - [x] 1.3 Add `frame_count_used` field to `IEvent` interface (optional int)
  - [x] 1.4 Add `fallback_reason` field to `IEvent` interface (optional string)

- [x] **Task 2: Create AnalysisModeBadge component** (AC: 1, 2, 3, 4)
  - [x] 2.1 Create `frontend/components/events/AnalysisModeBadge.tsx`
  - [x] 2.2 Display compact badge with abbreviation: SF (Single Frame), MF (Multi-Frame), VN (Video Native)
  - [x] 2.3 Add appropriate icons from lucide-react: Image (SF), Images (MF), Video (VN)
  - [x] 2.4 Apply color coding: gray (SF), blue (MF), purple (VN)
  - [x] 2.5 Handle null/undefined analysis_mode (show nothing or "---")
  - [x] 2.6 Add fallback indicator (small warning icon) when fallback_reason is present
  - [x] 2.7 Implement Tooltip/Popover with full details on hover/click:
        - Mode full name
        - Frame count if multi-frame
        - Fallback reason if present

- [x] **Task 3: Integrate AnalysisModeBadge into EventCard** (AC: 1, 2)
  - [x] 3.1 Import AnalysisModeBadge into EventCard.tsx
  - [x] 3.2 Add badge to the header section near SourceTypeBadge
  - [x] 3.3 Ensure badge doesn't clutter the layout (keep compact)
  - [x] 3.4 Pass analysis_mode, frame_count_used, and fallback_reason props

- [x] **Task 4: Add component tests** (AC: All) - BLOCKED: No testing framework
  - [x] 4.1 Test AnalysisModeBadge renders correct abbreviation for each mode - SKIPPED (no test framework)
  - [x] 4.2 Test fallback indicator appears when fallback_reason present - SKIPPED (no test framework)
  - [x] 4.3 Test tooltip content includes all relevant fields - SKIPPED (no test framework)
  - [x] 4.4 Test null analysis_mode renders empty/placeholder - SKIPPED (no test framework)

## Dev Notes

### Architecture References

- **Frontend Component Pattern**: Use shadcn/ui Tooltip component with custom styled badge
- **Badge Pattern**: Follow existing `SourceTypeBadge.tsx` and `SmartDetectionBadge.tsx` patterns in `frontend/components/events/`
- **Type Safety**: Extend existing event types in `frontend/types/event.ts`
- [Source: docs/architecture.md#Frontend-Stack]
- [Source: docs/epics-phase3.md#Story-P3-3.4]

### Project Structure Notes

- New component: `frontend/components/events/AnalysisModeBadge.tsx`
- Modified types: `frontend/types/event.ts` (add analysis_mode, frame_count_used, fallback_reason to IEvent)
- Modified component: `frontend/components/events/EventCard.tsx`

### Learnings from Previous Story

**From Story P3-3.3 (Status: done)**

- **AnalysisModeSelector Component Created**: `frontend/components/cameras/AnalysisModeSelector.tsx` - 226 lines implementing RadioGroup with icons, cost indicators, and tooltips. Use similar icon/color patterns for consistency.
- **Analysis Mode Values**: 'single_frame', 'multi_frame', 'video_native' - same values to use in badge
- **Icons Chosen**: Image (single), Images (multi), Video (video_native) from lucide-react - reuse same icons
- **Cost Indicators**: $ (single), $$ (multi), $$$ (video) - optional for badge display
- **Frontend Testing Blocked**: No testing framework configured (no Jest, Vitest, or React Testing Library) - expect Task 4 to remain blocked
- **shadcn/ui RadioGroup Added**: `frontend/components/ui/radio-group.tsx` now available

**Backend Support Already Exists:**
- Event model has `analysis_mode` (String, nullable), `frame_count_used` (Integer, nullable), `fallback_reason` (String, nullable) fields [Source: backend/app/models/event.py:63-66]
- EventResponse schema includes these fields [Source: backend/app/schemas/event.py:93-97]
- API already returns these fields in event responses

[Source: docs/sprint-artifacts/p3-3-3-build-analysis-mode-selector-ui-component.md#Dev-Agent-Record]

### Technical Notes from Epic

- Create `frontend/components/events/AnalysisModeBadge.tsx`
- Add to EventCard component
- Colors: single=gray, multi=blue, video=purple
- Keep badges small to not clutter timeline
- Use existing badge patterns from SourceTypeBadge.tsx

### References

- [Source: docs/architecture.md#Frontend-Stack]
- [Source: docs/epics-phase3.md#Story-P3-3.4]
- [Source: docs/sprint-artifacts/p3-3-3-build-analysis-mode-selector-ui-component.md]
- [Source: frontend/types/event.ts]
- [Source: frontend/components/events/EventCard.tsx]
- [Source: frontend/components/events/SourceTypeBadge.tsx]
- [Source: backend/app/models/event.py]
- [Source: backend/app/schemas/event.py]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/p3-3-4-display-analysis-mode-on-event-cards.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Frontend build successful with no errors from new code
- Existing lint warnings in other files (not related to this story)

### Completion Notes List

- **Task 1 Complete**: Added `AnalysisMode` type and three new fields (`analysis_mode`, `frame_count_used`, `fallback_reason`) to `IEvent` interface in `frontend/types/event.ts`
- **Task 2 Complete**: Created `AnalysisModeBadge.tsx` component with:
  - Compact badge showing SF/MF/VN abbreviations with appropriate icons (Image/Images/Video)
  - Color coding: gray (single_frame), blue (multi_frame), purple (video_native)
  - Fallback indicator with AlertTriangle icon when fallback_reason is present
  - Tooltip showing full mode name, frame count (for multi-frame), and fallback reason
  - Returns null for null/undefined analysis_mode (legacy events)
- **Task 3 Complete**: Integrated AnalysisModeBadge into EventCard.tsx in the header section alongside SourceTypeBadge
- **Task 4 Skipped**: No frontend testing framework configured (no Jest, Vitest, or React Testing Library)

### File List

| File | Action | Description |
|------|--------|-------------|
| `frontend/types/event.ts` | Modified | Added AnalysisMode type and three new fields to IEvent interface |
| `frontend/components/events/AnalysisModeBadge.tsx` | Created | New component for displaying analysis mode badge with tooltip |
| `frontend/components/events/EventCard.tsx` | Modified | Imported and integrated AnalysisModeBadge component |

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2025-12-06 | 1.0 | Story drafted from epics-phase3.md |
| 2025-12-06 | 2.0 | Implementation complete - all tasks done, ready for review |
| 2025-12-06 | 3.0 | Senior Developer Review - APPROVED |

---

## Senior Developer Review (AI)

### Reviewer
Brent Bengtson (AI-assisted)

### Date
2025-12-06

### Outcome
**APPROVED**

All acceptance criteria fully implemented. All completed tasks verified with code evidence. No HIGH or MEDIUM severity issues found. Implementation follows established patterns and architectural constraints.

### Summary

Clean, well-structured implementation of the AnalysisModeBadge component. The code follows existing badge patterns (SourceTypeBadge, SmartDetectionBadge) and maintains consistency with the AnalysisModeSelector component from Story P3-3.3. All four acceptance criteria are satisfied with proper evidence in the codebase.

### Key Findings

**No HIGH or MEDIUM severity issues found.**

**LOW severity observations:**
- Note: Console logging statements in EventCard.tsx (lines 104, 107) for image load debugging - consider removing for production

### Acceptance Criteria Coverage

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| AC1 | Badge shows SF/MF/VN with icon | IMPLEMENTED | `AnalysisModeBadge.tsx:44-68` MODE_CONFIG, `EventCard.tsx:134-138` integration |
| AC2 | Fallback indicator with tooltip | IMPLEMENTED | `AnalysisModeBadge.tsx:88,100-105,117-120` AlertTriangle icon + tooltip text |
| AC3 | No badge for null/undefined | IMPLEMENTED | `AnalysisModeBadge.tsx:76-79` returns null |
| AC4 | Tooltip with full details | IMPLEMENTED | `AnalysisModeBadge.tsx:91-107,110-130` label, description, frame count, fallback |

**Summary: 4 of 4 acceptance criteria fully implemented**

### Task Completion Validation

| Task | Marked | Verified | Evidence |
|------|--------|----------|----------|
| 1.1 AnalysisMode type | [x] | VERIFIED | `event.ts:18-22` |
| 1.2 analysis_mode field | [x] | VERIFIED | `event.ts:56` |
| 1.3 frame_count_used field | [x] | VERIFIED | `event.ts:57` |
| 1.4 fallback_reason field | [x] | VERIFIED | `event.ts:58` |
| 2.1 Create component | [x] | VERIFIED | `AnalysisModeBadge.tsx` exists |
| 2.2 SF/MF/VN abbreviations | [x] | VERIFIED | `AnalysisModeBadge.tsx:47,56,63` |
| 2.3 Icons Image/Images/Video | [x] | VERIFIED | `AnalysisModeBadge.tsx:17,46,54,62` |
| 2.4 Color coding | [x] | VERIFIED | `AnalysisModeBadge.tsx:50-51,58-59,66-67` |
| 2.5 Handle null/undefined | [x] | VERIFIED | `AnalysisModeBadge.tsx:76-79` |
| 2.6 Fallback indicator | [x] | VERIFIED | `AnalysisModeBadge.tsx:117-120` |
| 2.7 Tooltip implementation | [x] | VERIFIED | `AnalysisModeBadge.tsx:110-130` |
| 3.1 Import into EventCard | [x] | VERIFIED | `EventCard.tsx:16` |
| 3.2 Add near SourceTypeBadge | [x] | VERIFIED | `EventCard.tsx:134-138` |
| 3.3 Compact layout | [x] | VERIFIED | Uses `px-1.5 py-0.5 text-xs h-3` classes |
| 3.4 Pass props | [x] | VERIFIED | `EventCard.tsx:135-137` |
| 4.1-4.4 Tests | [x] SKIPPED | ACCEPTABLE | No test framework - documented correctly |

**Summary: 17 of 17 completed tasks verified, 0 questionable, 0 falsely marked complete**

### Test Coverage and Gaps

- **Frontend Tests**: None (no testing framework configured - known project constraint)
- **Manual Testing**: Required via browser to verify tooltip interactions
- **Backend Tests**: N/A (frontend-only story)

### Architectural Alignment

- Follows shadcn/ui Tooltip pattern as specified
- Uses lucide-react icons consistently with AnalysisModeSelector
- Color coding matches specification (gray/blue/purple)
- Component structure follows existing badge patterns
- TypeScript types properly extend IEvent interface

### Security Notes

No security concerns. Component is purely presentational with no user input handling.

### Best-Practices and References

- React component follows single responsibility principle
- Uses TypeScript for type safety
- Proper accessibility: `aria-hidden`, `sr-only` for screen readers
- Dark mode support included in color classes

### Action Items

**Advisory Notes:**
- Note: Consider removing console.log statements from EventCard.tsx before production (lines 104, 107) - not a blocker
