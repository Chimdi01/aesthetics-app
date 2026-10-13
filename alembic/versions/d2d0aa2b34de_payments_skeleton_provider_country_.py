"""payments skeleton: provider country, payout accounts, payments, webhook idempotency

Revision ID: d2d0aa2b34de
Revises: f01203e0020f
Create Date: 2026-10-13 19:55:50.622497

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd2d0aa2b34de'
down_revision: Union[str, Sequence[str], None] = 'f01203e0020f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # provider_profiles.country: same add-nullable/backfill/tighten
    # pattern as currency/timezone before it (no universal sensible
    # default) — 'GB' is a placeholder backfill for pre-existing dev
    # rows only, not a default for new ones (see CLAUDE.md).
    op.add_column('provider_profiles', sa.Column('country', sa.String(length=2), nullable=True))
    op.execute("UPDATE provider_profiles SET country = 'GB' WHERE country IS NULL")
    op.alter_column('provider_profiles', 'country', nullable=False)

    # First table to use the paymentprovider enum — create_type defaults
    # to True, so this is what actually creates the Postgres type.
    op.create_table(
        'provider_payout_accounts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('provider_profile_id', sa.UUID(), nullable=False),
        sa.Column(
            'payment_provider',
            postgresql.ENUM('stripe', 'flutterwave', name='paymentprovider'),
            nullable=False,
        ),
        sa.Column('external_account_id', sa.String(length=255), nullable=True),
        sa.Column(
            'status',
            sa.Enum('pending', 'active', 'restricted', 'disabled', name='payoutaccountstatus'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['provider_profile_id'], ['provider_profiles.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_profile_id'),
    )

    # create_type=False: paymentprovider already exists, created by
    # provider_payout_accounts above — see CLAUDE.md's "Reusing an
    # existing Postgres ENUM type in a NEW op.create_table" gotcha.
    op.create_table(
        'payments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('booking_id', sa.UUID(), nullable=False),
        sa.Column(
            'payment_provider',
            postgresql.ENUM('stripe', 'flutterwave', name='paymentprovider', create_type=False),
            nullable=False,
        ),
        sa.Column('amount', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('application_fee_amount', sa.BigInteger(), nullable=True),
        sa.Column('external_payment_id', sa.String(length=255), nullable=True),
        sa.Column(
            'status',
            sa.Enum('pending', 'succeeded', 'failed', 'refunded', name='paymentstatus'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # New table created in this same migration — no CONCURRENTLY needed
    # (nothing can be writing to a table that doesn't exist yet).
    op.create_index('ix_payments_booking_id_created_at', 'payments', ['booking_id', 'created_at'])

    op.create_table(
        'processed_webhook_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column(
            'payment_provider',
            postgresql.ENUM('stripe', 'flutterwave', name='paymentprovider', create_type=False),
            nullable=False,
        ),
        sa.Column('external_event_id', sa.String(length=255), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ux_processed_webhook_events_provider_event_id',
        'processed_webhook_events',
        ['payment_provider', 'external_event_id'],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ux_processed_webhook_events_provider_event_id', table_name='processed_webhook_events')
    op.drop_table('processed_webhook_events')
    op.drop_index('ix_payments_booking_id_created_at', table_name='payments')
    op.drop_table('payments')
    op.drop_table('provider_payout_accounts')

    # All three enum types were created by this migration — drop all
    # of them, same mirror-the-upgrade reasoning as every other enum
    # gotcha in this codebase.
    postgresql.ENUM(name='paymentstatus').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='payoutaccountstatus').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='paymentprovider').drop(op.get_bind(), checkfirst=True)

    op.drop_column('provider_profiles', 'country')
