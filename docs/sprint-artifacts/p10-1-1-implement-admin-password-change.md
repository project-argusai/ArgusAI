# Story P10-1.1: Implement Admin Password Change

Status: done

## Story

As a **user**,
I want **to change my admin password through the Settings UI**,
so that **I can maintain account security**.

## Acceptance Criteria

1. **Given** I navigate to Settings
   **When** I view the settings tabs
   **Then** I see a "Security" or "Account" tab (or section within General)

2. **Given** I view the password section
   **When** I look at the form
   **Then** I see fields for: Current Password, New Password, Confirm New Password

3. **Given** I enter my current password correctly and a valid new password
   **When** I submit the form
   **Then** my password is updated in the database
   **And** a success toast appears "Password updated successfully"
   **And** my session remains active

4. **Given** I enter an incorrect current password
   **When** I submit the form
   **Then** an error message appears "Current password is incorrect"
   **And** my password is not changed

5. **Given** I enter a weak new password (missing requirements)
   **When** I submit the form
   **Then** an error message shows password requirements

6. **Given** new password and confirm password don't match
   **When** I try to submit
   **Then** form validation prevents submission
   **And** error message shows "Passwords do not match"

## Tasks / Subtasks

- [x] Task 1: Verify backend API exists (AC: all)
  - [x] Subtask 1.1: Check `POST /api/v1/auth/change-password` endpoint
  - [x] Subtask 1.2: Verify it validates current password
  - [x] Subtask 1.3: Verify password strength validation
  - [x] Result: Backend API exists and is complete at `backend/app/api/v1/auth.py:250-302`

- [x] Task 2: Add API client method for password change (AC: 3-5)
  - [x] Subtask 2.1: Add `changePassword` method to `apiClient.auth` in `lib/api-client.ts`
  - [x] Subtask 2.2: Define request/response types
  - [x] Result: API client method already existed at `frontend/lib/api-client.ts:955-960`

- [x] Task 3: Create PasswordChangeForm component (AC: 1-6)
  - [x] Subtask 3.1: Create `frontend/components/settings/PasswordChangeForm.tsx`
  - [x] Subtask 3.2: Implement form with react-hook-form + zod validation
  - [x] Subtask 3.3: Add current password, new password, confirm password fields
  - [x] Subtask 3.4: Add password visibility toggles
  - [x] Subtask 3.5: Add password strength indicator
  - [x] Subtask 3.6: Handle API errors and display appropriate messages

- [x] Task 4: Integrate into Settings page (AC: 1)
  - [x] Subtask 4.1: Add to General tab or create Security section
  - [x] Subtask 4.2: Wrap in Card component with appropriate header

- [x] Task 5: Write tests (AC: all)
  - [x] Subtask 5.1: Unit tests for PasswordChangeForm component
  - [x] Subtask 5.2: Test validation (matching passwords, strength requirements)
  - [x] Subtask 5.3: Test API error handling

## Dev Notes

### Backend API Already Complete

The backend endpoint exists at `backend/app/api/v1/auth.py`:
- `POST /api/v1/auth/change-password`
- Request: `{ current_password: string, new_password: string }`
- Response: `{ message: string }` on success, 400 on error
- Password requirements: 8+ chars, uppercase, number, special char
- Uses `validate_password_strength()` from `app/utils/auth.py`

### Frontend Implementation Pattern

Follow existing settings form patterns:
- Use `react-hook-form` with `zodResolver` for validation
- Use shadcn/ui components: Input, Button, Card, Label
- Use `toast` from sonner for success/error notifications
- Match styling of existing settings forms

### Password Validation Schema (Zod)

```typescript
const passwordChangeSchema = z.object({
  currentPassword: z.string().min(1, 'Current password is required'),
  newPassword: z.string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least 1 uppercase letter')
    .regex(/[0-9]/, 'Password must contain at least 1 number')
    .regex(/[^A-Za-z0-9]/, 'Password must contain at least 1 special character'),
  confirmPassword: z.string(),
}).refine(data => data.newPassword === data.confirmPassword, {
  message: 'Passwords do not match',
  path: ['confirmPassword'],
});
```

### Project Structure Notes

- Component: `frontend/components/settings/PasswordChangeForm.tsx`
- API client: `frontend/lib/api-client.ts` (add to `auth` namespace)
- Settings page: `frontend/app/settings/page.tsx` (integrate component)
- Tests: `frontend/__tests__/components/settings/PasswordChangeForm.test.tsx`

### References

- Backend endpoint: [Source: backend/app/api/v1/auth.py#250-302]
- Auth schemas: [Source: backend/app/schemas/auth.py#32-35]
- Settings page patterns: [Source: frontend/app/settings/page.tsx]
- Security architecture: [Source: docs/architecture/security-architecture.md]

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/p10-1-1-implement-admin-password-change.context.xml

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- Backend API (`POST /api/v1/auth/change-password`) was already implemented at `backend/app/api/v1/auth.py:250-302`
- Frontend API client method was already implemented at `frontend/lib/api-client.ts:955-960`
- Created PasswordChangeForm component with Zod validation, password visibility toggles, and strength indicator
- Integrated component into Settings page General tab
- All 11 tests pass covering: field rendering, visibility toggles, validation errors, API submission, error handling, loading states, form clearing

### File List

- `frontend/components/settings/PasswordChangeForm.tsx` (created)
- `frontend/app/settings/page.tsx` (modified - added PasswordChangeForm import and usage)
- `frontend/__tests__/components/settings/PasswordChangeForm.test.tsx` (created)

