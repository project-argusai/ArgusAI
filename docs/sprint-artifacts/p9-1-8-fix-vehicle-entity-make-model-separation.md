# Story 9.1.8: Fix Vehicle Entity Make/Model Separation

Status: done

## Story

As a **user**,
I want **different vehicles to be tracked as separate entities**,
So that **I can see the history of each vehicle (e.g., my car vs delivery trucks)**.

## Acceptance Criteria

1. **AC-1.8.1:** Given "white Toyota Camry" in description, when entity extracted, then color=white, make=Toyota, model=Camry
2. **AC-1.8.2:** Given "black Ford F-150" in description, when entity extracted, then separate entity from Toyota
3. **AC-1.8.3:** Given same vehicle in multiple events, when matching, then events grouped together
4. **AC-1.8.4:** Given different vehicles, when viewing Entities page, then shown as separate entities

## Tasks / Subtasks

- [x] Task 1: Enhance regex to extract color + make + model together
- [x] Task 2: Create vehicle signature (color-make-model) for matching
- [x] Task 3: Update vehicle characteristics extraction
- [x] Task 4: Add signature-based matching alongside embedding matching
- [x] Task 5: Write unit tests for vehicle extraction
- [x] Task 6: Run tests to verify

## Implementation

### Backend Changes

**backend/app/services/vehicle_matching_service.py:**
- Enhanced `_extract_vehicle_characteristics()` to parse full vehicle descriptions
- Added comprehensive regex patterns for color + make + model extraction
- Added `vehicle_signature` field combining color-make-model (e.g., "white-toyota-camry")
- Added signature-based entity lookup alongside embedding matching
- Extended make list with more manufacturers

## Dev Notes

### Vehicle Signature Format

```
{color}-{make}-{model}
```
Examples:
- "white-toyota-camry"
- "black-ford-f150"
- "silver-honda-civic"

### Extraction Priority

1. Full pattern: "white Toyota Camry" -> color=white, make=Toyota, model=Camry
2. Color + make only: "white Toyota" -> color=white, make=Toyota
3. Make only: "Toyota" -> make=Toyota

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P9-1.md#P9-1.8]
- [Source: docs/epics-phase9.md#Story P9-1.8]
- [Backlog: BUG-011]

## Dev Agent Record

### Agent Model Used

Claude Opus 4.5

### Test Results

- Backend tests: 2976 passed, 7 skipped
- Vehicle matching tests: 34 passed (including 8 new signature tests)
- Frontend build: passed

### File List

- backend/app/services/vehicle_matching_service.py (modified)
- backend/tests/test_services/test_vehicle_matching_service.py (modified - added TestVehicleSignatureExtraction class)

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-22 | Claude Opus 4.5 | Enhanced vehicle extraction with make/model separation |

