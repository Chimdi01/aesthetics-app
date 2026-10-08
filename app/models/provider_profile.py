"""
Provider-only data. Split out from User (rather than adding nullable
columns to the users table) because a customer row would otherwise carry
a pile of always-NULL provider fields — this way the table only exists
for rows that need it, one-to-one with a User where role == provider.
"""
import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import Boolean, String, Text, Integer, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.database import Base


class ServiceCategory(str, enum.Enum):
    hair = "hair"
    makeup = "makeup"
    nails = "nails"
    barber = "barber"
    skincare = "skincare"


class AddressType(str, enum.Enum):
    shop = "shop"
    home = "home"


class ProviderProfile(Base):
    __tablename__ = "provider_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A single provider can offer more than one type of service (e.g. a
    # stylist who also does makeup) — stored as a Postgres array rather
    # than a join table since this is a "tag the provider" model, not a
    # full per-service catalog with its own pricing/duration.
    categories: Mapped[list[ServiceCategory]] = mapped_column(
        ARRAY(Enum(ServiceCategory, name="servicecategory")), nullable=False
    )
    # Where customers visit the provider. Both nullable: providers created
    # before search existed have no location and simply don't appear in
    # search results until they add one. Geography (not Geometry) so
    # distances/radii are in real meters on the earth's surface.
    location: Mapped[str | None] = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=True)
    address_type: Mapped[AddressType | None] = mapped_column(Enum(AddressType, name="addresstype"), nullable=True)
    # Admin-only moderation flag (see app/routers/admin.py) — never
    # client-settable at profile creation or anywhere else. False excludes
    # the profile from search results and blocks new bookings against it
    # (see app/routers/bookings.py); direct GET by id still works, since
    # existing bookings/reviews reference this row via FK and hiding it
    # entirely would break displaying that history.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="provider_profile")
