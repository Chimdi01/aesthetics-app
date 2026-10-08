"""add user and provider active flags and reports table

Revision ID: 7cacfa7b316e
Revises: 5d9d7466e207
Create Date: 2026-10-08 18:50:04.776302

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7cacfa7b316e'
down_revision: Union[str, Sequence[str], None] = '5d9d7466e207'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('reports',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('reporter_id', sa.UUID(), nullable=False),
    # Targets a User (either role), not a ProviderProfile — see
    # app/models/report.py for why reporting has to be two-way.
    sa.Column('reported_user_id', sa.UUID(), nullable=False),
    sa.Column('reason', sa.Enum('safety_concern', 'inappropriate_behavior', 'fraud_or_scam', 'spam', 'other', name='reportreason'), nullable=False),
    sa.Column('details', sa.String(length=2000), nullable=True),
    sa.Column('status', sa.Enum('pending', 'resolved', 'dismissed', name='reportstatus'), nullable=False),
    sa.Column('resolved_by', sa.UUID(), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['reported_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['reporter_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_reports_status_created_at', 'reports', ['status', 'created_at'], unique=False)
    # Both booleans use a constant server_default — a fast, metadata-only
    # ADD COLUMN in modern Postgres even against a populated table, no
    # CONCURRENTLY/backfill dance needed (that's specifically an
    # index-creation concern — see CLAUDE.md).
    op.add_column('provider_profiles', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_active')
    op.drop_column('provider_profiles', 'is_active')
    op.drop_index('ix_reports_status_created_at', table_name='reports')
    op.drop_table('reports')
    # create_table doesn't drop its enum types on downgrade — without
    # this, re-running upgrade() after a downgrade fails with "type
    # reportreason already exists" (same gotcha as bookingstatus/mediatype/etc).
    postgresql.ENUM(name='reportreason').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='reportstatus').drop(op.get_bind(), checkfirst=True)
