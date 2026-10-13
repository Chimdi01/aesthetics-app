import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.payout_account import PayoutAccountStatus
from app.payments.payment_provider import PaymentProvider


class PayoutAccountPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    payment_provider: PaymentProvider
    # Not sensitive the way an API key is — a processor's own account
    # id — but always None today, since no real onboarding flow exists
    # yet to set it (see app/models/payout_account.py).
    external_account_id: str | None
    status: PayoutAccountStatus
    created_at: datetime
