"""Add protect_controllers table and extend cameras for Phase 2 UniFi Protect integration (Story P2-1.1)

Revision ID: 012
Revises: 011
Create Date: 2025-11-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    """Create protect_controllers table and add Phase 2 columns to cameras"""

    # Create protect_controllers table
    op.create_table(
        'protect_controllers',
        sa.Column('id', sa.String(36), primary_key=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('host', sa.String(255), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False, server_default='443'),
        sa.Column('username', sa.String(100), nullable=False),
        sa.Column('password', sa.String(500), nullable=False),  # Fernet encrypted
        sa.Column('verify_ssl', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_connected', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('last_connected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Add Phase 2 columns to cameras table and foreign key using batch mode for SQLite
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_type', sa.String(20), nullable=False, server_default='rtsp'))
        batch_op.add_column(sa.Column('protect_controller_id', sa.String(36), nullable=True))
        batch_op.add_column(sa.Column('protect_camera_id', sa.String(100), nullable=True))
        batch_op.add_column(sa.Column('protect_camera_type', sa.String(20), nullable=True))
        batch_op.add_column(sa.Column('smart_detection_types', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('is_doorbell', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.create_foreign_key(
            'fk_cameras_protect_controller',
            'protect_controllers',
            ['protect_controller_id'],
            ['id'],
            ondelete='SET NULL'
        )

    # Create indexes for efficient lookups
    op.create_index('idx_cameras_protect_camera_id', 'cameras', ['protect_camera_id'])
    op.create_index('idx_cameras_source_type', 'cameras', ['source_type'])


def downgrade():
    """Remove protect_controllers table and Phase 2 columns from cameras"""

    # Drop indexes first
    op.drop_index('idx_cameras_source_type', 'cameras')
    op.drop_index('idx_cameras_protect_camera_id', 'cameras')

    # Drop foreign key and columns using batch mode for SQLite
    with op.batch_alter_table('cameras', schema=None) as batch_op:
        batch_op.drop_constraint('fk_cameras_protect_controller', type_='foreignkey')
        batch_op.drop_column('is_doorbell')
        batch_op.drop_column('smart_detection_types')
        batch_op.drop_column('protect_camera_type')
        batch_op.drop_column('protect_camera_id')
        batch_op.drop_column('protect_controller_id')
        batch_op.drop_column('source_type')

    # Drop protect_controllers table
    op.drop_table('protect_controllers')
