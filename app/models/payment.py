"""
One row per payment ATTEMPT against a Booking — not 1:1 with Booking,
since a failed attempt followed by a successful retry is two rows, not
one row overwritten. Nothing creates one of these yet: that needs a
real checkout flow calling a real processor SDK (blocked on company
registration / API keys, see CLAUDE.md), not built here. This table
exists now so that flow — and the webhook handler that will update
external_payment_id/status once a payment actually settles, see
app/models/webhook_event.py — has somewhere to write to.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.payments.payment_provider import PaymentProvider


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        # Every "payments for this booking" lookup filters on booking_id
        # and would sort newest-first — same composite-index pattern as
        # Message/Review/etc. (see CLAUDE.md).
        Index("ix_payments_booking_id_created_at", "booking_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False)
    # Denormalized from the provider's own payout account at creation —
    # same "copy it, don't join for it later" tradeoff already made for
    # Booking.category/Booking.currency (see CLAUDE.md).
    payment_provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, name="paymentprovider", create_type=False), nullable=False
    )
    # Integer minor units + currency, never a float — see app/money.py.
    # Copied from the booking at creation, not re-derived later.
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Our commission (rate TBD, see CLAUDE.md) on this specific
    # attempt — stored, not just computed on the fly, since the real
    # rate could change between one attempt and a later retry.
    application_fee_amount: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # NULL until a real processor call creates a charge.
    external_payment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="paymentstatus"), default=PaymentStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
