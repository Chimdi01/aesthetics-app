"""
A provider's own payout account with whichever processor handles
their market (see app/payments/payment_provider.py) — the thing Stripe
Connect/Flutterwave actually pays out to. One row is staged
automatically when the provider profile is created (see
app/routers/providers.py), with payment_provider already correctly
set from the provider's country; external_account_id stays NULL and
status stays 'pending' until the real onboarding flow (not built yet —
needs real API keys, see CLAUDE.md) actually creates an account on the
processor's side. This table exists now so that flow has somewhere to
write to once it's wired up.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.payments.payment_provider import PaymentProvider


class PayoutAccountStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    restricted = "restricted"
    disabled = "disabled"


class ProviderPayoutAccount(Base):
    __tablename__ = "provider_payout_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Unique: one payout account per provider — a provider operates in
    # one market, same 1:1 reasoning as ProviderProfile.user_id.
    provider_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profiles.id"), unique=True, nullable=False
    )
    payment_provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider, name="paymentprovider"), nullable=False
    )
    # NULL until the real onboarding flow creates an account — see the
    # module docstring.
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PayoutAccountStatus] = mapped_column(
        Enum(PayoutAccountStatus, name="payoutaccountstatus"), default=PayoutAccountStatus.pending, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
