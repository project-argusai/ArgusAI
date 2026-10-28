"""Restore events_fts sync triggers dropped by 058 (#757)

Migration 058 adds CHECK constraints to ``events`` with ``batch_alter_table``.
On SQLite that rebuilds the table (create temp copy, drop old, rename), and
dropping the old table silently drops the ``events_ai`` / ``events_au`` /
``events_ad`` triggers that 008 created. The ``events_fts`` virtual table
survives, so search keeps working against old rows but never sees new events.

This migration (re)creates the triggers, in the corrected external-content
form (see below), and rebuilds the
FTS index from ``events`` (the copy in 058 can also renumber rowids, which the
external-content index is keyed on). SQLite only; a no-op elsewhere because
``events_fts`` is an FTS5 table that only exists on SQLite.

Revision ID: r6e757a1b2c3
Revises: q4c735a1b2c3
Create Date: 2026-10-28
"""
from alembic import op


revision = "r6e757a1b2c3"
down_revision = "q4c735a1b2c3"
branch_labels = None
depends_on = None


# FTS5 external-content triggers in the form the SQLite docs give. 008's
# UPDATE/DELETE triggers wrote to events_fts directly, which with
# content='events' leaves the old tokens in the index (an edited event still
# matches its old description, a deleted one still matches at all). The
# 'delete' command removes the old tokens properly.
_TRIGGERS = (
    """
    CREATE TRIGGER events_ai AFTER INSERT ON events BEGIN
        INSERT INTO events_fts(rowid, id, description)
        VALUES (new.rowid, new.id, new.description);
    END
    """,
    """
    CREATE TRIGGER events_au AFTER UPDATE ON events BEGIN
        INSERT INTO events_fts(events_fts, rowid, id, description)
        VALUES ('delete', old.rowid, old.id, old.description);
        INSERT INTO events_fts(rowid, id, description)
        VALUES (new.rowid, new.id, new.description);
    END
    """,
    """
    CREATE TRIGGER events_ad AFTER DELETE ON events BEGIN
        INSERT INTO events_fts(events_fts, rowid, id, description)
        VALUES ('delete', old.rowid, old.id, old.description);
    END
    """,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        return

    has_fts = bind.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'events_fts'"
    ).first()
    if not has_fts:
        # Same definition as 008, in case it was never created.
        op.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS events_fts
            USING fts5(
                id UNINDEXED,
                description,
                content='events',
                content_rowid='rowid'
            )
            """
        )

    # Drop-and-create so DBs that still have 008's triggers (anything created
    # before 058 ran without a table rebuild) get the corrected versions too.
    for name in ("events_ai", "events_au", "events_ad"):
        op.execute(f"DROP TRIGGER IF EXISTS {name}")
    for ddl in _TRIGGERS:
        op.execute(ddl)

    # Rebuild the external-content index from events so rows added while the
    # triggers were missing (and any rowids renumbered by 058) are searchable.
    op.execute("INSERT INTO events_fts(events_fts) VALUES ('rebuild')")


def downgrade() -> None:
    # Intentionally a no-op: dropping the triggers would put databases back
    # into the broken state this migration repairs, and 008's downgrade still
    # drops them (and events_fts) if the chain goes back that far.
    pass
