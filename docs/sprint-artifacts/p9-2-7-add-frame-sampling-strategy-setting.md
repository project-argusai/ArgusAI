# Story 9.2.7: Add Frame Sampling Strategy Setting

Status: done

## Story

As a **user**,
I want **to choose between uniform, adaptive, and hybrid frame sampling**,
So that **I can optimize AI analysis for my specific camera scenarios**.

## Acceptance Criteria

1. **AC-2.7.1:** Given Settings page, when viewing, then sampling strategy selector visible
2. **AC-2.7.2:** Given selector, when clicked, then options uniform/adaptive/hybrid shown
3. **AC-2.7.3:** Given option selected, when saved, then setting persists
4. **AC-2.7.4:** Given new event, when processed, then configured strategy used

## Tasks / Subtasks

- [x] Task 1: Create FrameSamplingStrategySelector component
  - [x] Radio button group with three options
  - [x] Descriptions for each strategy
  - [x] Recommended use cases
- [x] Task 2: Integrate with Settings page
  - [x] Add selector to General settings tab
  - [x] Wire up to settings API
- [x] Task 3: Backend setting support
  - [x] Add settings_frame_sampling_strategy key
  - [x] Read in protect_event_handler
  - [x] Pass to frame extraction service
- [x] Task 4: Write tests

**Note:** This story was already implemented as part of Phase 8 (Story P8-2.5). All functionality verified as working.

## Dev Notes

### Sampling Strategies

- **Uniform:** Fixed interval extraction (every Nth frame)
- **Adaptive:** Content-aware selection using histogram + SSIM comparison
- **Hybrid:** Extract more candidates uniformly, then filter adaptively

### Source Components

- `frontend/components/settings/FrameSamplingStrategySelector.tsx` - Selector component
- `frontend/app/settings/page.tsx` - Integration (line 475-491)
- `backend/app/services/protect_event_handler.py` - Strategy usage (line 1572-1580)

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-2.md#P9-2.7]
- [Source: docs/epics-phase9.md#Story P9-2.7]
- [Backlog: FF-020]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5

### File List

- `frontend/components/settings/FrameSamplingStrategySelector.tsx` - Selector component
- `frontend/app/settings/page.tsx` - Settings page integration
- `backend/app/services/protect_event_handler.py` - Backend strategy handling

