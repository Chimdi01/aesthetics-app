"""time retrofit: provider IANA timezone column

Revision ID: 61120202ba75
Revises: 67c31bcb3b16
Create Date: 2026-10-13 18:33:53.065259

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '61120202ba75'
down_revision: Union[str, Sequence[str], None] = '67c31bcb3b16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Same add-nullable/backfill/tighten-to-NOT-NULL pattern as
    # currency (see the previous migration) — 'Europe/London' is a
    # placeholder backfill for pre-existing dev rows only (the first
    # launch market); there's no real production data yet.
    op.add_column('provider_profiles', sa.Column('timezone', sa.String(length=50), nullable=True))
    op.execute("UPDATE provider_profiles SET timezone = 'Europe/London' WHERE timezone IS NULL")
    op.alter_column('provider_profiles', 'timezone', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('provider_profiles', 'timezone')
