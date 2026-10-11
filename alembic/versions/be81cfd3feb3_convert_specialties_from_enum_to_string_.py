"""convert specialties from enum to string allowlist

Revision ID: be81cfd3feb3
Revises: cd64d7aa8754
Create Date: 2026-10-11 18:29:38.759112

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'be81cfd3feb3'
down_revision: Union[str, Sequence[str], None] = 'cd64d7aa8754'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# See CLAUDE.md's Specialties convention / app/specialties.py: the
# taxonomy is now an allowlist in code, not a Postgres enum, so it can
# grow without a migration like this one. Values unchanged for now —
# this migration only changes the storage shape, not the taxonomy.
servicecategory_enum = postgresql.ENUM(
    'hair', 'makeup', 'nails', 'barber', 'skincare', name='servicecategory'
)


def upgrade() -> None:
    """Upgrade schema."""
    # USING ...::text casts the enum's own text representation across —
    # safe here since the enum's values and the new allowlist's values
    # are identical today.
    op.execute(
        "ALTER TABLE provider_profiles ALTER COLUMN categories TYPE VARCHAR(50)[] USING categories::text[]"
    )
    op.execute("ALTER TABLE bookings ALTER COLUMN category TYPE VARCHAR(50) USING category::text")
    servicecategory_enum.drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Downgrade schema."""
    servicecategory_enum.create(op.get_bind(), checkfirst=True)
    op.execute(
        "ALTER TABLE bookings ALTER COLUMN category TYPE servicecategory USING category::servicecategory"
    )
    op.execute(
        "ALTER TABLE provider_profiles ALTER COLUMN categories TYPE servicecategory[] "
        "USING categories::servicecategory[]"
    )
