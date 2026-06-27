# Phase B Decomposition Slice 3: Standardize Recognition Settings Access in Face and Vehicle Processing

**Parent Epic:** [Phase B: Architectural Refactoring #443](https://github.com/project-argusai/ArgusAI/issues/443)  
**Previous:** Slice 2 – Standardized Recognition Gating (face/vehicle enabled flags)  
**Status:** Proposed  
**Effort:** XS  

---

## 1. User Story

**As a** backend developer working on the long-term health of `event_processor.py`,  
**I want** the remaining direct `SystemSetting` queries inside `_process_faces()` and `_process_vehicles()` to use the same typed constants and modern session patterns established in Slice 2,  
**so that** we continue the incremental reduction of legacy patterns in the largest remaining hotspot while keeping each change tiny, reviewable, and low-risk.

---

## 2. Acceptance Criteria

- [ ] All remaining magic string queries for recognition settings inside `_process_faces()` and `_process_vehicles()` are replaced with constants from `ai_types.py`.
- [ ] The affected constants are added if they do not already exist (`PERSON_MATCH_THRESHOLD`, `AUTO_CREATE_PERSONS`, `UPDATE_APPEARANCE_ON_HIGH_MATCH`, `VEHICLE_MATCH_THRESHOLD`, `AUTO_CREATE_VEHICLES`).
- [ ] All reads continue to use `get_db_session()` (no regression to raw `SessionLocal()`).
- [ ] No change in matching behavior or logging.
- [ ] Relevant tests continue to pass.
- [ ] The chunk document is updated with completion notes.

---

## 3. Concrete Examples

### Current code pattern (in `_process_faces`)

```python
threshold_setting = db.query(SystemSetting).filter(
    SystemSetting.key == "person_match_threshold"
).first()
auto_create_setting = db.query(SystemSetting).filter(
    SystemSetting.key == "auto_create_persons"
).first()
update_appearance_setting = db.query(SystemSetting).filter(
    SystemSetting.key == "update_appearance_on_high_match"
).first()

threshold = float(threshold_setting.value) if threshold_setting else 0.70
auto_create = auto_create_setting.value.lower() == "true" if auto_create_setting else True
update_appearance = update_appearance_setting.value.lower() == "true" if update_appearance_setting else True
```

### Target pattern (after Slice 3)

```python
from app.services.ai_types import (
    PERSON_MATCH_THRESHOLD,
    AUTO_CREATE_PERSONS,
    UPDATE_APPEARANCE_ON_HIGH_MATCH,
)

threshold = _get_recognition_setting_float(db, PERSON_MATCH_THRESHOLD, default=0.70)
auto_create = _get_recognition_setting_bool(db, AUTO_CREATE_PERSONS, default=True)
update_appearance = _get_recognition_setting_bool(db, UPDATE_APPEARANCE_ON_HIGH_MATCH, default=True)
```

Or (preferred): Move the default + parsing logic into the `person_matching_service` / `vehicle_matching_service` so `EventProcessor` no longer needs to read these settings at all.

---

## 4. Design / UX Samples

N/A — internal backend refactoring.

---

## 5. Laws of UX Mapping

**Tesler’s Law**: Continue shifting complexity and configuration knowledge out of the large `EventProcessor` class and into dedicated services or a small shared settings helper.

**Jakob’s Law**: The code now behaves consistently with the patterns introduced in Slice 2 and earlier Phase B work.

---

## 6. 12-Factor Alignment

- **III. Config**: Moves more configuration access toward typed, centralized constants.
- **VI & IX**: Continued use of `get_db_session()` improves process isolation and disposability.

This slice directly supports the AGENTS.md standing goal: *"Reduce magic `SystemSetting` string keys"*.

---

## 7. Technical Notes

**Primary locations:**
- `backend/app/services/event_processor.py`:
  - `_process_faces()` (lines ~1483–1496)
  - `_process_vehicles()` (symmetric block around line ~1613)

**Constants to introduce (or confirm) in `ai_types.py`:**
- `PERSON_MATCH_THRESHOLD`
- `AUTO_CREATE_PERSONS`
- `UPDATE_APPEARANCE_ON_HIGH_MATCH`
- `VEHICLE_MATCH_THRESHOLD`
- `AUTO_CREATE_VEHICLES`

**Better long-term direction (for later slices):**
The ideal end state is that `face_embedding_service` + `person_matching_service` (and their vehicle equivalents) read their own configuration internally. `EventProcessor` should only decide *whether* to run the processing (already improved in Slice 2).

This slice is the incremental step that makes that future extraction easier.

---

## 8. Testing Strategy

- Run the face/vehicle related portions of the event processor test suite.
- Existing integration paths that exercise person/vehicle matching will validate behavior.
- No new unit tests required for this standardization slice (pattern is already covered by prior slices).

---

## 9. Effort Sizing

**XS** — Almost identical in scope and risk to Slice 2. Pure pattern application on two symmetric methods.

---

## 10. Rollback / Safety Plan

- Extremely low risk. The queries are read-only and only affect logging + matching behavior that already has test coverage.
- Revert of the specific hunks is trivial.

---

## Implementation Tasks (for when approved)

1. Add the five recognition settings constants to `ai_types.py`.
2. Refactor the settings reading block inside `_process_faces()`.
3. Refactor the equivalent block inside `_process_vehicles()`.
4. Remove any now-unused local `SystemSetting` imports in those methods.
5. Run targeted tests.
6. Update this document with completion record.

---

## Why This Slice Next?

- Natural, low-risk continuation of the highly successful Slice 2 work.
- Removes the last cluster of recognition-related magic strings inside `event_processor.py`.
- Keeps each increment tiny (critical for maintaining review velocity on a 2,500+ line file).
- Sets up easier future structural extractions (e.g., "Move all recognition configuration into the services").

---

**This is proposed as Slice 3.** Ready for review and "this is good, implement" approval.

---

## Dev Agent Record

### Agent Model Used
Grok 4.3 (following AGENTS.md Phase B micro-chunk process)

### Completion Notes
- User approved the chunk with "This is good, implement".
- Added five new typed constants to `ai_types.py`:
  - `PERSON_MATCH_THRESHOLD`
  - `AUTO_CREATE_PERSONS`
  - `UPDATE_APPEARANCE_ON_HIGH_MATCH`
  - `VEHICLE_MATCH_THRESHOLD`
  - `AUTO_CREATE_VEHICLES`
- Refactored the settings reading blocks in both `_process_faces()` and `_process_vehicles()`:
  - Replaced all remaining magic `SystemSetting.key` strings with the new constants.
  - Removed local `from app.models.system_setting import SystemSetting` imports inside the methods.
  - Added clear "Phase B Slice 3" comments for traceability.
- No behavior change to person or vehicle matching logic.
- Import verification passed.
- Full `test_event_processor.py` suite shows no new regressions (same 5 pre-existing failures as before).
- This slice completes the standardization of recognition-related SystemSetting access inside `event_processor.py`.

### File List
- `backend/app/services/ai_types.py` — Added five new recognition settings constants
- `backend/app/services/event_processor.py` — Updated two methods + import + local import cleanup
- `docs/sprint-artifacts/phase-b-slice-3-event-processor-recognition-settings.md` — This document (updated with completion record)

### Change Log

| Date       | Change                                      | Author |
|------------|---------------------------------------------|--------|
| 2026-05-22 | Chunk proposed and approved                 | User   |
| 2026-05-22 | Implementation of Slice 3 completed         | Grok   |

---

**Slice 3 complete.** 

This brings the total number of standardized recognition settings in `event_processor.py` to a much cleaner state. The file is now ready for the next incremental step.

---

*Document created following AGENTS.md micro-chunk requirements.*