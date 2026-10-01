"""
A provider's typical weekly open hours — not a real calendar. One or more
time ranges per day of the week (split shifts allowed, e.g. 09:00-12:00
and 14:00-18:00 on the same day; no Google/iCal sync yet); a day the
provider doesn't work simply has no rows. Matches the roadmap's V1 scope:
"simple availability (usual working hours), not a full staff calendar" —
calendar sync to reduce double-booking is a separate, later workstream.

Multiple rows per day means no DB constraint alone can stop two ranges on
the same day from overlapping (that's a cross-row check, not expressible
as a single-row CheckConstraint) — overlap is rejected at the API layer
instead, in ProviderAvailabilityUpdate (see app/schemas/provider_availability.py).

Booking creation does NOT check this table. Providers already manually
accept/decline every booking request (see Booking's status state
machine), so a customer requesting an odd-hours slot isn't blocked here —
it's just something the provider would decline. Enforcing it at booking
time is a reasonable follow-up once real usage shows it's needed, not
built preemptively.

Times are plain wall-clock (no timezone) — fine for a single-city (London)
launch where provider and customer share a timezone; would need
revisiting before expanding to multiple timezones.
"""
import enum
import uuid
from datetime import datetime, time

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Time, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class DayOfWeek(str, enum.Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"
    saturday = "saturday"
    sunday = "sunday"


class ProviderAvailability(Base):
    __tablename__ = "provider_availability"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="availability_end_after_start"),
        Index("ix_provider_availability_provider_profile_id", "provider_profile_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profiles.id"), nullable=False
    )
    day_of_week: Mapped[DayOfWeek] = mapped_column(Enum(DayOfWeek, name="dayofweek"), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
