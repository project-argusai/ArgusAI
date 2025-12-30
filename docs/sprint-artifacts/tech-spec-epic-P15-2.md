# Epic Technical Specification: Authentication & User Management

Date: 2025-12-30
Author: Brent
Epic ID: P15-2
Status: Draft

---

## Overview

Epic P15-2 transforms ArgusAI from a single-user system to a production-ready multi-user platform. This epic implements proper user authentication, session management with device tracking, and role-based access control. It replaces the Phase 1.5 stub authentication with enterprise-grade security controls, enabling family deployments and team access.

## Objectives and Scope

**In Scope:**
- User model with email, password, roles (FR1-FR9)
- Session tracking with device/IP metadata (FR10-FR16)
- Role-based permissions: Admin, Operator, Viewer (FR17-FR22)
- User invitation flow with temporary passwords
- Force password change on first login
- Session list view with revocation
- User management admin UI

**Out of Scope:**
- OAuth/SSO integration (future phase)
- Two-factor authentication (future phase)
- Password reset via email (requires email service setup)
- API key authentication (implemented in P13-1)

## System Architecture Alignment

This epic introduces core authentication infrastructure:

- **User & Session Models** - New database tables with proper indexing
- **PasswordService** - bcrypt hashing with cost factor 12 (ADR-P15-002)
- **SessionService** - JWT tokens with server-side session tracking (ADR-P15-001)
- **RBAC Middleware** - FastAPI dependencies for permission enforcement (ADR-P15-003)

Reference: [Phase 15 Architecture](../architecture/phase-15-additions.md#phase-15-service-architecture)

## Detailed Design

### Services and Modules

| Service/Module | Responsibility | Files |
|----------------|---------------|-------|
| User Model | Store user accounts | `backend/app/models/user.py` |
| Session Model | Track active sessions | `backend/app/models/session.py` |
| PasswordService | Hash/verify passwords, validate complexity | `backend/app/services/password_service.py` |
| SessionService | Create/revoke sessions, enforce limits | `backend/app/services/session_service.py` |
| Users Router | User CRUD endpoints | `backend/app/api/v1/users.py` |
| Auth Router | Session management endpoints | `backend/app/api/v1/auth.py` (extended) |
| Permissions | RBAC dependency decorators | `backend/app/core/permissions.py` |
| UserManagement UI | Admin user list/actions | `frontend/components/settings/UserManagement.tsx` |
| SessionList UI | Active sessions display | `frontend/components/settings/SessionList.tsx` |

### Data Models and Contracts

**User Model:**

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,                    -- UUID
    email TEXT UNIQUE NOT NULL,             -- Login email
    password_hash TEXT NOT NULL,            -- bcrypt hash (cost 12)
    role TEXT NOT NULL DEFAULT 'viewer',    -- 'admin', 'operator', 'viewer'
    is_active BOOLEAN DEFAULT TRUE,         -- Account enabled/disabled
    must_change_password BOOLEAN DEFAULT FALSE,
    password_expires_at TIMESTAMP,          -- For temporary passwords (72h)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login_at TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

**Session Model:**

```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,                    -- UUID
    user_id TEXT NOT NULL,                  -- FK to users.id
    token_hash TEXT NOT NULL,               -- SHA-256 of JWT
    device_info TEXT,                       -- Parsed User-Agent
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
```

**Pydantic Schemas:**

```python
# backend/app/schemas/user.py
class UserCreate(BaseModel):
    email: EmailStr
    role: Literal["admin", "operator", "viewer"]
    send_email: bool = False

class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None

class UserUpdate(BaseModel):
    email: EmailStr | None = None
    role: Literal["admin", "operator", "viewer"] | None = None
    is_active: bool | None = None

# backend/app/schemas/session.py
class SessionResponse(BaseModel):
    id: str
    device_info: str | None
    ip_address: str | None
    created_at: datetime
    last_active_at: datetime
    is_current: bool
```

### APIs and Interfaces

**User Management API (Admin only):**

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| POST | `/api/v1/users` | Create user | `{email, role, send_email?}` | `UserResponse + temporary_password?` |
| GET | `/api/v1/users` | List users | - | `UserResponse[]` |
| GET | `/api/v1/users/{id}` | Get user | - | `UserResponse` |
| PUT | `/api/v1/users/{id}` | Update user | `UserUpdate` | `UserResponse` |
| DELETE | `/api/v1/users/{id}` | Delete user | - | `204 No Content` |
| POST | `/api/v1/users/{id}/reset` | Reset password | - | `{temporary_password, expires_at}` |

**Session Management API:**

| Method | Endpoint | Description | Request | Response |
|--------|----------|-------------|---------|----------|
| GET | `/api/v1/auth/sessions` | List my sessions | - | `SessionResponse[]` |
| DELETE | `/api/v1/auth/sessions/{id}` | Revoke session | - | `204 No Content` |
| DELETE | `/api/v1/auth/sessions` | Revoke all except current | - | `{revoked_count}` |
| POST | `/api/v1/auth/change-password` | Change password | `{current_password?, new_password}` | `{success, message}` |

### Workflows and Sequencing

**User Invitation Flow:**

```
Admin creates user
       │
       ▼
┌─────────────────────────────┐
│  Generate random password   │
│  (16 chars, secrets module) │
└─────────────────────────────┘
       │
       ▼
┌─────────────────────────────┐
│  Create user record         │
│  must_change_password=true  │
│  password_expires_at=72h    │
└─────────────────────────────┘
       │
       ├──► send_email=false: Show credentials on screen
       │
       └──► send_email=true: Send invitation email (if email configured)
```

**First Login Flow:**

```
User enters credentials
       │
       ▼
Validate password ──► Invalid ──► 401 Unauthorized
       │
       ▼ Valid
Check must_change_password
       │
       ├──► false: Create session, return JWT, redirect to dashboard
       │
       └──► true: Create session with limited scope, redirect to /change-password
                  │
                  ▼
           Force password change
                  │
                  ▼
           Set must_change_password=false
                  │
                  ▼
           Redirect to dashboard
```

**Session Creation Flow:**

```
Valid login/password change
       │
       ▼
┌─────────────────────────────┐
│  Check session count        │
│  (max 5 per user)           │
└─────────────────────────────┘
       │
       ├──► < 5: Create new session
       │
       └──► >= 5: Delete oldest session, create new
                  │
                  ▼
┌─────────────────────────────┐
│  Generate JWT token         │
│  Store hash in sessions     │
│  Set HTTP-only cookie       │
└─────────────────────────────┘
```

## Non-Functional Requirements

### Performance

| Metric | Target | Notes |
|--------|--------|-------|
| Password hash time | ~250ms | bcrypt cost 12 |
| JWT validation | < 1ms | Stateless |
| Session lookup | < 5ms | Indexed by token_hash |
| Session list API | < 100ms | NFR8 |

### Security

| Requirement | Implementation | Reference |
|-------------|---------------|-----------|
| NFR1: bcrypt cost ≥ 12 | `bcrypt__rounds=12` in passlib | ADR-P15-002 |
| NFR2: Token expiry 24h | password_expires_at field | - |
| NFR3: 256-bit tokens | `secrets.token_urlsafe(32)` | - |
| NFR4: Rate limiting | Existing API rate limiter | P14-2.6 |
| NFR5: Audit logging | Log all auth events | Existing logger |
| NFR6: Session encryption | SQLite encrypted at rest | Existing |

**Password Complexity Rules:**
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 number
- At least 1 special character (!@#$%^&*()_+-=[]{}|;:,.<>?)

### Reliability/Availability

- Session cleanup runs hourly (APScheduler)
- Expired sessions auto-removed
- User deletion cascades to sessions
- Account disable immediately invalidates all sessions

### Observability

- Log: Login success/failure with user email (no passwords)
- Log: Session creation with device/IP
- Log: Session revocation with reason
- Log: User CRUD operations with admin email
- Metric: Active sessions per user

## Dependencies and Integrations

**Backend Dependencies (New):**

| Package | Version | Purpose |
|---------|---------|---------|
| passlib | ^1.7.4 | Password hashing with bcrypt |
| python-jose | ^3.3.0 | JWT token generation |
| bcrypt | ^4.0.0 | bcrypt backend for passlib |

**Frontend Dependencies:**
- No new dependencies (uses existing shadcn/ui components)

**Integration Points:**
- Existing AuthContext for frontend session state
- Existing API client for auth endpoints
- Existing toast system for feedback

## Acceptance Criteria (Authoritative)

1. **AC1:** Admin can create user with email and role, receives temporary password
2. **AC2:** New user must change password on first login
3. **AC3:** Password validation enforces all complexity rules with specific error messages
4. **AC4:** Passwords hashed with bcrypt cost factor 12
5. **AC5:** User can view list of active sessions with device/IP info
6. **AC6:** User can revoke individual sessions
7. **AC7:** User can revoke all sessions except current
8. **AC8:** Maximum 5 concurrent sessions per user enforced
9. **AC9:** Sessions expire after 24 hours of inactivity
10. **AC10:** Admin role has access to user management endpoints
11. **AC11:** Operator role can manage events/entities but not users
12. **AC12:** Viewer role has read-only access
13. **AC13:** Current session marked with is_current=true in session list
14. **AC14:** Temporary passwords expire after 72 hours if unused

## Traceability Mapping

| AC | FR | Spec Section | Component | Test Idea |
|----|-----|--------------|-----------|-----------|
| AC1 | FR1, FR2 | User Invitation | users.py | Create user, verify temp password |
| AC2 | FR3 | First Login | auth.py | Login with must_change_password=true |
| AC3 | FR6 | Password Validation | PasswordService | Test each rule individually |
| AC4 | NFR1 | Security | PasswordService | Verify hash format/timing |
| AC5 | FR10, FR11 | Sessions API | SessionList.tsx | List sessions, verify device info |
| AC6 | FR12 | Sessions API | auth.py | Revoke and verify invalidated |
| AC7 | FR13 | Sessions API | auth.py | Revoke all, verify count |
| AC8 | FR14 | Session Limits | SessionService | Create 6 sessions, verify oldest deleted |
| AC9 | FR15 | Session Expiry | SessionService | Mock time, verify cleanup |
| AC10 | FR18 | RBAC | permissions.py | Admin access to /users |
| AC11 | FR19 | RBAC | permissions.py | Operator denied /users access |
| AC12 | FR20 | RBAC | permissions.py | Viewer read-only enforcement |
| AC13 | FR16 | Sessions API | SessionList.tsx | Verify current session UI |
| AC14 | FR2 | User Invitation | UserService | Expired temp password rejected |

## Risks, Assumptions, Open Questions

**Risks:**
- **Risk:** Existing stub auth migration complexity
  - *Mitigation:* Keep stub for backward compat initially, require first admin creation

- **Risk:** Email service not configured for invitations
  - *Mitigation:* Default to show-on-screen, email optional

**Assumptions:**
- Assumption: Single admin user exists after initial setup (created via CLI or first-run)
- Assumption: bcrypt library works on all target platforms (Linux, macOS)
- Assumption: Existing AuthContext can be extended without breaking changes

**Open Questions:**
- Q: How to handle first admin creation on fresh install?
  - *Recommendation:* CLI command `python -m app.cli create-admin` or first-run wizard

- Q: Should we support "remember me" for longer sessions?
  - *Recommendation:* Defer to future phase, default 24h is reasonable

## Test Strategy Summary

**Unit Tests:**
- PasswordService: hash, verify, validate_complexity
- SessionService: create, revoke, enforce_limits, cleanup
- RBAC: require_role decorator for each role

**Integration Tests:**
- User CRUD endpoints with auth
- Session lifecycle (create → list → revoke)
- Password change flow
- Role permission enforcement

**E2E Tests (Playwright):**
- Full user invitation flow
- First login with password change
- Session management UI
- Admin user management

**Security Tests:**
- Password timing attack resistance
- Session fixation prevention
- Role bypass attempts
- Token manipulation detection

**Manual Testing:**
- Device info parsing accuracy
- Session list UI across browsers
- Password complexity feedback UX
