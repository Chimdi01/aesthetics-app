"""trigger: refuse making a user admin if they hold a provider profile

Revision ID: c20b1323c9c1
Revises: d2d0aa2b34de
Create Date: 2026-10-13 21:57:41.729369

"""
from typing import Sequence, Union

from alembic import op

from app.db_triggers import (
    ADMIN_PROVIDER_EXCLUSIVITY_DROP_TRIGGER_SQL,
    ADMIN_PROVIDER_EXCLUSIVITY_FUNCTION_SQL,
    ADMIN_PROVIDER_EXCLUSIVITY_TRIGGER_SQL,
)

# revision identifiers, used by Alembic.
revision: str = 'c20b1323c9c1'
down_revision: Union[str, Sequence[str], None] = 'd2d0aa2b34de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The actual SQL lives in app/db_triggers.py, shared with
# tests/conftest.py's schema setup — see that module's docstring for
# why (triggers aren't part of SQLAlchemy's ORM metadata, so
# Base.metadata.create_all(), what builds the test DB, would
# otherwise never create this one).


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(ADMIN_PROVIDER_EXCLUSIVITY_FUNCTION_SQL)
    op.execute(ADMIN_PROVIDER_EXCLUSIVITY_DROP_TRIGGER_SQL)
    op.execute(ADMIN_PROVIDER_EXCLUSIVITY_TRIGGER_SQL)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_admin_with_provider_profile ON users")
    op.execute("DROP FUNCTION IF EXISTS prevent_admin_with_provider_profile()")
