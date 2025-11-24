"""Add FTS5 full-text search for events.description

Revision ID: 008
Revises: 007
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    """Create FTS5 virtual table and triggers for event description search"""

    # Create FTS5 virtual table for full-text search on descriptions
    op.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS events_fts
        USING fts5(
            id UNINDEXED,
            description,
            content='events',
            content_rowid='rowid'
        )
    """)

    # Populate FTS5 table with existing data
    op.execute("""
        INSERT INTO events_fts(rowid, id, description)
        SELECT rowid, id, description FROM events
    """)

    # Trigger to keep FTS5 index synchronized on INSERT
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
            INSERT INTO events_fts(rowid, id, description)
            VALUES (new.rowid, new.id, new.description);
        END
    """)

    # Trigger to keep FTS5 index synchronized on UPDATE
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
            UPDATE events_fts
            SET description = new.description
            WHERE rowid = old.rowid;
        END
    """)

    # Trigger to keep FTS5 index synchronized on DELETE
    op.execute("""
        CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
            DELETE FROM events_fts WHERE rowid = old.rowid;
        END
    """)


def downgrade():
    """Drop FTS5 virtual table and triggers"""
    op.execute("DROP TRIGGER IF EXISTS events_ad")
    op.execute("DROP TRIGGER IF EXISTS events_au")
    op.execute("DROP TRIGGER IF EXISTS events_ai")
    op.execute("DROP TABLE IF EXISTS events_fts")
