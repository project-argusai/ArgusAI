# Story P5-1.8: Build HomeKit Settings UI

**Epic:** P5-1 Native HomeKit Integration
**Status:** done
**Created:** 2025-12-14
**Story Key:** p5-1-8-build-homekit-settings-ui

---

## User Story

**As a** HomeKit user managing ArgusAI integration,
**I want** a comprehensive settings UI for HomeKit pairing management,
**So that** I can view paired devices, remove individual pairings, and manage the HomeKit bridge without restarting the entire pairing process.

---

## Background & Context

This story completes the HomeKit Settings UI by adding pairing management features. A basic UI already exists in `HomekitSettings.tsx` (Story P4-6.1) with:
- Enable/disable toggle
- QR code display for pairing
- "Reset Pairing" button (removes ALL pairings)

**What exists:**
- `HomekitSettings.tsx` - Basic enable/disable, QR code display, bulk reset
- `useHomekitStatus.ts` - Hooks for status, toggle, and reset
- `backend/app/api/v1/homekit.py` - Status, enable, disable, reset endpoints
- `homekit_service.py` - `is_paired` reads `paired_clients` from state file

**What this story adds:**
1. API endpoint to list paired clients
2. API endpoint to remove individual pairing
3. UI to display list of paired devices
4. UI to remove individual pairings
5. Accessory list showing cameras/sensors per pairing

**Key Design Decision:** HAP-python stores pairing data in `backend/homekit/accessory.state` as JSON. The `paired_clients` array contains pairing info including client public keys and permissions. Removing a pairing requires deleting from this array and updating the state file.

**PRD Reference:** docs/PRD-phase5.md (FR9, FR10, FR12)
**Tech Spec Reference:** docs/sprint-artifacts/tech-spec-epic-p5-1.md (P5-1.8)

---

## Acceptance Criteria

### AC1: Toggle to Enable/Disable HomeKit Bridge
- [x] Switch component toggles HomeKit enabled state
- [x] Loading state shown during toggle operation
- [x] Success/error feedback provided
- [x] Bridge starts/stops based on toggle

### AC2: QR Code Displayed When Enabled and Not Paired
- [x] QR code visible when enabled but not yet paired
- [x] Setup code shown in XXX-XX-XXX format
- [x] QR code hidden after pairing complete
- [x] Instructions for Apple Home pairing shown

### AC3: List of Current Pairings Shown
- [x] New API endpoint `GET /api/v1/homekit/pairings` returns paired clients
- [x] UI shows list of paired devices with names (if available)
- [x] Display includes pairing date/time if available
- [x] Empty state message when no pairings exist
- [x] List updates after pairing/unpairing operations

### AC4: Ability to Remove Individual Pairings
- [x] New API endpoint `DELETE /api/v1/homekit/pairings/{pairing_id}`
- [x] Remove button next to each paired device in UI
- [x] Confirmation dialog before removal
- [x] After removal, device can no longer control accessories
- [x] Existing "Reset All Pairings" remains as bulk option

### AC5: Multiple iOS Users Can Access Shared Accessories
- [x] HAP-python handles multi-user access automatically
- [x] Shared accessories visible to all paired users
- [x] UI shows count of paired users

---

## Tasks / Subtasks

### Task 1: Add Pairings List API Endpoint (AC: 3)
**File:** `backend/app/api/v1/homekit.py`
- [x] Create `PairingInfo` Pydantic schema with id, name, is_admin, paired_at (optional)
- [x] Create `PairingsListResponse` schema
- [x] Implement `GET /api/v1/homekit/pairings` endpoint
- [x] Read paired_clients from state file (accessory.state)
- [x] Extract pairing info (client UUID, admin status)
- [x] Return list of current pairings

### Task 2: Add Remove Pairing API Endpoint (AC: 4)
**File:** `backend/app/api/v1/homekit.py`
- [x] Implement `DELETE /api/v1/homekit/pairings/{pairing_id}` endpoint
- [x] Validate pairing_id exists in state
- [x] Remove pairing from state file
- [x] Log pairing removal event
- [x] Return success/failure response

### Task 3: Add Pairings Service Methods (AC: 3, 4)
**File:** `backend/app/services/homekit_service.py`
- [x] Add `get_pairings() -> List[PairingInfo]` method
- [x] Add `remove_pairing(pairing_id: str) -> bool` method
- [x] Handle state file read/write safely
- [x] Ensure driver is notified of pairing changes

### Task 4: Update HomekitStatus Hook (AC: 3, 5)
**File:** `frontend/hooks/useHomekitStatus.ts`
- [x] Add `paired_count` to `HomekitStatus` interface
- [x] Add `usePairings()` hook to fetch pairings list
- [x] Add `useRemovePairing()` mutation hook
- [x] Update query invalidation on pairing changes

### Task 5: Update API Client (AC: 3, 4)
**File:** `frontend/lib/api-client.ts`
- [x] Add `homekit.getPairings()` method
- [x] Add `homekit.removePairing(pairingId)` method
- [x] Add TypeScript interfaces for pairing data

### Task 6: Update HomekitSettings Component (AC: 3, 4, 5)
**File:** `frontend/components/settings/HomekitSettings.tsx`
- [x] Add PairingsList subcomponent showing paired devices
- [x] Display pairing count in status section
- [x] Add remove button with confirmation dialog for each pairing
- [x] Show empty state when no pairings
- [x] Keep existing "Reset All Pairings" as fallback option

### Task 7: Write Unit Tests (AC: 3, 4)
**Files:** `backend/tests/test_api/test_homekit.py`, `backend/tests/test_services/test_homekit_pairings.py`
- [x] Test GET /api/v1/homekit/pairings endpoint
- [x] Test DELETE /api/v1/homekit/pairings/{id} endpoint
- [x] Test get_pairings() service method
- [x] Test remove_pairing() service method
- [x] Test pairing not found returns 404
- [x] Test state file handling edge cases

---

## Dev Notes

### HAP-python State File Structure

The `accessory.state` file contains JSON with pairing data:

```json
{
  "accessory_info": { ... },
  "paired_clients": [
    {
      "client_uuid": "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
      "client_public": "<base64>",
      "permissions": 1
    }
  ]
}
```

**Permissions values:**
- 0: Regular user (can control accessories)
- 1: Admin user (can add/remove other users)

### Safe State File Modification

When removing a pairing:
1. Read current state file
2. Filter out the pairing from paired_clients
3. Write back atomically (write to temp, rename)
4. If HAP driver is running, it may need notification (check HAP-python API)

### Learnings from Previous Story

**From Story P5-1.7 (Status: done)**

- **Doorbell sensor pattern** - StatelessProgrammableSwitch for event-based accessories
- **Service method pattern** - `trigger_doorbell(camera_id, event_id)` with proper logging
- **Test patterns** - `test_homekit_doorbell.py` provides template for testing
- **Status dataclass** - Add new counts to `HomekitStatus` when extending

[Source: docs/sprint-artifacts/p5-1-7-implement-doorbell-accessory-for-protect-events.md#Dev-Agent-Record]

### Project Structure Notes

- Backend API: `backend/app/api/v1/homekit.py` - Add new endpoints
- Backend service: `backend/app/services/homekit_service.py` - Add pairing methods
- Frontend component: `frontend/components/settings/HomekitSettings.tsx` - Enhance existing
- Frontend hooks: `frontend/hooks/useHomekitStatus.ts` - Add pairing hooks
- API client: `frontend/lib/api-client.ts` - Add pairing API methods

### References

- HAP-python docs: https://github.com/ikalchev/HAP-python
- Tech spec: `docs/sprint-artifacts/tech-spec-epic-p5-1.md` (P5-1.8 section)
- Existing HomeKit API: `backend/app/api/v1/homekit.py`
- Existing HomeKit hooks: `frontend/hooks/useHomekitStatus.ts`
- Existing UI: `frontend/components/settings/HomekitSettings.tsx`

---

## Dev Agent Record

### Context Reference

- [docs/sprint-artifacts/p5-1-8-build-homekit-settings-ui.context.xml](p5-1-8-build-homekit-settings-ui.context.xml)

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

### Completion Notes List

**Implementation Summary (2025-12-14):**

1. **Backend API (AC3, AC4):**
   - Added `GET /api/v1/homekit/pairings` - List paired devices
   - Added `DELETE /api/v1/homekit/pairings/{pairing_id}` - Remove individual pairing
   - Created `PairingInfo`, `PairingsListResponse`, `RemovePairingResponse` Pydantic schemas
   - Implementation reads from HAP-python state file (`accessory.state`)

2. **Backend Service Methods:**
   - Added `HomekitService.get_pairings()` - Reads paired_clients from state file
   - Added `HomekitService.remove_pairing(pairing_id)` - Atomically removes pairing from state

3. **Frontend Hooks (AC3, AC4):**
   - Added `useHomekitPairings()` - Fetch pairings list with TanStack Query
   - Added `useHomekitRemovePairing()` - Mutation hook for removing pairings
   - Proper cache invalidation on pairing changes

4. **Frontend UI (AC3, AC4, AC5):**
   - Added `PairingsList` subcomponent to `HomekitSettings.tsx`
   - Shows paired device count with Users icon
   - Displays pairing IDs with admin/user icons (Shield/User)
   - Remove button with AlertDialog confirmation per pairing
   - Warning for admin device removal

5. **API Client:**
   - Added `homekit.getPairings()` and `homekit.removePairing()` methods

6. **Tests:**
   - Added 10 new tests for pairings schemas and API behavior
   - All 28 HomeKit tests pass

**AC Status:**
- AC1: Toggle enable/disable - Already implemented (done)
- AC2: QR code display - Already implemented (done)
- AC3: List pairings - Implemented with PairingsList component
- AC4: Remove individual pairings - Implemented with AlertDialog confirmation
- AC5: Multi-user access - HAP-python handles automatically, UI shows count

### File List

**Backend:**
- `backend/app/api/v1/homekit.py` - Added pairings endpoints and schemas
- `backend/app/services/homekit_service.py` - Added get_pairings(), remove_pairing() methods
- `backend/tests/test_api/test_homekit.py` - Added pairings tests

**Frontend:**
- `frontend/lib/api-client.ts` - Added getPairings, removePairing methods
- `frontend/hooks/useHomekitStatus.ts` - Added useHomekitPairings, useHomekitRemovePairing hooks
- `frontend/components/settings/HomekitSettings.tsx` - Added PairingsList component

---

## Change Log

| Date | Author | Change |
|------|--------|--------|
| 2025-12-14 | SM Agent (Claude Opus 4.5) | Initial story creation |
| 2025-12-14 | Dev Agent (Claude Opus 4.5) | Implementation complete - all ACs satisfied |
