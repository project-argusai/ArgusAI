# Epic Technical Specification: Entity UX Improvements

Date: 2025-12-30
Author: Brent
Epic ID: P15-1
Status: Draft

---

## Overview

Epic P15-1 addresses critical UX friction in entity management by fixing modal scrolling issues, enabling seamless event navigation from entity modals, and implementing virtual scrolling for performance with large event lists. This epic directly responds to user feedback about entity modal overflow and navigation difficulties identified during Phase 14.

## Objectives and Scope

**In Scope:**
- Entity detail modal scrolling for long event lists (FR23)
- Virtual scrolling implementation for 1000+ events (FR24)
- Click-through from entity modal events to event detail (FR25)
- Back navigation preserving entity modal state (FR26)
- Event count and scroll position indicators (FR27)

**Out of Scope:**
- Entity creation/editing (existing functionality)
- Entity matching algorithm changes (covered in P14-6)
- Multi-entity event support (P15-4)

## System Architecture Alignment

This epic focuses on frontend component improvements with no backend changes required. Key architecture components:

- **@tanstack/react-virtual** - Virtual scrolling library (ADR-P15-004)
- **EntityDetailModal.tsx** - Primary component being modified
- **EventDetailModal.tsx** - Target for navigation
- **React state management** - For modal stacking and state preservation

Reference: [Phase 15 Architecture](../architecture/phase-15-additions.md#adr-p15-004-virtual-scrolling-for-entity-events)

## Detailed Design

### Services and Modules

| Component | Responsibility | Owner |
|-----------|---------------|-------|
| `EntityDetailModal.tsx` | Display entity details with scrollable event list | Frontend |
| `EntityEventList.tsx` | Virtual scrolling wrapper for events | Frontend (new) |
| `EventDetailModal.tsx` | Display event details (existing) | Frontend |
| React Context/State | Manage modal stack and navigation | Frontend |

### Data Models and Contracts

No new data models required. Existing models used:

```typescript
// Entity from existing api-client.ts
interface Entity {
  id: string;
  name: string;
  type: string;
  avatar_url?: string;
  event_count?: number;
}

// Event from existing api-client.ts
interface Event {
  id: string;
  description: string;
  created_at: string;
  thumbnail_path?: string;
  // ... other existing fields
}
```

### APIs and Interfaces

No new API endpoints. Existing endpoints used:

- `GET /api/v1/entities/{id}/events` - Fetch entity's events (paginated)
- `GET /api/v1/events/{id}` - Fetch event detail

### Workflows and Sequencing

**Modal Navigation Flow:**

```
User clicks entity card
       │
       ▼
┌─────────────────────────────┐
│   EntityDetailModal opens   │
│   - Loads entity + events   │
│   - Virtual scroll active   │
└─────────────────────────────┘
       │
User clicks event in list
       │
       ▼
┌─────────────────────────────┐
│   EventDetailModal opens    │
│   - Entity modal preserved  │
│   - Stacked on top          │
└─────────────────────────────┘
       │
User closes event modal (X/Esc/backdrop)
       │
       ▼
┌─────────────────────────────┐
│   Returns to EntityModal    │
│   - Scroll position kept    │
│   - Same event highlighted  │
└─────────────────────────────┘
```

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| Modal load time (1000+ events) | < 500ms | NFR7 |
| Scroll frame rate | 60fps | Browser DevTools |
| Memory usage | < 50 DOM nodes | React DevTools |

### Security

No security implications - read-only UI components.

### Reliability/Availability

- Modal should handle empty event lists gracefully
- Network errors during event fetch show retry option
- Virtual scroller handles dynamic list updates

### Observability

- Console warnings if virtual scroller row height mismatch > 20%
- React Query DevTools for cache inspection

## Dependencies and Integrations

| Dependency | Version | Purpose |
|------------|---------|---------|
| @tanstack/react-virtual | ^3.0.0 | Virtual scrolling |
| @tanstack/react-query | ^5.x | Data fetching (existing) |
| radix-ui/dialog | ^1.x | Modal primitives (existing) |

No new backend dependencies required.

## Acceptance Criteria (Authoritative)

1. **AC1:** Entity detail modal with 50+ events displays scrollable event list with max-height constraint
2. **AC2:** Scroll through 1000+ events maintains 60fps performance
3. **AC3:** Modal header and footer remain sticky during scroll
4. **AC4:** Event list shows "Showing X-Y of Z" scroll position indicator
5. **AC5:** Clicking event item opens EventDetailModal without closing EntityDetailModal
6. **AC6:** Closing EventDetailModal returns to EntityDetailModal with preserved scroll position
7. **AC7:** Event count badge displays accurately in modal header
8. **AC8:** Virtual scrolling activates when event count exceeds 50

## Traceability Mapping

| AC | Spec Section | Component | Test Idea |
|----|--------------|-----------|-----------|
| AC1 | Scrolling Fix | EntityDetailModal | Render modal with 100 events, verify scroll |
| AC2 | Virtual Scrolling | EntityEventList | Performance test with 1000 events |
| AC3 | Scrolling Fix | EntityDetailModal | Verify sticky header/footer CSS |
| AC4 | Scroll Indicator | EntityEventList | Scroll and verify indicator updates |
| AC5 | Event Navigation | EntityDetailModal | Click event, verify stacked modal |
| AC6 | Back Navigation | Modal Stack | Close nested modal, verify state |
| AC7 | Event Count | EntityDetailModal | Verify count matches API response |
| AC8 | Virtual Threshold | EntityEventList | Test 49 vs 51 events behavior |

## Risks, Assumptions, Open Questions

**Risks:**
- **Risk:** Row height inconsistency breaks scroll position accuracy
  - *Mitigation:* Use fixed row height, test with various event content lengths

**Assumptions:**
- Assumption: Existing EventDetailModal can be rendered as stacked modal without refactoring
- Assumption: React Query cache handles event data without duplicate fetches

**Open Questions:**
- Q: Should scroll position persist across modal close/reopen?
  - *Recommendation:* No, reset on reopen for consistent UX

## Test Strategy Summary

**Unit Tests:**
- EntityEventList virtual scroller initialization
- Row height calculation
- Scroll position indicator math

**Integration Tests:**
- Modal stacking behavior
- State preservation on navigation
- Event click handlers

**E2E Tests (Playwright):**
- Full flow: Open entity → scroll → click event → close → verify position
- Performance: Load 1000 events, measure frame rate

**Manual Testing:**
- Visual inspection of scroll indicators
- Keyboard navigation (Tab, Escape)
- Touch scrolling on mobile
