"""Add system_settings table for configuration storage

Revision ID: 005
Revises: 004
Create Date: 2025-11-17

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    """Create system_settings table"""
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(100), primary_key=True, nullable=False),
        sa.Column('value', sa.String(2000), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)
    )

    # Insert default settings
    op.execute("""
        INSERT INTO system_settings (key, value) VALUES
        ('ai_model_primary', 'openai'),
        ('data_retention_days', '30'),
        ('motion_sensitivity', 'medium'),
        ('thumbnail_storage_mode', 'filesystem')
    """)


def downgrade():
    """Drop system_settings table"""
    op.drop_table('system_settings')
