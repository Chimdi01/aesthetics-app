"""
A single message in the back-and-forth between a booking's customer and
provider — scoped to a Booking, not a general DM system. Matches the
roadmap's V1 scope: "basic in-app messaging for booking back-and-forth" —
a generic messaging system between arbitrary users is more than V1 needs.

Push notifications on new messages are NOT built here — that needs a push
provider (FCM/APNs) and device-token registration, a separate
external-account workstream (like Stripe, deferred for the same reason:
needs an account/credentials this session doesn't have). This model and
its endpoints just persist and retrieve messages; notifying either party
is a follow-up once that account exists.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Every read here is "messages for this booking, oldest first" —
        # one composite index serves both the filter and the sort, so
        # listing a booking's conversation stays an index scan no matter
        # how many total messages/bookings exist platform-wide.
        Index("ix_messages_booking_id_created_at", "booking_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
