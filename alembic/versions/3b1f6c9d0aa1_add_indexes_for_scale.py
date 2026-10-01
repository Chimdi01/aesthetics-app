"""add indexes for scale

Revision ID: 3b1f6c9d0aa1
Revises: 2245f79fd675
Create Date: 2026-09-29 20:10:00.000000

Adds indexes on the FK/filter columns every existing "list X for this
booking/provider" query already uses, plus their sort column where one
query always sorts (e.g. bookings by scheduled_at). These are the exact
queries that degrade from an index scan to a full table scan as row
counts grow — cheap to add now, much more disruptive to add later
against a table with real production traffic on it.

CREATE INDEX CONCURRENTLY (not a plain CREATE INDEX) so this doesn't take
a write-blocking lock on tables that may already hold real rows by the
time this migration runs against a production database — unlike
2245f79fd675's index on the brand-new (empty) messages table, which
didn't need it. CONCURRENTLY can't run inside a transaction, hence the
autocommit_block() wrapping every statement here.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3b1f6c9d0aa1'
down_revision: Union[str, Sequence[str], None] = '2245f79fd675'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_bookings_customer_id_scheduled_at", "bookings", ["customer_id", "scheduled_at"]),
    ("ix_bookings_provider_profile_id_scheduled_at", "bookings", ["provider_profile_id", "scheduled_at"]),
    ("ix_portfolio_media_provider_profile_id_created_at", "portfolio_media", ["provider_profile_id", "created_at"]),
    ("ix_provider_availability_provider_profile_id", "provider_availability", ["provider_profile_id"]),
    ("ix_reviews_provider_profile_id_created_at", "reviews", ["provider_profile_id", "created_at"]),
]


def upgrade() -> None:
    for name, table, columns in _INDEXES:
        with op.get_context().autocommit_block():
            op.create_index(name, table, columns, unique=False, postgresql_concurrently=True)


def downgrade() -> None:
    for name, table, _columns in _INDEXES:
        with op.get_context().autocommit_block():
            op.drop_index(name, table_name=table, postgresql_concurrently=True)
