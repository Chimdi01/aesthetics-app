"""money retrofit: currency plus integer minor units for bookings

Revision ID: 67c31bcb3b16
Revises: be81cfd3feb3
Create Date: 2026-10-11 18:51:23.595415

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '67c31bcb3b16'
down_revision: Union[str, Sequence[str], None] = 'be81cfd3feb3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# See CLAUDE.md's Money convention / app/money.py: amounts are integer
# minor units plus an ISO 4217 currency code, never a bare Decimal.
# XOF has no minor-unit subdivision used in practice (factor 1); the
# other launch currencies are 2-decimal (factor 100).
_MINOR_UNIT_FACTOR_CASE = "CASE WHEN currency = 'XOF' THEN 1 ELSE 100 END"


def upgrade() -> None:
    """Upgrade schema."""
    # provider_profiles.currency: add nullable, backfill, then tighten —
    # same pattern as any NOT NULL column added against a table that may
    # already have rows (see CLAUDE.md). 'GBP' is a placeholder backfill
    # for pre-existing dev rows only; there's no real production data yet.
    op.add_column('provider_profiles', sa.Column('currency', sa.String(length=3), nullable=True))
    op.execute("UPDATE provider_profiles SET currency = 'GBP' WHERE currency IS NULL")
    op.alter_column('provider_profiles', 'currency', nullable=False)

    # bookings.currency: same add-nullable/backfill/tighten pattern, but
    # backfilled from each booking's own provider (not a flat placeholder)
    # since that's the real, correct value per CLAUDE.md's "a booking's
    # currency is copied from the provider's currency at creation".
    op.add_column('bookings', sa.Column('currency', sa.String(length=3), nullable=True))
    op.execute(
        "UPDATE bookings SET currency = provider_profiles.currency "
        "FROM provider_profiles WHERE bookings.provider_profile_id = provider_profiles.id"
    )
    op.alter_column('bookings', 'currency', nullable=False)

    # price/transport_fee: NUMERIC(10,2) major units -> BIGINT minor
    # units. USING can reference the now-populated currency column on
    # the same row to pick the right factor; safe to do after currency
    # is backfilled above, not before.
    op.execute(
        f"ALTER TABLE bookings ALTER COLUMN price TYPE BIGINT USING "
        f"ROUND(price * {_MINOR_UNIT_FACTOR_CASE})::bigint"
    )
    op.execute(
        f"ALTER TABLE bookings ALTER COLUMN transport_fee TYPE BIGINT USING "
        f"ROUND(transport_fee * {_MINOR_UNIT_FACTOR_CASE})::bigint"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Reverse order: convert price/transport_fee back to major units
    # while currency is still present (the USING clause needs it), THEN
    # drop the currency columns.
    op.execute(
        f"ALTER TABLE bookings ALTER COLUMN price TYPE NUMERIC(10, 2) USING "
        f"price::numeric / {_MINOR_UNIT_FACTOR_CASE}"
    )
    op.execute(
        f"ALTER TABLE bookings ALTER COLUMN transport_fee TYPE NUMERIC(10, 2) USING "
        f"transport_fee::numeric / {_MINOR_UNIT_FACTOR_CASE}"
    )
    op.drop_column('bookings', 'currency')
    op.drop_column('provider_profiles', 'currency')
