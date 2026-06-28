"""Add missing event columns (model/DB drift repair)

Revision ID: e7c9a1b3d5f2
Revises: 47e72e4a4433
Create Date: 2026-06-28

Repairs accumulated model/schema drift: 17 columns existed on the Event ORM
model but were never added to the `events` table via a migration (alembic was
"at head" yet the columns were absent). Production restarts that loaded the
newer model code therefore failed every `SELECT` against `events`
(`OperationalError: no such column: events.ai_response_time_ms`), so the events
list endpoint 500'd and the UI showed no events ("all data gone") even though
all rows were intact.

All additions are additive/nullable or carry a server_default, so existing rows
backfill cleanly and no data is touched.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7c9a1b3d5f2'
down_revision = '47e72e4a4433'
branch_labels = None
depends_on = None


# (name, column) — order is cosmetic; SQLite appends regardless.
_NULLABLE_COLUMNS = [
    ('ai_response_time_ms', sa.Integer()),
    ('tokens_used', sa.Integer()),
    ('context_stats', sa.Text()),
    ('post_processing_summary', sa.Text()),
    ('entity_similarity_score', sa.Float()),
    ('entity_occurrence_count', sa.Integer()),
    ('entity_is_new', sa.Boolean()),
    ('final_entity_id', sa.String()),
    ('final_entity_name', sa.String()),
    ('final_entity_type', sa.String(length=20)),
    ('final_entity_is_new', sa.Boolean()),
    ('final_entity_occurrence_count', sa.Integer()),
    ('final_entity_similarity_score', sa.Float()),
]

# NOT NULL booleans (model default False). server_default backfills existing rows;
# SQLite requires a DEFAULT to add a NOT NULL column to a populated table.
_NOTNULL_BOOL_COLUMNS = [
    'ocr_used',
    'ai_fallback_used',
    'context_included',
    'regenerated',
]

_ALL_COLUMN_NAMES = [name for name, _ in _NULLABLE_COLUMNS] + _NOTNULL_BOOL_COLUMNS


def upgrade() -> None:
    for name, coltype in _NULLABLE_COLUMNS:
        op.add_column('events', sa.Column(name, coltype, nullable=True))
    for name in _NOTNULL_BOOL_COLUMNS:
        op.add_column(
            'events',
            sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    for name in reversed(_ALL_COLUMN_NAMES):
        op.drop_column('events', name)
