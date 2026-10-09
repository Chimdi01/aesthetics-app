"""
One row per user, created automatically at signup (see
app/routers/users.py's create_user) — every account has exactly one of
these, same cardinality as a hypothetical 1:1 profile table, which is
why it's a separate table rather than more columns bolted onto User:
this is a cohesive concern (notification settings) a user manages
together, not individual facts about them the way email/role/is_active
are.

Defaults are all "on" / "every message" — the safer default for a
feature just launching is over-notifying (easy for a user to dial back)
rather under-notifying (a user missing something they actually wanted
to see, with no obvious reason to go looking for a settings page they
don't know exists yet).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MessageNotificationFrequency(str, enum.Enum):
    # Every message in a booking's conversation triggers a notification.
    every_message = "every_message"
    # Only the FIRST message in a given booking's conversation does —
    # the "milestone, not noise" option for a user who wants to know a
    # conversation started but not be pinged for every back-and-forth
    # reply after that.
    first_message_only = "first_message_only"


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)

    notify_on_new_message: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    message_frequency: Mapped[MessageNotificationFrequency] = mapped_column(
        Enum(MessageNotificationFrequency, name="messagenotificationfrequency"),
        default=MessageNotificationFrequency.every_message,
        nullable=False,
    )
    notify_on_booking_status_change: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_on_new_review: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_on_verification_decision: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Goes to the REPORTER when a report they filed is resolved/dismissed
    # — not to the reported user (see app/notifications.py's
    # notify_report_decision docstring for why).
    notify_on_report_decision: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
