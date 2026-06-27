# P16-6.1 Multi-Entity Events – Technical Design Document

**Story**: P16-6.1 Research Multi-Entity Data Model  
**Status**: Draft (to be completed by the research execution)  
**GitHub**: #302  
**Date**: 2026-01-XX  
**Author**: TBD (researcher)

---

## Executive Summary

This document captures the findings and recommendation from the P16-6.1 research story. It defines the canonical data model for associating one or more `RecognizedEntity` records with an `Event`, the migration path from the current mixed state (`matched_entity_ids` JSON + `entity_events` junction), and the concrete changes required for stories P16-6.2–6.4.

**Primary Recommendation (preview)**: Make the `entity_events` junction table the single source of truth. Keep `matched_entity_ids` as a derived/compat JSON field (populated by a DB trigger or application-layer sync during a transition window). Update all manual assignment paths and response serializers to support lists.

---

## 1. Current State Audit (to be filled by research)

### 1.1 Read/Write Inventory

| Location | Reads `matched_entity_ids` (JSON) | Writes JSON | Reads `entity_events` | Writes junction | Notes |
|----------|-----------------------------------|-------------|-----------------------|-----------------|-------|
| `event_processor.py:1709` (recognition) | No | Yes (list) | No | Yes (via entity_service) | Builds list from face+vehicle embeddings |
| `entity_service.assign_event()` | No | No | Yes (` .first() `) | Yes (replace or insert) | Enforces single today |
| `entity_alert_service.py` | Yes (in several places) | Sometimes | Via `get_entities_by_ids` | No | Needs update for multi |
| `ai_processing_coordinator.py` | Indirect | No | Indirect | No | Enriches singular `matched_entity` |
| `context.py` event endpoints | Via schemas | No | Via service | No | Returns singular today |
| `get_entity_events*()` | No | No | Yes (join) | No | Already correct for multi |
| Frontend EventCard / types | N/A | N/A | N/A | N/A | Consumes singular `entity_id/name` |

### 1.2 Data Consistency Snapshot (example – replace with real numbers)

- Total events: X
- Events with ≥1 EntityEvent row: Y (Z%)
- Events where `len(JSON)` != junction count: W (drift rate)
- Max entities per event observed: N (usually 1–2 from auto recognition)

### 1.3 Hot Path Performance

- Entity detail "recent events" query: already uses junction → scales to multi.
- Event list response enrichment: currently does cheap singular lookup → will need small join or aggregation view.

---

## 2. Option Comparison

### Option A – Dual Maintenance (JSON + Junction)
- Pros: Minimal schema change, fast JSON reads for alerts.
- Cons: Two sources of truth, drift risk, more code to keep in sync.

### Option B – Junction as Source of Truth + Derived JSON (Recommended)
- Junction is authoritative.
- JSON is populated on write (application or trigger) for backward-compat API clients that still read the old column.
- Pros: One canonical store, leverages existing indexes and queries, clean migration.
- Cons: One-time backfill + dual-write window.

### Option C – Junction Only, Drop JSON Column
- Aggressive cleanup.
- Requires API versioning or careful deprecation of the singular fields.

**Recommendation**: B (with a clear deprecation timeline for the JSON column after 2–3 releases).

---

## 3. Proposed Data Model Changes

No new tables.

**Possible small additions** (to be confirmed):
- New index on `entity_events (event_id, entity_id)` if not already optimal.
- Optional `source` column on `EntityEvent` (`'auto' | 'manual'`) for debugging/audit (nice-to-have).

**Event table**:
- `matched_entity_ids` kept (Text/JSON) as derived field during transition.
- New helper view or property `matched_entities` (list of summaries) will be computed in the service layer.

---

## 4. Migration Strategy (Zero-Downtime)

**Phase 0 (this story)**: Audit + design (read-only).

**Phase 1 (P16-6.2)**:
- Add `MULTI_ENTITY_ENABLED` feature flag (default false).
- Update `assign_event` (and new `assign_entities` method) to accept list, create multiple `EntityEvent` rows, update occurrence counts correctly, create multiple `EntityAdjustment` records.
- Update recognition path (if needed) to always ensure junction rows exist.
- Add consistency repair helper.

**Phase 2**:
- Backfill script: for every event that has JSON but missing junction rows, create the missing links (idempotent).
- Verification queries run in prod.

**Phase 3**:
- Change all response serializers to return `matched_entities: [...]` array (keep singular fields populated from first element for compat).
- Update frontend.
- Flip feature flag for new assignments.

**Phase 4** (future):
- Stop writing the JSON column.
- Remove the column after all clients are updated (or keep forever as cheap compat).

Rollback: Feature flag + the repair script can revert links if needed. JSON column acts as safety net.

---

## 5. API & Schema Changes (Target Shapes)

See the concrete examples already written in `story-P16-6.1.md`.

New endpoint (or overloaded):
- `POST /api/v1/context/events/{event_id}/entities` (array)
- Keep old singular endpoint during transition (maps to single-item list).

Event response will grow a `matched_entities: MatchedEntitySummary[]` while preserving the old singular fields (first element or null).

---

## 6. Frontend Impact

- `EntitySelectModal`: add `multi?: boolean` prop. When true → checkboxes + `selectedIds: string[]`, `onSelectMany(ids)`.
- `EventCard`: render 0–N small `EntityBadge` components (reuse or new small pill).
- Types: add `matched_entities?: Array<...>`; keep `entity_id/name` for backward compat in components.
- Confirmation dialog text updated for "N entities will trigger re-classification".

---

## 7. Alert Rule & Dispatch Impact

- `AlertRule.entity_id` (singular today) → consider evolving to `entity_ids: string[]` (any match) or keep singular + new "any of these" mode.
- `EntityAlertService` already accepts `List[str]` in several internal methods — mostly just needs the call sites updated to pass the full list from the event.

---

## 8. Testing & Verification Plan

- New integration test: create event → auto-match 2 entities → manual add 3rd → assert 3 junction rows + correct counts + alert fires for any of them.
- Consistency monitor (can be turned into a health check later).
- Load test entity with 1000 events.

---

## 9. Rollback & Safety

Documented in the story plan. All changes behind flag + reversible repair script.

---

## 10. Open Questions for Team Review

1. Do we want to expose "source" (auto vs manual) on the entity badges in the UI?
2. Should alert rules support "all of" in addition to "any of"?
3. Deprecation timeline for the old singular `entity_id` / `matched_entity` fields in the public event API?

---

**Appendix**: Links to all code locations audited, raw diagnostic query results, and the option scoring spreadsheet (to be attached after research execution).

---

*This is a living design doc. Update it throughout the research and subsequent implementation stories.*