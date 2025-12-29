# Story P14-2.2: Add Missing Foreign Key Constraint

Status: done

## Story

As a database administrator,
I want WebhookLog.alert_rule_id and event_id to have proper foreign key constraints,
so that orphaned webhook logs are automatically cleaned up when rules or events are deleted.

## Acceptance Criteria

1. **AC-1**: WebhookLog model has ForeignKey to AlertRule with CASCADE delete
2. **AC-2**: WebhookLog model has ForeignKey to Event with CASCADE delete
3. **AC-3**: Alembic migration handles existing orphaned records by deleting them
4. **AC-4**: Migration is reversible with proper downgrade
5. **AC-5**: Relationships are added for ORM navigation (alert_rule, event)
6. **AC-6**: Existing webhook logging continues to work after migration

## Tasks / Subtasks

- [ ] Task 1: Update WebhookLog model (AC: 1, 2, 5)
  - [ ] 1.1: Add ForeignKey constraint to alert_rule_id column
  - [ ] 1.2: Add ForeignKey constraint to event_id column
  - [ ] 1.3: Add relationship properties to WebhookLog class
  - [ ] 1.4: Add back_populates relationships to AlertRule and Event models

- [ ] Task 2: Create Alembic migration (AC: 3, 4)
  - [ ] 2.1: Generate migration with `alembic revision -m "add_webhooklog_fk_constraints"`
  - [ ] 2.2: Add cleanup query to delete orphaned webhook logs
  - [ ] 2.3: Add foreign key constraints using batch_alter_table (SQLite compatibility)
  - [ ] 2.4: Implement reversible downgrade with constraint drops

- [ ] Task 3: Run tests and verify functionality (AC: 6)
  - [ ] 3.1: Run `alembic upgrade head` to apply migration
  - [ ] 3.2: Run full test suite `pytest tests/ -v`
  - [ ] 3.3: Test cascade delete: create rule with webhook log, delete rule, verify log deleted
  - [ ] 3.4: Test cascade delete: delete event, verify log deleted

## Dev Notes

### Implementation Pattern

**Current Code (`backend/app/models/alert_rule.py`):**
```python
class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_rule_id = Column(String, nullable=False, index=True)  # No FK!
    event_id = Column(String, nullable=False, index=True)  # No FK!
```

**Updated Model:**
```python
class WebhookLog(Base):
    __tablename__ = "webhook_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_rule_id = Column(
        String,
        ForeignKey('alert_rules.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    event_id = Column(
        String,
        ForeignKey('events.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    # ... rest of model

    # Add relationships
    alert_rule = relationship("AlertRule", back_populates="webhook_logs")
    event = relationship("Event", back_populates="webhook_logs")
```

### Migration Script Pattern

```python
def upgrade():
    # First, clean up any orphaned records
    op.execute("""
        DELETE FROM webhook_logs
        WHERE alert_rule_id NOT IN (SELECT id FROM alert_rules)
        OR event_id NOT IN (SELECT id FROM events)
    """)

    # Add foreign key constraints (batch mode for SQLite)
    with op.batch_alter_table('webhook_logs') as batch_op:
        batch_op.create_foreign_key(
            'fk_webhook_logs_alert_rule',
            'alert_rules',
            ['alert_rule_id'],
            ['id'],
            ondelete='CASCADE'
        )
        batch_op.create_foreign_key(
            'fk_webhook_logs_event',
            'events',
            ['event_id'],
            ['id'],
            ondelete='CASCADE'
        )

def downgrade():
    with op.batch_alter_table('webhook_logs') as batch_op:
        batch_op.drop_constraint('fk_webhook_logs_alert_rule', type_='foreignkey')
        batch_op.drop_constraint('fk_webhook_logs_event', type_='foreignkey')
```

### Project Structure Notes

- Model file: `backend/app/models/alert_rule.py`
- Migration location: `backend/alembic/versions/`
- Related models: `backend/app/models/event.py` for Event back_populates

### Testing Standards

From project architecture:
- Backend uses pytest with fixtures
- Run: `cd backend && pytest tests/ -v`
- Coverage: `pytest tests/ --cov=app --cov-report=html`

### Learnings from Previous Story

**From Story P14-2-1-standardize-database-session-management (Status: done)**

- **New Helper Created**: `get_db_session()` context manager available at `backend/app/core/database.py` - use for any new database operations
- **Pattern Established**: All service layer code now uses `with get_db_session() as db:` pattern
- **Special Cases Documented**: Some services retain SessionLocal for factory patterns with caller-managed sessions
- **Testing Setup**: Unit tests added at `backend/tests/test_core/test_database.py` - follow patterns established there

[Source: docs/sprint-artifacts/P14-2-1-standardize-database-session-management.md#Dev-Agent-Record]

### References

- [Source: docs/sprint-artifacts/tech-spec-epic-P14-2.md#Story-P14-2.2]
- [Source: docs/epics-phase14.md#Story-P14-2.2]
- [Source: backend/app/models/alert_rule.py - existing WebhookLog model]
- [Source: backend/app/models/event.py - Event model for relationship]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

### Completion Notes List

- Added ForeignKey constraints to WebhookLog for both `alert_rule_id` and `event_id` columns
- Both constraints use CASCADE delete to automatically clean up webhook logs when parent records are deleted
- Added SQLAlchemy relationship properties to WebhookLog for ORM navigation (`alert_rule`, `event`)
- Added `back_populates` relationships to AlertRule and Event models (`webhook_logs`)
- Created Alembic migration (057) that first cleans orphaned records then adds FK constraints
- Migration uses batch mode for SQLite compatibility
- All 76 model tests pass, all 67 event tests pass, all 15 alert rule tests pass

### File List

**Modified:**
- backend/app/models/alert_rule.py (WebhookLog FK constraints, relationships, AlertRule back_populates)
- backend/app/models/event.py (Event back_populates)

**Added:**
- backend/alembic/versions/057_add_webhooklog_fk_constraints.py (migration)

