"""
The core transaction: a customer requests time with a provider for a
specific category of service, at the provider's shop or via a house-call.
`category` must be one of the provider's declared
ProviderProfile.categories — enforced in the router (Postgres can't
cheaply constrain "this value is a member of that other row's array
column" as a real FK-like constraint), not here.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.provider_profile import ServiceCategory


class VisitType(str, enum.Enum):
    shop_visit = "shop_visit"
    house_call = "house_call"


class BookingStatus(str, enum.Enum):
    requested = "requested"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        # Every "my bookings" listing filters on one of these and sorts by
        # scheduled_at — composite indexes keep that an index scan
        # regardless of total platform-wide booking volume.
        Index("ix_bookings_customer_id_scheduled_at", "customer_id", "scheduled_at"),
        Index("ix_bookings_provider_profile_id_scheduled_at", "provider_profile_id", "scheduled_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    provider_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profiles.id"), nullable=False
    )
    category: Mapped[ServiceCategory] = mapped_column(Enum(ServiceCategory, name="servicecategory"), nullable=False)
    visit_type: Mapped[VisitType] = mapped_column(Enum(VisitType, name="visittype"), nullable=False)
    # Required for house_call, left empty for shop_visit — enforced in the
    # Pydantic schema, not as a DB constraint.
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Numeric, not Float — money should never be a binary float.
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    transport_fee: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="bookingstatus"), default=BookingStatus.requested, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
