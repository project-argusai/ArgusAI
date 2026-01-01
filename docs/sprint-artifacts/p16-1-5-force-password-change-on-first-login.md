# Story P16-1.5: Force Password Change on First Login

Status: done

## Story

As a **new user**,
I want **to be required to change my temporary password**,
So that **my account is secured with a password only I know**.

## Acceptance Criteria

1. ✅ Given I log in with a temporary password, When my account has `must_change_password=true`, Then I am redirected to a "Change Password" page before accessing any other page
2. ✅ Given I am on the Change Password page, When I enter a new password meeting requirements (8+ chars, 1 upper, 1 lower, 1 number), Then my password is updated, And `must_change_password` is set to false, And I am redirected to the dashboard
3. ✅ Given I try to navigate away from Change Password page, When `must_change_password=true`, Then I am redirected back to Change Password page
4. ✅ The Change Password page shows password requirements
5. ✅ A password strength indicator shows weak/medium/strong (shows requirement checklist)

## Tasks / Subtasks

- [x] Task 1: Review existing implementation (AC: 1, 2, 4, 5)
  - [x] Found change-password page already implemented (Story P15-2.6)
  - [x] Login page already redirects on `must_change_password`
  - [x] Backend already clears flag after password change
  - [x] Password requirements and strength indicator exist
- [x] Task 2: Implement navigation protection (AC: 3)
  - [x] Updated `ProtectedRoute.tsx` to redirect if `must_change_password=true`
  - [x] Added loading state while redirecting
- [x] Task 3: Update AppShell for clean UI (AC: 1)
  - [x] Added `/change-password` to `AUTH_NO_LAYOUT_ROUTES`
  - [x] Change password page now renders without Header/Sidebar
- [x] Task 4: Verify lint passes
  - [x] No new lint errors introduced

## Dev Notes

### Implementation Summary

Most of P16-1.5 was already implemented in Story P15-2.6. This story added the critical missing piece: **preventing users from bypassing the password change by navigating directly to other pages**.

### Changes Made

1. **`frontend/components/auth/ProtectedRoute.tsx`**:
   - Added check for `user?.must_change_password`
   - Redirects to `/change-password` if flag is true
   - Shows "Redirecting to password change..." while transitioning
   - Prevents rendering protected content until password is changed

2. **`frontend/components/layout/AppShell.tsx`**:
   - Added `AUTH_NO_LAYOUT_ROUTES` array with `/change-password`
   - Change password page now renders without Header/Sidebar/DesktopToolbar
   - Still wrapped in ProtectedRoute for authentication

### Existing Implementation (from P15-2.6)

- `frontend/app/change-password/page.tsx` - Full-screen password change form
- Password validation: 8+ chars, 1 uppercase, 1 lowercase, 1 number, 1 special char
- Visual checklist showing which requirements are met
- Backend `POST /api/v1/auth/change-password` clears `must_change_password` flag

### Flow

```
Login → Check must_change_password → Redirect to /change-password
                                           ↓
                               User enters new password
                                           ↓
                               Validation passes → API call
                                           ↓
                               must_change_password = false
                                           ↓
                               Redirect to dashboard
```

### Edge Cases Handled

- User tries to navigate to `/events` directly → Redirected to `/change-password`
- User refreshes on `/change-password` → Page loads correctly
- User changes password successfully → Can now access all routes

### References

- [Source: frontend/components/auth/ProtectedRoute.tsx] - Navigation protection
- [Source: frontend/components/layout/AppShell.tsx] - Layout handling
- [Source: frontend/app/change-password/page.tsx] - Password change UI

## Dev Agent Record

### Context Reference

N/A - Built on P15-2.6 implementation

### Agent Model Used

Claude Opus 4.5

### Debug Log References

No issues encountered

### Completion Notes List

- P16-1.5 builds on P15-2.6 which implemented the change-password page
- The missing piece was preventing navigation bypass
- Now users cannot access any protected route until password is changed

### File List

| File | Status | Description |
|------|--------|-------------|
| `frontend/components/auth/ProtectedRoute.tsx` | MODIFIED | Added must_change_password redirect |
| `frontend/components/layout/AppShell.tsx` | MODIFIED | Added change-password to no-layout routes |
