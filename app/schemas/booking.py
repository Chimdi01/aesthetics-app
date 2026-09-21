import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.booking import BookingStatus, VisitType
from app.models.provider_profile import ServiceCategory


class BookingCreate(BaseModel):
    provider_profile_id: uuid.UUID
    category: ServiceCategory
    visit_type: VisitType
    address: str | None = None
    scheduled_at: datetime
    price: Decimal | None = None
    transport_fee: Decimal | None = None

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
    category: ServiceCategory
    visit_type: VisitType
    address: str | None
    scheduled_at: datetime
    price: Decimal | None
    transport_fee: Decimal | None
    status: BookingStatus
    created_at: datetime
