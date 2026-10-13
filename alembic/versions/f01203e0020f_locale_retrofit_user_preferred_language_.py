"""locale retrofit: user preferred_language column

Revision ID: f01203e0020f
Revises: 61120202ba75
Create Date: 2026-10-13 19:27:53.537217

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f01203e0020f'
down_revision: Union[str, Sequence[str], None] = '61120202ba75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Unlike currency/timezone (no universal sensible default, so those
    # went through add-nullable/backfill/tighten), 'en' IS a universal
    # sensible default here — CLAUDE.md's Locale convention says "en
    # now, fr later". A NOT NULL column with a constant server_default
    # applies to existing rows in the same ALTER TABLE on Postgres 11+
    # (no table rewrite), so one step is enough.
    op.add_column(
        'users', sa.Column('preferred_language', sa.String(length=2), nullable=False, server_default='en')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'preferred_language')
