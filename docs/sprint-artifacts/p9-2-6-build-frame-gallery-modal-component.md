# Story 9.2.6: Build Frame Gallery Modal Component

Status: done

## Story

As a **user**,
I want **to click on an event thumbnail to see all analyzed frames**,
So that **I can understand what the AI saw and verify accuracy**.

## Acceptance Criteria

1. **AC-2.6.1:** Given event card, when clicking thumbnail, then frame gallery modal opens
2. **AC-2.6.2:** Given modal open, when viewing, then all frames displayed in navigable gallery
3. **AC-2.6.3:** Given gallery, when navigating, then keyboard support (arrows, Escape)
4. **AC-2.6.4:** Given gallery, when viewing frame, then timestamp offset displayed

## Tasks / Subtasks

- [x] Task 1: Create FrameGalleryModal component
  - [x] Modal with lightbox-style frame display
  - [x] Navigation between frames (prev/next buttons)
  - [x] Current frame indicator (e.g., "3 of 10")
- [x] Task 2: Add keyboard navigation
  - [x] Arrow keys for prev/next
  - [x] Escape to close modal
- [x] Task 3: Show frame metadata
  - [x] Display timestamp offset for each frame
- [x] Task 4: Integrate with EventCard
  - [x] Clickable thumbnail opens gallery
  - [x] Film icon button for multiple frames
- [x] Task 5: Add API endpoint for frames
  - [x] GET /api/v1/events/{id}/frames
- [x] Task 6: Write tests

**Note:** This story was already implemented as part of Phase 8 (Story P8-2.2). All functionality verified as working.

## Dev Notes

### Source Components

- `frontend/components/events/FrameGalleryModal.tsx` - Gallery modal component
- `frontend/components/events/EventCard.tsx` - Thumbnail click integration
- `backend/app/api/v1/events.py` - Frames endpoint

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-2.md#P9-2.6]
- [Source: docs/epics-phase9.md#Story P9-2.6]
- [Backlog: FF-020]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5

### File List

- `frontend/components/events/FrameGalleryModal.tsx` - Frame gallery modal
- `frontend/components/events/EventCard.tsx` - Event card with clickable thumbnail

