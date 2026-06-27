# Story P16-6.1: Research Multi-Entity Data Model

**Epic:** P16-6 - Multi-Entity Events  
**Status:** drafted  
**Priority:** Low (Growth)  
**GitHub Issue:** #302 (IMP-069)  
**FRs Covered:** FR36-FR40

## Story

**As a** developer,  
**I want** to understand the best approach for supporting multiple entities per event (e.g., two people walking together or a person with a vehicle),  
**So that** I can implement the feature correctly without creating technical debt or breaking existing single-entity events, automatic recognition, manual assignments, alert rules, and entity timelines.

## Acceptance Criteria

- [ ] **AC1**: Given the current data model (`matched_entity_ids` JSON Text column on `events` + existing `entity_events` junction table), when I audit all read/write paths, then I produce a complete inventory of every location that touches either representation.
- [ ] **AC2**: Given a running system (dev or prod snapshot), when I run diagnostic queries, then I report:
  - Total events with 0, 1, 2+ EntityEvent links
  - Consistency rate between `len(matched_entity_ids JSON)` and actual junction row count for the same events
  - Any events that have junction rows but empty JSON (or vice versa)
- [ ] **AC3**: Given the evaluation of Option A (keep/enhance JSON + junction) vs Option B (make junction the single source of truth, JSON as read-only derived/compat field) vs Option C (junction only, remove JSON), then I document pros/cons for query performance (entity event lists, event cards, alert evaluation), backward compatibility for existing API clients, migration complexity, and risk.
- [ ] **AC4**: Given the research findings, when I recommend a primary approach, then the recommendation explicitly justifies the choice against: query perf on hot paths (event list + entity detail), support for multi-entity alert rules ("any of"), manual assignment UX, and automatic recognition output.
- [ ] **AC5**: And I create a complete technical design document at `docs/sprint-artifacts/p16-6-1-multi-entity-design.md` that includes:
  - Recommended data model + schema changes (if any)
  - Migration strategy (zero-downtime, dual-write period, backfill)
  - Updated API request/response shapes (examples for assign, event GET, entity events)
  - Impact on alert rule engine and EntityAlertService
  - Frontend changes required (EntitySelectModal → multi-select, EventCard badges, types)
  - Rollback plan
- [ ] **AC6**: The design document includes concrete before/after DB state examples, sample JSON payloads, and a phased implementation roadmap for stories 6.2–6.4.

## Concrete Examples

### Current Single-Entity Event (from GET /api/v1/events/{id} or list)
```json
{
  "id": "evt_abc123",
  "timestamp": "2026-01-15T14:22:00Z",
  "description": "A person walked up the driveway",
  "entity_id": "ent_person_987",
  "entity_name": "Brent (Homeowner)",
  "matched_entity": { "id": "ent_person_987", "name": "Brent (Homeowner)", "type": "person" },
  "matched_entity_ids": "[\"ent_person_987\"]"
}
```

### Desired Multi-Entity Event (target shape for P16-6)
```json
{
  "id": "evt_def456",
  "timestamp": "2026-01-15T14:25:00Z",
  "description": "Two people and a vehicle approached the front door",
  "matched_entities": [
    { "id": "ent_person_987", "name": "Brent (Homeowner)", "type": "person", "similarity": 0.92, "source": "auto" },
    { "id": "ent_person_432", "name": "Visitor - Sarah", "type": "person", "similarity": 0.81, "source": "manual" },
    { "id": "ent_vehicle_55", "name": "Blue Toyota Camry", "type": "vehicle", "similarity": 0.88, "source": "auto" }
  ],
  "matched_entity_ids": "[\"ent_person_987\",\"ent_person_432\",\"ent_vehicle_55\"]"   // kept for compat during transition
}
```

### Current Assign Request (singular, will become array in 6.2)
```json
POST /api/v1/context/events/evt_def456/entity
{ "entity_id": "ent_person_432" }
```

### Target Multi-Assign Request
```json
POST /api/v1/context/events/evt_def456/entities
{
  "entity_ids": ["ent_person_432", "ent_vehicle_55"],
  "reason": "manual"
}
```

### DB State Example (current mixed reality research must quantify)
- Event `evt_def456` has 3 rows in `entity_events` (one per entity) with similarity scores.
- Its `events.matched_entity_ids` column may contain only 1 or 2 IDs (or be stale) because manual assign path only touches junction + occurrence counts, not the JSON.

### Alert Rule Impact (FR40)
Current (P12-1): `entity_id` filter matches events where the (singular) link equals the rule's entity.
Future: Rule with `entity_ids: ["ent_person_987"]` should fire if **any** of the event's matched entities matches.

## Design / UX Samples (for downstream stories, captured here)

**Event Card (multi badges)** – ASCII wireframe:
```
┌─────────────────────────────────────────────────────────────┐
│ [thumb]  Two people at door + vehicle                       │
│          Brent (Homeowner)  Visitor-Sarah  Blue Toyota      │
│          [View] [Re-analyze] [Assign]                       │
└─────────────────────────────────────────────────────────────┘
```
- Max 3 badges visible, `+N more` overflow (Miller’s Law).
- Clicking any badge opens that EntityDetail (Fitts’s Law – large targets).
- Distinct styling for mixed person/vehicle groups (Von Restorff).

**EntitySelectModal (multi-select mode)**:
- Checkboxes instead of single radio/click-to-select.
- "Select all visible" + search still works.
- Summary footer: "3 entities selected – re-classification will run for all".
- Existing "Don't show again" confirmation dialog text updated to mention multiple.

**Entity Detail page**:
- "Co-occurring events" section already queries via junction (good).
- Timeline will naturally show events where this entity is one of several.

Accessibility: All new badges/buttons get `aria-label`, keyboard navigable, high-contrast.

## Laws of UX Mapping

1. **Miller’s Law (Chunking)**: Multi-entity events will be represented as small, scannable badges (max 3 + overflow) rather than a long list. This prevents cognitive overload on event cards and timelines.
2. **Von Restorff Effect (Isolation)**: Group events (person + vehicle, multiple people) will use subtle visual differentiation (e.g., mixed icons or a "group" badge treatment) so they stand out from ordinary single-entity events without being alarming.
3. **Fitts’s Law**: The "Assign" action and individual entity badges will remain large, easy targets. Multi-select will use familiar checkbox patterns users already know from other apps (Jakob’s Law).

Trade-off: Adding multi-select slightly increases complexity in the assignment modal (Hick’s Law), mitigated by progressive disclosure (single-select remains the 90% path; multi is opt-in via "Add another" or a toggle).

## 12-Factor Alignment

- **Factor IV (Backing services)**: The `entity_events` junction table is the attached backing store for relationships. All access goes through `EntityService` methods (no direct SQL in API routes).
- **Factor VI (Processes)**: Stateless workers (event_processor, alert evaluation) will read the canonical relationship from the DB only. No in-memory singletons holding "current entities for event".
- **Factor IX (Disposability)**: Any migration or dual-write logic will be idempotent and safe to restart. Research will define the exact dual-write window and verification queries.
- **Factor XI (Logs)**: All research diagnostic queries and future assignment operations will emit structured JSON logs with `event_id`, `entity_ids[]`, `action`, `source` (auto vs manual).
- **Factor XII (Admin processes)**: Any backfill or consistency repair will be a separate one-off script (e.g., `scripts/fix_multi_entity_consistency.py`) invocable via alembic or dedicated admin command, never inside the web server.

No violations introduced; the story explicitly improves data modeling hygiene.

## Technical Notes

**Relevant files / components (to audit during research):**
- **Models**: `backend/app/models/event.py` (matched_entity_ids JSON), `backend/app/models/recognized_entity.py` (RecognizedEntity + EntityEvent junction – already exists since P4)
- **Services**:
  - `backend/app/services/entity_service.py`: `assign_event()`, `get_entity_events*()`, `match_or_create_entity()`
  - `backend/app/services/event_processor.py`: recognition path + `_link_entity_to_event()` (already builds list)
  - `backend/app/services/entity_alert_service.py`: reads `matched_entity_ids` for alert dispatch
  - `backend/app/services/ai_processing_coordinator.py`: response enrichment
- **API**: `backend/app/api/v1/context.py`: `assign_event_to_entity`, entity detail + events endpoints, event schemas
- **Schemas**: `backend/app/schemas/event.py`, `backend/app/schemas/context.py` (MatchedEntitySummary etc.)
- **Frontend**:
  - `frontend/components/entities/EntitySelectModal.tsx` (single-select today)
  - `frontend/components/events/EventCard.tsx` (singular entity badge)
  - `frontend/types/event.ts`, `frontend/lib/api-client.ts`
  - `frontend/components/entities/EntityDetail.tsx`, `EntityEventList.tsx`
- **Alert rules**: `backend/app/services/alert_engine.py` + rule evaluation for entity filter (P12-1)
- **DB**: Current `entity_events` table + indexes; potential new composite indexes or partial indexes for multi queries

**Performance considerations**:
- Entity event lists already join the junction (good).
- Event list responses that currently do a singular lookup will need to become a small join or cached aggregation if we keep the JSON.
- Alert evaluation must remain <5s p95 even when rules have entity lists.

**Security / Privacy**:
- No new PII exposure; entity-event links are internal.
- Manual multi-assign still creates `EntityAdjustment` rows for audit/learning (existing behavior).

**Dependencies**:
- P16-4 (Entity Assignment UX confirmation dialog) – the multi version will extend it.
- P12-1 (Entity-based alert rules) – will need extension for "any of" semantics.
- No hard blocker; research can be done in isolation.

## Testing Strategy

- **Research phase (this story)**: Manual diagnostic scripts + pytest that assert on current DB shape (no behavior change yet). Example: `test_multi_entity_audit.py` that counts links vs JSON and fails if unexpected drift is discovered.
- **Later stories**: 
  - Unit tests for new multi-assign service method and schema serializers.
  - Integration tests: create event, auto-recognize 2 entities, manually add a 3rd, verify both JSON and junction are consistent, verify entity detail shows the event, verify alert fires for any of the three.
  - E2E: Playwright flow through multi-select assignment on an event card and on entity detail.
  - Performance: query timing for entity with 500+ events before/after any indexing changes.
- All new endpoints/schemas will have contract tests via the existing OpenAPI-generated client.

## Effort Sizing

**S** – Research + inventory + one design document. No production code changes in this story. (If the audit reveals surprising data corruption, may grow to M, but expected to stay S.)

## Rollback / Safety Plan

- Research produces only a document and optional diagnostic queries/scripts (committed to `scripts/audit_multi_entity.py`).
- No schema changes, no data writes.
- If the recommended path requires a migration, the design doc will include:
  - Forward migration (add columns/indexes if needed)
  - Dual-write period with feature flag (`MULTI_ENTITY_ASSIGN_ENABLED`)
  - Verification queries that can be run in production before cutting over
  - Reverse migration (documented but never auto-applied)
- All findings will be captured in the design doc and also summarized in the GitHub issue #302 for stakeholder review before P16-6.2 begins.

## Dev Notes

### Technical Context
- The junction table `entity_events` was introduced in Phase 4 (P4-8 / P4-3) for the temporal context engine and is already the canonical store for "which events belong to this entity" (used by `get_entity_events*` and entity detail pages).
- Automatic recognition (`event_processor.py` + `entity_service.match_or_create_entity`) can and does produce multiple links per event (face + vehicle embeddings).
- Manual user assignment (`/events/{id}/entity` + `entity_service.assign_event`) still assumes and enforces a single link (`.first()`, replace semantics).
- The `matched_entity_ids` JSON column on Event is written primarily on the recognition hot path and is used by `EntityAlertService` and some response enrichment, but the manual assign path does **not** keep it in sync.
- This story is pure research + design. Code changes begin in P16-6.2.

### Key Questions the Research Must Answer
1. How many real events in production have >1 entity today via automatic recognition?
2. Is the JSON column ever the source of truth for anything the junction cannot answer faster?
3. What is the cheapest path to support multi-assign in the UI while keeping alert rules, occurrence counts, and EntityAdjustment audit trail correct?
4. Should we expose a single `matched_entities: [...]` array in all event responses going forward (breaking the old singular fields gracefully)?

### References
- [Epic P16-6 in docs/epics-phase16.md](docs/epics-phase16.md#Epic-P16-6)
- [PRD Phase 16 – Multi-Entity Events section](docs/PRD-phase16.md)
- [GitHub Issue #302](https://github.com/project-argusai/ArgusAI/issues/302)
- Existing junction usage: `backend/app/services/entity_service.py:1054` (get_entity_events), `backend/app/models/recognized_entity.py:205`
- Current singular assign: `backend/app/api/v1/context.py:988` + `entity_service.py:1304`
- Recognition multi handling: `backend/app/services/event_processor.py:1709` (building the list) and `entity_alert_service.py`

### Learnings from Related Work
- P12-1 (Entity Alert Rules) and P16-4 (Assignment UX) both assumed single-entity and will need targeted extensions.
- P15-5 (AI Annotations) and P10-4 (Entity assignment from cards) already proved the value of per-entity feedback and re-classification.

## Dev Agent Record

### Context Reference
<!-- To be populated by BMAD context workflow when story is activated -->

### Agent Model Used
TBD (research + synthesis)

### Debug Log References
N/A (this story is read-only analysis)

### Completion Notes List
- [ ] Full path inventory completed (models, services, API, frontend, alert engine)
- [ ] Diagnostic audit queries executed against realistic dataset; results table added to design doc
- [ ] Option comparison matrix (A/B/C) with scoring
- [ ] `p16-6-1-multi-entity-design.md` written, reviewed, and linked here
- [ ] Recommended approach + phased rollout plan approved by user

### File List (to be updated on completion)
- `docs/sprint-artifacts/p16-6-1-multi-entity-design.md` (new – primary output)
- `scripts/audit_multi_entity_consistency.py` (optional diagnostic helper)
- `docs/sprint-artifacts/stories/story-P16-6.1.md` (this file)

### Change Log

| Date       | Change                          | Author      |
|------------|---------------------------------|-------------|
| 2026-01-XX | Story plan created (research scope defined) | Grok (following AGENTS.md) |

---

**Next Step (after this story is approved)**: Execute the research, produce the design doc, then use `/bmad:bmm:workflows:create-story` (or equivalent) to generate detailed plans for P16-6.2 (backend multi-entity support), P16-6.3 (event card multi-badge UI), and P16-6.4 (multi-select assignment modal + alert updates).

This story deliberately stays small (S) and research-only so the team can make an informed decision before touching hot paths or user-facing assignment flows.