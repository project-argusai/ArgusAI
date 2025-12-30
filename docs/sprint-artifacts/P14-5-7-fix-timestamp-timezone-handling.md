# Story 14-5.7: Fix Timestamp Timezone Handling

Status: done

## Story

As a **developer**,
I want consistent UTC timestamp handling across all models,
so that time-based queries work correctly across timezones.

## Acceptance Criteria

1. **AC1**: All DateTime columns have `timezone=True` for timezone-aware storage
2. **AC2**: `system_setting.py` uses Python UTC default instead of `server_default=func.now()`
3. **AC3**: `activity_summary.py` DateTime columns (period_start, period_end, generated_at) have `timezone=True`
4. **AC4**: `homekit.py` DateTime columns (created_at, updated_at) have `timezone=True`
5. **AC5**: `user.py` DateTime columns (created_at, last_login) have `timezone=True`
6. **AC6**: Alembic migration updates column definitions for SQLite compatibility
7. **AC7**: Migration is reversible
8. **AC8**: Existing data timestamps are preserved (no data corruption)

## Tasks / Subtasks

- [x] Task 1: Audit all DateTime columns in models (AC: #1)
  - [x] Identify columns missing `timezone=True`
  - [x] Document current state
- [x] Task 2: Update ActivitySummary model (AC: #3)
  - [x] Add `timezone=True` to period_start, period_end, generated_at
- [x] Task 3: Update SystemSetting model (AC: #2)
  - [x] Change `server_default=func.now()` to `default=lambda: datetime.now(timezone.utc)`
  - [x] Keep `onupdate` behavior
- [x] Task 4: Update HomeKit models (AC: #4)
  - [x] Add `timezone=True` to HomeKitConfig.created_at, updated_at
  - [x] Add `timezone=True` to HomeKitAccessory.created_at
- [x] Task 5: Update User model (AC: #5)
  - [x] Add `timezone=True` to created_at, last_login
- [x] Task 6: Create Alembic migration (AC: #6, #7, #8)
  - [x] Create migration file 059_fix_timestamp_timezone_handling.py
  - [x] Handle SQLite compatibility (no-op migration)
  - [x] Ensure data preservation (no schema changes)
- [x] Task 7: Test migration (AC: #6, #7, #8)
  - [x] Verify model imports work
  - [x] Verify migration syntax is valid
  - [x] All 76 model tests pass

## Dev Notes

### Technical Implementation

**Columns requiring timezone=True:**

| Model | Column | Current State | Fix Required |
|-------|--------|--------------|--------------|
| ActivitySummary | period_start | `DateTime` | Add `timezone=True` |
| ActivitySummary | period_end | `DateTime` | Add `timezone=True` |
| ActivitySummary | generated_at | `DateTime` | Add `timezone=True` |
| SystemSetting | updated_at | `server_default=func.now()` | Use Python default |
| HomeKitConfig | created_at | `DateTime` | Add `timezone=True` |
| HomeKitConfig | updated_at | `DateTime` | Add `timezone=True` |
| HomeKitAccessory | created_at | `DateTime` | Add `timezone=True` |
| User | created_at | `DateTime` | Add `timezone=True` |
| User | last_login | `DateTime` | Add `timezone=True` |

**Note**: Many other models already have `DateTime(timezone=True)` - see Event, MotionEvent, AlertRule, etc.

### SQLite Considerations

SQLite stores DATETIME as TEXT in ISO 8601 format. The `timezone=True` parameter primarily affects:
1. Python-side serialization/deserialization
2. PostgreSQL TIMESTAMP WITH TIME ZONE type selection

For SQLite, the migration won't change the underlying storage but ensures Python handles timezones correctly.

### server_default vs default

- `server_default=func.now()`: Uses database server time (may differ from app timezone)
- `default=lambda: datetime.now(timezone.utc)`: Consistent UTC from Python

The latter is preferred for consistency and testability.

### Migration Strategy

Since SQLite doesn't have a native timezone-aware datetime type, the migration will:
1. Not alter column types (unnecessary for SQLite)
2. Update model definitions for correct Python handling
3. Be a no-op migration for SQLite (documentation only)

### Project Structure Notes

- Model files: `backend/app/models/`
- Migration directory: `backend/alembic/versions/`
- Next migration number: 059

### References

- [Source: docs/epics-phase14.md#story-p14-5-7]
- [Source: docs/sprint-artifacts/tech-spec-epic-P14-5.md]
- [Pattern: backend/app/models/event.py - existing DateTime(timezone=True) usage]

### Learnings from Previous Story

**From Story P14-5.6 (Status: done)**

- SQLite batch_alter_table pattern works well for constraint changes
- Model tests verify imports and relationships correctly
- No actual column type migration needed for SQLite - just model definition updates

[Source: docs/sprint-artifacts/P14-5-6-add-check-constraints-on-float-columns.md#Dev-Agent-Record]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

None - implementation was straightforward.

### Completion Notes List

- Added `timezone=True` to 9 DateTime columns across 4 models
- Changed SystemSetting from `server_default=func.now()` to Python UTC default
- Created Alembic migration 059 as documentation-only (SQLite no-op)
- All 76 model tests pass

### File List

**MODIFIED:**
- `backend/app/models/activity_summary.py` - Added timezone=True to period_start, period_end, generated_at
- `backend/app/models/system_setting.py` - Changed to Python UTC default with timezone=True
- `backend/app/models/homekit.py` - Added timezone=True to HomeKitConfig and HomeKitAccessory timestamps
- `backend/app/models/user.py` - Added timezone=True to created_at, last_login
- `docs/sprint-artifacts/sprint-status.yaml` - Updated story status

**NEW:**
- `backend/alembic/versions/059_fix_timestamp_timezone_handling.py` - Documentation migration
- `docs/sprint-artifacts/P14-5-7-fix-timestamp-timezone-handling.md` - Story file
