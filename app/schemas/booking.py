import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.booking import BookingStatus, VisitType
from app.specialties import Specialty


class BookingCreate(BaseModel):
    provider_profile_id: uuid.UUID
    category: Specialty
    visit_type: VisitType
    address: str | None = None
    scheduled_at: datetime
    # Integer minor units (e.g. pence, kobo) — see app/money.py and
    # CLAUDE.md's Money convention. No currency field here: a booking's
    # currency is always copied from the provider's own currency (see
    # app/routers/bookings.py), never client-supplied. ge=0: these are
    # client-supplied (no pricing catalog yet — see CLAUDE.md), but a
    # negative price/fee is never valid regardless of what pricing model
    # eventually sits behind this field.
    price: int | None = Field(default=None, ge=0)
    transport_fee: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_address_for_house_call(self):
        if self.visit_type == VisitType.house_call and not self.address:
            raise ValueError("address is required for a house_call booking")
        return self


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class BookingPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    provider_profile_id: uuid.UUID
    category: str
    visit_type: VisitType
    address: str | None
    scheduled_at: datetime
    currency: str
    price: int | None
    transport_fee: int | None
    status: BookingStatus
    created_at: datetime
