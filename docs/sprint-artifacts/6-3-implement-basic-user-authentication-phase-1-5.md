# Story 6.3: Implement Basic User Authentication (Phase 1.5)

Status: ready-for-dev

## Story

As a **user**,
I want **to log in with a username and password**,
so that **my camera system is protected from unauthorized access**.

## Acceptance Criteria

1. **Login Redirect** - Unauthenticated access handling
   - When a user accesses the dashboard without authentication
   - Then they are redirected to `/login`
   - [Source: docs/epics.md#Story-6.3]

2. **Authentication Implementation** - Core auth mechanics
   - Method: Username + password
   - Password hashing: bcrypt with cost factor 12
   - Session management: JWT tokens
   - Token storage: HTTP-only cookies (secure, SameSite)
   - Token expiration: 24 hours
   - [Source: docs/epics.md#Story-6.3]

3. **Database Schema** - User table migration
   - New table: `users` (id, username, password_hash, created_at, last_login)
   - Username: Unique, 3-50 characters, alphanumeric + underscore
   - Password hash: bcrypt hash string (60 chars)
   - Default user: Created on first setup (username: admin, password: randomly generated)
   - [Source: docs/epics.md#Story-6.3]

4. **Login Endpoint** - POST /api/v1/auth/login
   - Request body: `{"username": "admin", "password": "password"}`
   - Validation: Username exists, password matches hash
   - Success: Return JWT token, set HTTP-only cookie, 200 OK
   - Failure: Return 401 Unauthorized, "Invalid credentials"
   - Rate limiting: Max 5 attempts per 15 minutes
   - [Source: docs/epics.md#Story-6.3]

5. **JWT Token** - Token structure and validation
   - Payload: `{"user_id": "uuid", "username": "admin", "exp": timestamp}`
   - Signing: HS256 with secret key from environment (`JWT_SECRET_KEY`)
   - Expiration: 24 hours from issuance
   - Validate: Signature, expiration, user exists
   - [Source: docs/epics.md#Story-6.3]

6. **Authentication Middleware** - API protection
   - Intercept all API requests (except /health, /login, /metrics)
   - Check for JWT in cookie or Authorization header
   - Validate token: Signature, expiration, user active
   - Add user context to request (request.state.user)
   - Reject if invalid: 401 Unauthorized
   - [Source: docs/epics.md#Story-6.3]

7. **Logout Endpoint** - POST /api/v1/auth/logout
   - Clear JWT cookie (set max-age=0)
   - Return 200 OK
   - [Source: docs/epics.md#Story-6.3]

8. **Frontend Login Page** - /login route
   - Route: `/login`
   - Form: Username input, password input, "Login" button
   - Validation: Required fields, username min length
   - Submit: POST to `/api/v1/auth/login`
   - Success: Redirect to `/` or original requested page
   - Error: Show error message "Invalid username or password"
   - [Source: docs/epics.md#Story-6.3]

9. **Protected Routes** - Frontend route protection
   - All dashboard routes require authentication
   - Redirect to `/login` if not authenticated
   - After login: Redirect back to originally requested page
   - Logout button in user menu (header dropdown)
   - [Source: docs/epics.md#Story-6.3]

10. **Password Management** - Basic password operations
    - Change password: `POST /api/v1/auth/change-password` (requires current password)
    - Password requirements: 8+ characters, 1 uppercase, 1 number, 1 special char
    - [Source: docs/epics.md#Story-6.3]

## Tasks / Subtasks

- [ ] Task 1: Create User database model and migration (AC: #3)
  - [ ] Create `backend/app/models/user.py` with User model
  - [ ] Add id, username, password_hash, created_at, last_login fields
  - [ ] Create Alembic migration for users table
  - [ ] Add unique constraint on username
  - [ ] Create initial admin user setup script

- [ ] Task 2: Implement password hashing utilities (AC: #2)
  - [ ] Install bcrypt package (`pip install bcrypt`)
  - [ ] Create `backend/app/utils/auth.py` with hash/verify functions
  - [ ] Hash with cost factor 12
  - [ ] Write unit tests for password hashing

- [ ] Task 3: Implement JWT token utilities (AC: #5)
  - [ ] Install python-jose package (`pip install python-jose[cryptography]`)
  - [ ] Add JWT_SECRET_KEY to config.py and .env
  - [ ] Create `backend/app/utils/jwt.py` with create/decode functions
  - [ ] Implement token expiration (24 hours)
  - [ ] Write unit tests for JWT creation/validation

- [ ] Task 4: Create authentication API endpoints (AC: #4, #7, #10)
  - [ ] Create `backend/app/api/v1/auth.py` router
  - [ ] Implement POST /api/v1/auth/login endpoint
  - [ ] Implement POST /api/v1/auth/logout endpoint
  - [ ] Implement POST /api/v1/auth/change-password endpoint
  - [ ] Add rate limiting with slowapi (5 attempts/15 min)
  - [ ] Register auth router in main.py
  - [ ] Write integration tests for auth endpoints

- [ ] Task 5: Implement authentication middleware (AC: #6)
  - [ ] Create `backend/app/middleware/auth_middleware.py`
  - [ ] Extract JWT from cookie or Authorization header
  - [ ] Validate token and fetch user
  - [ ] Add user to request.state
  - [ ] Exclude /health, /login, /metrics, /docs from auth
  - [ ] Add middleware to FastAPI app
  - [ ] Write tests for middleware

- [ ] Task 6: Create frontend login page (AC: #8)
  - [ ] Create `/frontend/app/login/page.tsx`
  - [ ] Build login form with username/password fields
  - [ ] Add form validation (required, min length)
  - [ ] Handle form submission to /api/v1/auth/login
  - [ ] Display error messages
  - [ ] Redirect to dashboard on success

- [ ] Task 7: Implement frontend auth context and protection (AC: #9)
  - [ ] Update `/frontend/contexts/AuthContext.tsx` with real auth
  - [ ] Create ProtectedRoute wrapper component
  - [ ] Update layout to check auth status
  - [ ] Add redirect to /login for unauthenticated users
  - [ ] Implement returnUrl handling for post-login redirect
  - [ ] Add logout button to header user menu

- [ ] Task 8: Testing and validation (AC: #1-10)
  - [ ] Write unit tests for auth utilities (bcrypt, JWT)
  - [ ] Write integration tests for auth endpoints
  - [ ] Test login flow end-to-end
  - [ ] Test protected route redirection
  - [ ] Verify rate limiting works
  - [ ] Run `npm run build` and `npm run lint` for frontend
  - [ ] Run pytest for backend

## Dev Notes

### Architecture Context

From `docs/architecture.md`:
- Authentication uses JWT tokens stored in HTTP-only cookies
- Backend middleware for API protection
- Frontend uses React Context for auth state
- Protected routes redirect to /login

### Learnings from Previous Story

**From Story 6-2-add-comprehensive-logging-and-monitoring (Status: done)**

- **Middleware Pattern**: RequestLoggingMiddleware at `backend/app/middleware/logging_middleware.py` - follow same pattern for auth middleware
- **Import pattern**: `from app.middleware.logging_middleware import ...` - middleware package now exists
- **Config Pattern**: Settings from `app.core.config` - add JWT_SECRET_KEY here
- **Test Pattern**: Unit tests in `backend/tests/test_core/` - follow for auth tests
- **Frontend Pattern**: Status page uses api-client.ts pattern - follow for auth API
- **Review Finding**: No critical issues - clean patterns to follow

[Source: docs/sprint-artifacts/6-2-add-comprehensive-logging-and-monitoring.md#Dev-Agent-Record]

### Technical Implementation Notes

**Dependencies to Add (requirements.txt):**
```
bcrypt>=4.0.0
python-jose[cryptography]>=3.3.0
slowapi>=0.1.9
```

**Environment Variables (.env):**
```
JWT_SECRET_KEY=your-super-secret-key-change-in-production
```

**User Model Example:**
```python
class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(60), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
```

**JWT Token Pattern:**
```python
from jose import jwt, JWTError
from datetime import datetime, timedelta

def create_access_token(user_id: str, username: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": expire
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm="HS256")
```

### Files to Create/Modify

**New Files:**
- `/backend/app/models/user.py` - User SQLAlchemy model
- `/backend/app/utils/auth.py` - Password hashing utilities
- `/backend/app/utils/jwt.py` - JWT token utilities
- `/backend/app/api/v1/auth.py` - Auth API endpoints
- `/backend/app/middleware/auth_middleware.py` - Auth middleware
- `/backend/tests/test_utils/test_auth.py` - Auth utility tests
- `/backend/tests/test_api/test_auth.py` - Auth API tests
- `/frontend/app/login/page.tsx` - Login page
- `/frontend/components/auth/ProtectedRoute.tsx` - Route protection

**Modify:**
- `/backend/requirements.txt` - Add bcrypt, python-jose, slowapi
- `/backend/app/core/config.py` - Add JWT_SECRET_KEY
- `/backend/main.py` - Add auth middleware, auth router
- `/frontend/contexts/AuthContext.tsx` - Real auth implementation
- `/frontend/components/layout/Header.tsx` - Add logout button

### References

- [PRD: Security Requirements](../prd.md)
- [Architecture: Authentication](../architecture.md)
- [Epics: Story 6.3](../epics.md#Story-6.3)
- [Story 6.2: Middleware Pattern](./6-2-add-comprehensive-logging-and-monitoring.md) - middleware pattern reference

## Dev Agent Record

### Context Reference

- docs/sprint-artifacts/6-3-implement-basic-user-authentication-phase-1-5.context.xml

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

## Change Log

| Date | Version | Description |
|------|---------|-------------|
| 2025-11-23 | 1.0 | Story drafted from epics.md Story 6.3 |
