"""
Idempotency ledger for payment-provider webhooks — see CLAUDE.md's
Payments convention: "idempotent webhook handling keyed by the
provider's own event id". Once a real webhook handler exists, it
checks for an existing row with the same (payment_provider,
external_event_id) before doing anything, and inserts one as part of
the SAME transaction as whatever it does in response — so a
provider's at-least-once delivery retrying one event never
double-applies its effect (e.g. crediting a payout twice). Not wired
into a real handler yet — see app/routers/payment_webhooks.py, which
deliberately 501s rather than process anything unverified.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.payments.payment_provider import PaymentProvider


class ProcessedWebhookEvent(Base):
    __tablename__ = "processed_webhook_events"
    __table_args__ = (
        Index(
            "ux_processed_webhook_events_provider_event_id",
            "payment_provider",
            "external_event_id",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, name="paymentprovider", create_type=False), nullable=False
    )
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
