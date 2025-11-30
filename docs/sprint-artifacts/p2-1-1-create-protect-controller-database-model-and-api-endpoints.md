# Story P2-1.1: Create Protect Controller Database Model and API Endpoints

Status: done

## Story

As a **backend developer**,
I want **database models and API endpoints for Protect controller management**,
so that **the system can store and manage UniFi Protect controller connection settings securely**.

## Acceptance Criteria

| # | Criteria | Verification |
|---|----------|--------------|
| AC1 | Database migration creates `protect_controllers` table with all required columns (id, name, host, port, username, password, verify_ssl, is_connected, last_connected_at, last_error, created_at, updated_at) | Run migration, verify schema |
| AC2 | Password field is encrypted using existing Fernet encryption before storage | Unit test encryption/decryption |
| AC3 | `cameras` table extended with Phase 2 columns (source_type, protect_controller_id, protect_camera_id, protect_camera_type, smart_detection_types, is_doorbell) | Run migration, verify schema |
| AC4 | POST `/api/v1/protect/controllers` creates new controller record | API test |
| AC5 | GET `/api/v1/protect/controllers` returns list of all controllers | API test |
| AC6 | GET `/api/v1/protect/controllers/{id}` returns single controller | API test |
| AC7 | PUT `/api/v1/protect/controllers/{id}` updates controller | API test |
| AC8 | DELETE `/api/v1/protect/controllers/{id}` removes controller | API test |
| AC9 | All endpoints return consistent `{ data, meta }` response format | API test |
| AC10 | Indexes created on `cameras.protect_camera_id` and `cameras.source_type` | Verify migration |

## Tasks / Subtasks

- [x] **Task 1: Create ProtectController SQLAlchemy Model** (AC: 1, 2)
  - [x] 1.1 Create `backend/app/models/protect_controller.py` with all columns
  - [x] 1.2 Add relationship to Camera model
  - [x] 1.3 Implement password encryption/decryption using `backend/app/utils/encryption.py`
  - [x] 1.4 Export model in `backend/app/models/__init__.py`

- [x] **Task 2: Extend Camera Model** (AC: 3, 10)
  - [x] 2.1 Add `source_type` column (TEXT DEFAULT 'rtsp', values: 'rtsp', 'usb', 'protect')
  - [x] 2.2 Add `protect_controller_id` foreign key column
  - [x] 2.3 Add `protect_camera_id` column (TEXT, nullable)
  - [x] 2.4 Add `protect_camera_type` column (TEXT, nullable)
  - [x] 2.5 Add `smart_detection_types` column (TEXT for JSON array)
  - [x] 2.6 Add `is_doorbell` column (BOOLEAN DEFAULT FALSE)

- [x] **Task 3: Create Alembic Migration** (AC: 1, 3, 10)
  - [x] 3.1 Generate migration script for `protect_controllers` table
  - [x] 3.2 Add camera table alterations in same migration
  - [x] 3.3 Create indexes: `idx_cameras_protect_camera_id`, `idx_cameras_source_type`
  - [x] 3.4 Test migration upgrade and downgrade

- [x] **Task 4: Create Pydantic Schemas** (AC: 9)
  - [x] 4.1 Create `backend/app/schemas/protect.py`
  - [x] 4.2 Define `ProtectControllerCreate` schema (name, host, port, username, password, verify_ssl)
  - [x] 4.3 Define `ProtectControllerUpdate` schema (all fields optional)
  - [x] 4.4 Define `ProtectControllerResponse` schema (excludes raw password)
  - [x] 4.5 Define `ProtectControllerList` schema with meta

- [x] **Task 5: Create API Router** (AC: 4-9)
  - [x] 5.1 Create `backend/app/api/v1/protect.py` router
  - [x] 5.2 Implement `POST /protect/controllers` endpoint
  - [x] 5.3 Implement `GET /protect/controllers` endpoint
  - [x] 5.4 Implement `GET /protect/controllers/{id}` endpoint
  - [x] 5.5 Implement `PUT /protect/controllers/{id}` endpoint
  - [x] 5.6 Implement `DELETE /protect/controllers/{id}` endpoint
  - [x] 5.7 Register router in `backend/app/api/v1/__init__.py` or `main.py`

- [x] **Task 6: Write Tests** (AC: 1-10)
  - [x] 6.1 Create `backend/tests/test_api/test_protect.py`
  - [x] 6.2 Test ProtectController model creation with encryption
  - [x] 6.3 Test all CRUD endpoints
  - [x] 6.4 Test response format consistency
  - [x] 6.5 Test validation errors (missing fields, invalid data)

- [x] **Task 7: Verify Integration** (AC: all)
  - [x] 7.1 Run all migrations successfully
  - [x] 7.2 Run all tests pass
  - [x] 7.3 Manual API testing via Swagger UI
  - [x] 7.4 Verify existing camera functionality unaffected

## Dev Notes

### Architecture Patterns

**Backend Service Pattern** (from architecture.md):
- Services in `backend/app/services/` handle business logic
- API routers in `backend/app/api/v1/` handle HTTP concerns
- Models in `backend/app/models/` define database schema
- Schemas in `backend/app/schemas/` define request/response validation

**Naming Conventions** (from architecture.md lines 719-740):
- Backend: `snake_case` for files, functions, variables
- Models: `PascalCase` for classes
- Tables: `snake_case` plural (e.g., `protect_controllers`)
- API routes: `kebab-case` (e.g., `/protect/controllers`)

**API Response Format** (from architecture.md lines 529-534):
```python
{
    "data": {...},  # Single object or list
    "meta": {
        "request_id": "uuid",
        "timestamp": "ISO8601"
    }
}
```

### Encryption

Use existing Fernet encryption from `backend/app/utils/encryption.py`:
```python
from app.utils.encryption import encrypt_value, decrypt_value

# Store encrypted
controller.password = encrypt_value(plain_password)

# Read decrypted (never expose in API response)
plain_password = decrypt_value(controller.password)
```

### Database Schema

**protect_controllers table** (from architecture.md lines 1503-1518):
```sql
CREATE TABLE protect_controllers (
    id TEXT PRIMARY KEY,                    -- UUID
    name TEXT NOT NULL,                     -- User-friendly name
    host TEXT NOT NULL,                     -- IP address or hostname
    port INTEGER DEFAULT 443,               -- HTTPS port
    username TEXT NOT NULL,                 -- Protect username
    password TEXT NOT NULL,                 -- Encrypted with Fernet
    verify_ssl BOOLEAN DEFAULT FALSE,       -- SSL verification toggle
    is_connected BOOLEAN DEFAULT FALSE,     -- Current connection status
    last_connected_at TIMESTAMP,            -- Last successful connection
    last_error TEXT,                        -- Last error message
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**cameras table extensions** (from architecture.md lines 1521-1534):
```sql
ALTER TABLE cameras ADD COLUMN source_type TEXT DEFAULT 'rtsp';
ALTER TABLE cameras ADD COLUMN protect_controller_id TEXT REFERENCES protect_controllers(id);
ALTER TABLE cameras ADD COLUMN protect_camera_id TEXT;
ALTER TABLE cameras ADD COLUMN protect_camera_type TEXT;
ALTER TABLE cameras ADD COLUMN smart_detection_types TEXT;
ALTER TABLE cameras ADD COLUMN is_doorbell BOOLEAN DEFAULT FALSE;

CREATE INDEX idx_cameras_protect_camera_id ON cameras(protect_camera_id);
CREATE INDEX idx_cameras_source_type ON cameras(source_type);
```

### Project Structure Notes

**Files to create:**
- `backend/app/models/protect_controller.py` - SQLAlchemy model
- `backend/app/schemas/protect.py` - Pydantic schemas
- `backend/app/api/v1/protect.py` - API router
- `backend/alembic/versions/XXX_add_protect_controllers.py` - Migration
- `backend/tests/test_api/test_protect.py` - Tests

**Files to modify:**
- `backend/app/models/__init__.py` - Export new model
- `backend/app/models/camera.py` - Add new columns
- `backend/main.py` or `backend/app/api/v1/__init__.py` - Register router

### References

- [Source: docs/architecture.md#Phase-2-Database-Schema-Additions] - Schema details
- [Source: docs/architecture.md#Phase-2-API-Contracts] - API endpoint specifications
- [Source: docs/epics-phase2.md#Story-1.1] - Acceptance criteria
- [Source: docs/PRD-phase2.md] - FR1-FR3 requirements

### First Story Notes

This is the first Phase 2 story. No previous story context exists.

**Foundation for subsequent stories:**
- Story 1.2 (connection validation) will add `POST /protect/controllers/test` endpoint
- Story 1.3 (UI) will consume these API endpoints
- Story 1.4 (WebSocket) will use the controller model for connection management
- All subsequent Epic 2-6 stories depend on this foundation

## Dev Agent Record

### Context Reference

- [p2-1-1-create-protect-controller-database-model-and-api-endpoints.context.xml](./p2-1-1-create-protect-controller-database-model-and-api-endpoints.context.xml)

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

Implementation followed context file artifacts and architectural patterns. All acceptance criteria verified through 26 passing tests.

### Completion Notes List

- Created ProtectController SQLAlchemy model with Fernet password encryption
- Extended Camera model with 6 new Phase 2 columns for UniFi Protect integration
- Created Alembic migration 012 with protect_controllers table, camera extensions, and indexes
- Implemented Pydantic schemas with proper { data, meta } response format
- Built complete CRUD API at /api/v1/protect/controllers with proper error handling
- Registered router in main.py
- Wrote 26 comprehensive tests covering all acceptance criteria
- All tests pass, existing Camera model tests (13) unaffected

### File List

**Created:**
- backend/app/models/protect_controller.py
- backend/app/schemas/protect.py
- backend/app/api/v1/protect.py
- backend/alembic/versions/012_add_protect_controllers_and_camera_extensions.py
- backend/tests/test_api/test_protect.py

**Modified:**
- backend/app/models/__init__.py (added ProtectController export)
- backend/app/models/camera.py (added Phase 2 columns and relationship)
- backend/main.py (registered protect_router)

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-11-30 | Story drafted from epics-phase2.md | SM Agent |
| 2025-11-30 | Implementation complete - all 7 tasks done, 26 tests passing | Dev Agent |
| 2025-11-30 | Senior Developer Review - APPROVED | AI Reviewer |

## Senior Developer Review (AI)

### Reviewer
Brent (AI-assisted)

### Date
2025-11-30

### Outcome
**APPROVE** ✅

All acceptance criteria fully implemented with evidence. All tasks verified complete. Code quality is high with proper error handling, security, and test coverage.

### Summary
Story P2-1.1 establishes the foundation for UniFi Protect integration with a complete database model, CRUD API, and comprehensive test suite. The implementation follows all architectural patterns and constraints. The code is well-structured, secure, and production-ready.

### Key Findings

**No HIGH or MEDIUM severity issues found.**

**LOW Severity:**
- Note: `MetaResponse.timestamp` uses deprecated `datetime.utcnow`. Consider updating to `datetime.now(timezone.utc)` for Python 3.12+ compatibility. (Non-blocking)

### Acceptance Criteria Coverage

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| AC1 | protect_controllers table with all columns | ✅ IMPLEMENTED | `alembic/versions/012_...py:23-37` |
| AC2 | Password Fernet encryption | ✅ IMPLEMENTED | `models/protect_controller.py:50-79` |
| AC3 | cameras table Phase 2 columns | ✅ IMPLEMENTED | `models/camera.py:60-66` |
| AC4 | POST /protect/controllers | ✅ IMPLEMENTED | `api/v1/protect.py:44-101` |
| AC5 | GET /protect/controllers (list) | ✅ IMPLEMENTED | `api/v1/protect.py:104-125` |
| AC6 | GET /protect/controllers/{id} | ✅ IMPLEMENTED | `api/v1/protect.py:128-164` |
| AC7 | PUT /protect/controllers/{id} | ✅ IMPLEMENTED | `api/v1/protect.py:167-232` |
| AC8 | DELETE /protect/controllers/{id} | ✅ IMPLEMENTED | `api/v1/protect.py:235-281` |
| AC9 | { data, meta } response format | ✅ IMPLEMENTED | `schemas/protect.py:93-111` |
| AC10 | Indexes on cameras | ✅ IMPLEMENTED | `alembic/versions/012_...py:58-59` |

**Summary: 10 of 10 acceptance criteria fully implemented**

### Task Completion Validation

| Task | Marked | Verified | Evidence |
|------|--------|----------|----------|
| 1.1 Create protect_controller.py | ✅ | ✅ | File exists |
| 1.2 Add Camera relationship | ✅ | ✅ | `protect_controller.py:48` |
| 1.3 Password encryption | ✅ | ✅ | `protect_controller.py:50-79` |
| 1.4 Export in __init__.py | ✅ | ✅ | `models/__init__.py:2` |
| 2.1-2.6 Camera columns | ✅ | ✅ | `camera.py:60-66` |
| 3.1-3.4 Migration | ✅ | ✅ | Migration file exists |
| 4.1-4.5 Pydantic schemas | ✅ | ✅ | `schemas/protect.py` |
| 5.1-5.7 API endpoints | ✅ | ✅ | `api/v1/protect.py` |
| 6.1-6.5 Tests | ✅ | ✅ | 26 tests passing |
| 7.1-7.4 Integration | ✅ | ✅ | All verified |

**Summary: 25 of 25 tasks verified, 0 questionable, 0 false completions**

### Test Coverage and Gaps

- **26 tests** covering all acceptance criteria
- **Test classes**: TestProtectControllerModel, TestProtectControllerAPI, TestResponseFormat, TestValidation, TestDatabaseSchema, TestBackwardsCompatibility
- **Edge cases**: Duplicate names (409), not found (404), validation errors (422)
- **No gaps identified**

### Architectural Alignment

- ✅ Follows backend service pattern (models/, schemas/, api/v1/)
- ✅ Consistent naming conventions (snake_case, PascalCase)
- ✅ Response format matches `{ data, meta }` standard
- ✅ Router registered with API prefix
- ✅ Encryption uses existing `encrypt_password/decrypt_password` utilities

### Security Notes

- ✅ Password encrypted with Fernet AES-256 before storage
- ✅ Password excluded from API response (write-only field)
- ✅ Double encryption prevention implemented
- ✅ Error handling prevents information leakage

### Best-Practices and References

- FastAPI 0.115 best practices followed
- SQLAlchemy 2.0 ORM patterns used
- Pydantic v2 schemas with `from_attributes=True`
- pytest with TestClient for integration testing

### Action Items

**Advisory Notes:**
- Note: Consider updating `MetaResponse.timestamp` to use `datetime.now(timezone.utc)` instead of deprecated `datetime.utcnow` for future Python compatibility (non-blocking)
