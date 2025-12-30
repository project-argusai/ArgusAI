# Story 14-5.6: Add Check Constraints on Float Columns

Status: done

## Story

As a **database administrator**,
I want float columns to have range constraints,
so that invalid data cannot be stored in the database.

## Acceptance Criteria

1. **AC1**: `event.ai_confidence` has CheckConstraint: 0 <= value <= 100 (or NULL allowed)
2. **AC2**: `event.anomaly_score` has CheckConstraint: 0 <= value <= 1 (or NULL allowed)
3. **AC3**: `event.audio_confidence` has CheckConstraint: 0 <= value <= 1 (or NULL allowed)
4. **AC4**: `camera.audio_threshold` has CheckConstraint: 0 <= value <= 1 (or NULL allowed)
5. **AC5**: Alembic migration adds all constraints
6. **AC6**: Migration is reversible (downgrade works)
7. **AC7**: Existing data is validated - migration fails if invalid data exists

## Tasks / Subtasks

- [x] Task 1: Add CheckConstraints to Event model (AC: #1, #2, #3)
  - [x] Add constraint for ai_confidence (0-100)
  - [x] Add constraint for anomaly_score (0-1)
  - [x] Add constraint for audio_confidence (0-1)
- [x] Task 2: Add CheckConstraint to Camera model (AC: #4)
  - [x] Add constraint for audio_threshold (0-1)
- [x] Task 3: Create Alembic migration (AC: #5, #6, #7)
  - [x] Create migration file 058_add_float_check_constraints.py
  - [x] Add data validation step before constraint creation
  - [x] Add upgrade() with batch_alter_table for SQLite compatibility
  - [x] Add downgrade() to remove constraints
- [x] Task 4: Test migration (AC: #5, #6)
  - [x] Verify model imports work
  - [x] Verify migration syntax is valid
  - [x] All 45 model tests pass

## Dev Notes

### Technical Implementation

**Float columns requiring constraints:**

| Model | Column | Valid Range | Nullable |
|-------|--------|-------------|----------|
| Event | ai_confidence | 0-100 | Yes |
| Event | anomaly_score | 0.0-1.0 | Yes |
| Event | audio_confidence | 0.0-1.0 | Yes |
| Camera | audio_threshold | 0.0-1.0 | Yes |

**Note**: The `event.confidence` column (Integer) already has a CheckConstraint at `event.py:135`.

### SQLite Considerations

SQLite requires batch mode for adding constraints to existing tables. The pattern is:
```python
with op.batch_alter_table('table_name', schema=None) as batch_op:
    batch_op.create_check_constraint(
        'constraint_name',
        sa.or_(
            sa.column('column_name').is_(None),
            sa.and_(
                sa.column('column_name') >= 0,
                sa.column('column_name') <= 100
            )
        )
    )
```

### Constraint Naming Convention

Follow existing pattern from model files:
- `check_ai_confidence_range` for Event.ai_confidence
- `check_anomaly_score_range` for Event.anomaly_score
- `check_audio_confidence_range` for Event.audio_confidence
- `check_audio_threshold_range` for Camera.audio_threshold

### Project Structure Notes

- Model files: `backend/app/models/event.py`, `backend/app/models/camera.py`
- Migration directory: `backend/alembic/versions/`
- Next migration number: 058

### References

- [Source: docs/epics-phase14.md#story-p14-5-6]
- [Source: docs/sprint-artifacts/tech-spec-epic-P14-5.md]
- [Pattern: backend/app/models/event.py:135 - existing confidence constraint]
- [Pattern: backend/alembic/versions/057_add_webhooklog_fk_constraints.py - batch_alter_table usage]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

None - implementation was straightforward.

### Completion Notes List

- Added 3 CheckConstraints to Event model in `__table_args__`
- Added 1 CheckConstraint to Camera model in `__table_args__`
- Created Alembic migration 058 with:
  - Data validation/cleanup step before adding constraints
  - SQLite-compatible batch_alter_table operations
  - Full downgrade support
- All constraints allow NULL values since these are optional columns

### File List

**MODIFIED:**
- `backend/app/models/event.py` - Added 3 CheckConstraints to __table_args__
- `backend/app/models/camera.py` - Added 1 CheckConstraint to __table_args__
- `docs/sprint-artifacts/sprint-status.yaml` - Updated story status

**NEW:**
- `backend/alembic/versions/058_add_float_check_constraints.py` - Migration file
- `docs/sprint-artifacts/p14-5-6-add-check-constraints-on-float-columns.md` - Story file

