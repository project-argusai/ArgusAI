"""fix_timestamp_timezone_handling

Revision ID: 059
Revises: 058
Create Date: 2025-12-30 14:00:00.000000

Story P14-5.7: Fix Timestamp Timezone Handling

This migration documents the model changes for consistent UTC timestamp handling.

Changes made to models (in Python code):
- ActivitySummary: period_start, period_end, generated_at -> DateTime(timezone=True)
- SystemSetting: updated_at -> default=lambda instead of server_default=func.now()
- HomeKitConfig: created_at, updated_at -> DateTime(timezone=True)
- HomeKitAccessory: created_at -> DateTime(timezone=True)
- User: created_at, last_login -> DateTime(timezone=True)

SQLite Note:
SQLite stores datetime as TEXT in ISO 8601 format. The timezone=True parameter
affects Python-side handling and PostgreSQL type selection, but SQLite does not
require schema changes. This migration is essentially a no-op for SQLite but
ensures model and schema definitions are synchronized.

PostgreSQL Note:
For PostgreSQL, this would require ALTER COLUMN ... TYPE TIMESTAMP WITH TIME ZONE.
Since ArgusAI primarily uses SQLite, we skip actual column alterations.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '059'
down_revision = '058'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Document timezone-aware DateTime column changes.

    This is a no-op migration for SQLite as it stores datetime as TEXT.
    The actual changes are in the model definitions:
    - Added timezone=True to DateTime columns
    - Changed server_default=func.now() to Python default for consistency
    """
    # For SQLite: No schema changes needed
    # The model changes ensure Python handles timezones consistently
    #
    # Affected columns (model changes only):
    # - activity_summaries.period_start: DateTime -> DateTime(timezone=True)
    # - activity_summaries.period_end: DateTime -> DateTime(timezone=True)
    # - activity_summaries.generated_at: DateTime -> DateTime(timezone=True)
    # - system_settings.updated_at: server_default=func.now() -> default=lambda: datetime.now(timezone.utc)
    # - homekit_config.created_at: DateTime -> DateTime(timezone=True)
    # - homekit_config.updated_at: DateTime -> DateTime(timezone=True)
    # - homekit_accessories.created_at: DateTime -> DateTime(timezone=True)
    # - users.created_at: DateTime -> DateTime(timezone=True)
    # - users.last_login: DateTime -> DateTime(timezone=True)
    pass


def downgrade() -> None:
    """
    Downgrade is a no-op since no schema changes were made.

    Model changes would need to be manually reverted:
    - Remove timezone=True from DateTime columns
    - Change default=lambda back to server_default=func.now() for system_settings
    """
    pass
