# Story P14-2.1: Standardize Database Session Management

Status: done

## Story

As a backend developer,
I want all database session creation to use a consistent context manager pattern,
so that session lifecycle is properly managed and connection leaks are prevented.

## Acceptance Criteria

1. **AC-1**: A `get_db_session()` context manager is added to `backend/app/core/database.py`
2. **AC-2**: All 43+ `db = SessionLocal()` instances in service files are converted to use the new context manager
3. **AC-3**: The context manager properly rolls back transactions on exceptions
4. **AC-4**: The context manager always closes the session in the finally block
5. **AC-5**: All existing tests pass without modification (pattern is compatible)
6. **AC-6**: No database connection leaks under any code path

## Tasks / Subtasks

- [ ] Task 1: Create context manager in database.py (AC: 1, 3, 4)
  - [ ] 1.1: Add `@contextmanager` decorated `get_db_session()` function
  - [ ] 1.2: Implement try/except/finally with rollback and close
  - [ ] 1.3: Add docstring with usage examples
  - [ ] 1.4: Add unit tests for the context manager

- [ ] Task 2: Refactor event_processor.py (10 instances) (AC: 2)
  - [ ] 2.1: Import `get_db_session` from core.database
  - [ ] 2.2: Replace all 10 `db = SessionLocal()` patterns with `with get_db_session() as db:`
  - [ ] 2.3: Remove redundant try/finally blocks that only handle session cleanup
  - [ ] 2.4: Verify each refactored function works correctly

- [ ] Task 3: Refactor protect_event_handler.py (4 instances) (AC: 2)
  - [ ] 3.1: Import and replace all 4 instances
  - [ ] 3.2: Verify event handling still works

- [ ] Task 4: Refactor protect_service.py (2 instances) (AC: 2)
  - [ ] 4.1: Import and replace both instances
  - [ ] 4.2: Verify Protect integration still works

- [ ] Task 5: Refactor remaining service files (AC: 2)
  - [ ] 5.1: push_notification_service.py (2 instances)
  - [ ] 5.2: digest_scheduler.py (2 instances)
  - [ ] 5.3: ai_service.py (1 instance)
  - [ ] 5.4: audio_extractor.py (2 instances)
  - [ ] 5.5: reprocessing_service.py (2 instances)
  - [ ] 5.6: delivery_service.py (1 instance)
  - [ ] 5.7: summary_service.py (1 instance)

- [ ] Task 6: Refactor route and middleware files (AC: 2)
  - [ ] 6.1: system.py routes (3 instances)
  - [ ] 6.2: events.py routes (1 instance)
  - [ ] 6.3: auth_middleware.py (2 instances)
  - [ ] 6.4: last_seen.py middleware (1 instance)
  - [ ] 6.5: main.py (2 instances)

- [ ] Task 7: Run full test suite (AC: 5, 6)
  - [ ] 7.1: Run `pytest tests/ -v` to verify all tests pass
  - [ ] 7.2: Run with coverage to ensure no regressions
  - [ ] 7.3: Test manually by triggering events and checking logs

## Dev Notes

### Implementation Pattern

**Add to `backend/app/core/database.py`:**
```python
from contextlib import contextmanager
from typing import Generator

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions in non-request contexts.

    Usage:
        with get_db_session() as db:
            db.query(Model).all()
            db.commit()  # If needed

    Automatically handles:
    - Session creation
    - Rollback on exception
    - Session cleanup
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

**Before/After Example:**
```python
# Before (anti-pattern):
def process_event():
    db = SessionLocal()
    try:
        event = db.query(Event).first()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# After (standardized):
def process_event():
    with get_db_session() as db:
        event = db.query(Event).first()
        db.commit()
```

### Files to Modify

| File | Instances | Lines (Approximate) |
|------|-----------|---------------------|
| `event_processor.py` | 10 | 218, 238, 566, 1398, 1856, 1896, 1958, 2091, 2211, 2362 |
| `protect_event_handler.py` | 4 | 261, 1013, 1747, 3048 |
| `protect_service.py` | 2 | 712, 840 |
| `push_notification_service.py` | 2 | 691, 910 |
| `digest_scheduler.py` | 2 | 207, 463 |
| `ai_service.py` | 1 | 2613 |
| `audio_extractor.py` | 2 | 354, 487 |
| `reprocessing_service.py` | 2 | 303, 324 |
| `system.py` | 3 | 134, 171, 1657 |
| `events.py` | 1 | 160 |
| `auth_middleware.py` | 2 | 152, 237 |
| `last_seen.py` | 1 | 103 |
| `main.py` | 2 | 118, 177 |
| `delivery_service.py` | 1 | 100 |
| `summary_service.py` | 1 | 485 |

### What NOT to Change

- `database.py:get_db()` - This is the FastAPI dependency for request-scoped sessions
- Test files - They use their own session handling patterns
- Any code that already uses `get_db()` dependency injection

### Project Structure Notes

- Context manager goes in `backend/app/core/database.py` alongside existing `get_db()`
- Import pattern: `from app.core.database import get_db_session`
- No new files needed, just extend existing database module

### Testing Standards

From project architecture:
- Backend uses pytest with fixtures
- Run: `cd backend && pytest tests/ -v`
- Coverage: `pytest tests/ --cov=app --cov-report=html`

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P14-2.md#Story-P14-2.1]
- [Source: docs/architecture/08-implementation-patterns.md]
- [Source: backend/app/core/database.py - existing session patterns]

## Dev Agent Record

### Context Reference

- `docs/sprint-artifacts/P14-2-1-standardize-database-session-management.context.xml`

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- Added `get_db_session()` context manager to `backend/app/core/database.py`
- Refactored all 36+ service file instances to use new context manager pattern
- Two special cases retained with `SessionLocal` and documented comments:
  - `push_notification_service.py` - Factory pattern where caller manages session
  - `delivery_service.py` - Lazy initialization with explicit `_close_db()` method
- Unit tests added for the new context manager

### File List

**Modified:**
- backend/app/core/database.py (added get_db_session context manager)
- backend/main.py (2 instances)
- backend/app/services/event_processor.py (10 instances)
- backend/app/services/protect_event_handler.py (4 instances)
- backend/app/services/protect_service.py (2 instances)
- backend/app/services/push_notification_service.py (2 instances - 1 retained as special case)
- backend/app/services/digest_scheduler.py (2 instances)
- backend/app/services/ai_service.py (1 instance)
- backend/app/services/audio_extractor.py (2 instances)
- backend/app/services/reprocessing_service.py (2 instances)
- backend/app/services/delivery_service.py (1 instance - retained as special case)
- backend/app/services/summary_service.py (1 instance)
- backend/app/api/v1/system.py (3 instances)
- backend/app/api/v1/events.py (1 instance)
- backend/app/middleware/auth_middleware.py (2 instances)
- backend/app/middleware/last_seen.py (1 instance)

**Added:**
- backend/tests/test_core/test_database.py (unit tests for get_db_session)

