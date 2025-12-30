# Story P14-3.9: Add Missing API Route Tests

Status: drafted

## Story

As a **developer**,
I want all API routes to have test coverage,
So that endpoint behavior is verified and security-critical modules are regression-tested.

## Acceptance Criteria

1. **AC1**: Security-critical modules have 80%+ test coverage:
   - `auth.py` - Login, logout, session management, password change
   - `api_keys.py` - Key CRUD, authentication validation
   - `mobile_auth.py` - Device pairing, token exchange, token refresh

2. **AC2**: `test_auth.py` covers all endpoints:
   - POST /auth/login - success, invalid credentials, disabled account
   - POST /auth/logout - clears cookie
   - POST /auth/change-password - success, wrong current password, weak password
   - GET /auth/me - returns current user
   - GET /auth/setup-status - returns user count

3. **AC3**: `test_api_keys.py` covers all endpoints:
   - POST /api-keys - create key with valid scopes
   - GET /api-keys - list keys (with/without revoked)
   - GET /api-keys/{id} - get single key
   - DELETE /api-keys/{id} - revoke key
   - GET /api-keys/{id}/usage - get usage stats

4. **AC4**: `test_mobile_auth.py` covers all endpoints:
   - POST /mobile/auth/pair - generate pairing code
   - POST /mobile/auth/confirm - confirm code (requires auth)
   - GET /mobile/auth/status/{code} - check pairing status
   - POST /mobile/auth/exchange - exchange code for tokens
   - POST /mobile/auth/refresh - refresh access token
   - POST /mobile/auth/revoke - revoke tokens

5. **AC5**: `test_notifications.py` covers all endpoints:
   - GET /notifications - list with filtering
   - PATCH /notifications/{id}/read - mark single as read
   - PATCH /notifications/mark-all-read - mark all as read
   - DELETE /notifications/{id} - delete single
   - DELETE /notifications - bulk delete

6. **AC6**: Tests use TestClient with proper authentication
7. **AC7**: Tests cover both success and error paths
8. **AC8**: All existing tests continue to pass

## Tasks / Subtasks

- [ ] Task 1: Create test_auth.py (AC: #1, #2, #6, #7)
  - [ ] 1.1 Create test file with imports and fixtures
  - [ ] 1.2 Add tests for POST /auth/login (success, failure cases)
  - [ ] 1.3 Add tests for POST /auth/logout
  - [ ] 1.4 Add tests for POST /auth/change-password (success, failures)
  - [ ] 1.5 Add tests for GET /auth/me
  - [ ] 1.6 Add tests for GET /auth/setup-status

- [ ] Task 2: Create test_api_keys.py (AC: #1, #3, #6, #7)
  - [ ] 2.1 Create test file with imports and fixtures
  - [ ] 2.2 Add tests for POST /api-keys (create key, validation)
  - [ ] 2.3 Add tests for GET /api-keys (list, filter)
  - [ ] 2.4 Add tests for GET /api-keys/{id}
  - [ ] 2.5 Add tests for DELETE /api-keys/{id}
  - [ ] 2.6 Add tests for GET /api-keys/{id}/usage

- [ ] Task 3: Create test_mobile_auth.py (AC: #1, #4, #6, #7)
  - [ ] 3.1 Create test file with imports and fixtures
  - [ ] 3.2 Add tests for POST /mobile/auth/pair
  - [ ] 3.3 Add tests for POST /mobile/auth/confirm
  - [ ] 3.4 Add tests for GET /mobile/auth/status/{code}
  - [ ] 3.5 Add tests for POST /mobile/auth/exchange
  - [ ] 3.6 Add tests for POST /mobile/auth/refresh
  - [ ] 3.7 Add tests for POST /mobile/auth/revoke

- [ ] Task 4: Create test_notifications.py (AC: #5, #6, #7)
  - [ ] 4.1 Create test file with imports and fixtures
  - [ ] 4.2 Add tests for GET /notifications
  - [ ] 4.3 Add tests for PATCH /notifications/{id}/read
  - [ ] 4.4 Add tests for PATCH /notifications/mark-all-read
  - [ ] 4.5 Add tests for DELETE /notifications/{id}
  - [ ] 4.6 Add tests for DELETE /notifications (bulk)

- [ ] Task 5: Validate all tests pass (AC: #8)
  - [ ] 5.1 Run pytest for new test files
  - [ ] 5.2 Run full test suite to verify no regressions
  - [ ] 5.3 Check coverage for new files

## Dev Notes

### Priority Order

Per the tech spec, security-critical modules should be tested first:
1. `auth.py` - Core authentication (login/logout/session)
2. `api_keys.py` - API key management (external access)
3. `mobile_auth.py` - Mobile device pairing and tokens
4. `notifications.py` - User-facing notifications

### Testing Patterns

From existing test files (`test_cameras.py`, `test_events.py`):
- Use `fastapi.testclient.TestClient`
- Use `db_session` fixture for database isolation
- Mock external services (AI providers, cameras)
- Create test users with proper authentication

### Authentication in Tests

```python
from app.api.v1.auth import get_current_user
from app.models.user import User

@pytest.fixture
def authenticated_client(api_client, db_session):
    """Create client with authenticated user."""
    user = User(
        id=str(uuid.uuid4()),
        username="testuser",
        password_hash=hash_password("TestPass123!"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # Override the get_current_user dependency
    def override_get_current_user():
        return user

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield api_client
    app.dependency_overrides.clear()
```

### Rate Limiting Consideration

`auth.py` uses `slowapi` for rate limiting (5 attempts/15 min).
Tests should either:
- Mock the rate limiter
- Use separate test keys
- Run in sequence with resets

### Learnings from Previous Story

**From Story P14-3.8 (Status: done)**

- Factory functions added: `make_event`, `make_camera`, `make_alert_rule`, `make_entity`
- Each factory accepts `**overrides` for customization and optional `db_session` for persistence
- Pytest fixtures `sample_camera`, `sample_event`, `sample_alert_rule`, `sample_entity` now available globally
- Use shared fixtures from `conftest.py` rather than redefining

[Source: docs/sprint-artifacts/P14-3-8-consolidate-test-fixture-definitions.md#Dev-Agent-Record]

### Project Structure Notes

- Test files: `backend/tests/test_api/test_*.py`
- API routes: `backend/app/api/v1/*.py`
- API fixtures: `backend/tests/test_api/conftest.py`
- Global fixtures: `backend/tests/conftest.py`

### References

- [Source: docs/epics-phase14.md#Story-P14-3.9]
- [Source: docs/sprint-artifacts/tech-spec-epic-P14-3.md#Story-P14-3.9]
- [Source: backend/app/api/v1/auth.py]
- [Source: backend/app/api/v1/api_keys.py]
- [Source: backend/app/api/v1/mobile_auth.py]
- [Source: backend/app/api/v1/notifications.py]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

### File List

