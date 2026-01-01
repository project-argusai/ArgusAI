# Story P16-1.6: User Audit Logging

Status: done

## Story

As an **administrator**,
I want **user management actions logged**,
So that **I can review who made changes and when**.

## Acceptance Criteria

1. ✅ Given an admin creates a new user, When the action completes, Then an audit log entry is created with: action='create_user', user_id (who did it), target_user_id (who was affected), details (JSON with username, role), ip_address, timestamp
2. ✅ Given an admin changes a user's role, When the action completes, Then an audit log entry records: action='change_role', details with old_role and new_role
3. ✅ Audit logs are created for: create_user, update_user, delete_user, change_role, reset_password, disable_user, enable_user, change_password
4. ✅ Audit logs cannot be modified or deleted via API (no PUT/DELETE endpoints)

## Tasks / Subtasks

- [x] Task 1: Create UserAuditLog model (AC: 1, 2, 3)
  - [x] Created `backend/app/models/user_audit_log.py` with UserAuditLog model
  - [x] Added AuditAction enum with all action types
  - [x] Added to models/__init__.py exports
- [x] Task 2: Create database migration (AC: 1)
  - [x] Created `alembic/versions/i1a2b3c4d5e8_add_user_audit_logs_table.py`
  - [x] Added indexes for common queries
- [x] Task 3: Create UserAuditService (AC: 1, 2, 3)
  - [x] Created `backend/app/services/user_audit_service.py`
  - [x] Implemented log methods for all action types
  - [x] Added get_audit_logs() and get_user_audit_history() for querying
- [x] Task 4: Integrate audit logging into UserService (AC: 1, 2, 3)
  - [x] Updated create_user() to log create_user action
  - [x] Updated update_user() to log update_user, change_role, enable_user, disable_user
  - [x] Updated delete_user() to log delete_user action
  - [x] Updated reset_password() to log reset_password action
  - [x] Updated change_password() to log change_password action
- [x] Task 5: Update API endpoints to pass request info (AC: 1)
  - [x] Updated users.py endpoints to extract IP and User-Agent
  - [x] Updated auth.py change_password endpoint

## Dev Notes

### Implementation Summary

Story P16-1.6 adds comprehensive audit logging for all user management actions. The audit trail captures who performed each action, who was affected, what changed, and from where.

### Key Components

1. **UserAuditLog Model** (`backend/app/models/user_audit_log.py`)
   - Stores action, actor, target, details (JSON), IP address, user agent, timestamp
   - Append-only design (no update/delete via API)
   - Indexed for efficient querying

2. **UserAuditService** (`backend/app/services/user_audit_service.py`)
   - Provides typed methods for each action type
   - log_create_user(), log_update_user(), log_delete_user()
   - log_change_role(), log_reset_password(), log_change_password()
   - log_enable_user(), log_disable_user()
   - Query methods for admin viewing

3. **Integration Points**
   - UserService now creates audit logs for all user management operations
   - API endpoints pass Request object for IP/User-Agent extraction

### Audit Actions Logged

| Action | Trigger | Details Captured |
|--------|---------|------------------|
| create_user | Admin creates user | username, role, email |
| update_user | Admin updates user | changed fields |
| delete_user | Admin deletes user | username |
| change_role | Admin changes role | old_role, new_role |
| reset_password | Admin resets password | - |
| change_password | User changes own password | - |
| enable_user | Admin enables account | - |
| disable_user | Admin disables account | - |

### Security Design

- Audit logs are append-only
- No PUT or DELETE endpoints exposed
- IP addresses captured for security tracing
- User-Agent stored for device identification

### Database Schema

```sql
CREATE TABLE user_audit_logs (
    id VARCHAR(36) PRIMARY KEY,
    action VARCHAR(50) NOT NULL,
    user_id VARCHAR(36) REFERENCES users(id),      -- Who performed action
    target_user_id VARCHAR(36) REFERENCES users(id), -- Who was affected
    details JSON,
    ip_address VARCHAR(45),
    user_agent VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX idx_audit_action_created ON user_audit_logs(action, created_at);
CREATE INDEX idx_audit_target_created ON user_audit_logs(target_user_id, created_at);
```

### References

- [Source: backend/app/models/user_audit_log.py] - Audit log model
- [Source: backend/app/services/user_audit_service.py] - Audit service
- [Source: backend/app/services/user_service.py] - Integration points
- [Source: backend/app/api/v1/users.py] - API endpoints

## Dev Agent Record

### Context Reference

Built on P16-1.2 (User Management API) and P15-2.3 (User Service)

### Agent Model Used

Claude Opus 4.5

### Debug Log References

No issues encountered

### Completion Notes List

- Audit logging is comprehensive across all user management actions
- IP address extraction handles X-Forwarded-For for proxy scenarios
- User-Agent captured for device identification
- Future enhancement: Add read-only API endpoint for admin viewing (optional)

### File List

| File | Status | Description |
|------|--------|-------------|
| `backend/app/models/user_audit_log.py` | NEW | UserAuditLog model and AuditAction enum |
| `backend/app/models/__init__.py` | MODIFIED | Added UserAuditLog export |
| `backend/alembic/versions/i1a2b3c4d5e8_add_user_audit_logs_table.py` | NEW | Migration for audit logs table |
| `backend/app/services/user_audit_service.py` | NEW | Audit logging service |
| `backend/app/services/user_service.py` | MODIFIED | Integrated audit logging |
| `backend/app/api/v1/users.py` | MODIFIED | Added request info extraction |
| `backend/app/api/v1/auth.py` | MODIFIED | Added audit logging to change_password |
