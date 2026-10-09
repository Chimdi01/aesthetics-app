"""
Separate from app/schemas/user.py — same reasoning as every other
schemas/ split in this codebase: this describes the NotificationPreference
resource, not User.
"""
from pydantic import BaseModel, ConfigDict

from app.models.notification_preference import MessageNotificationFrequency


class NotificationPreferencesPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notify_on_new_message: bool
    message_frequency: MessageNotificationFrequency
    notify_on_booking_status_change: bool
    notify_on_new_review: bool
    notify_on_verification_decision: bool
    notify_on_report_decision: bool


class NotificationPreferencesUpdate(BaseModel):
    # Every field optional: a PARTIAL update (PATCH semantics) — set
    # only the ones you want to change. None/omitted means "leave this
    # one alone", not "turn it off" — see app/routers/users.py's
    # update_notification_preferences, which applies via
    # model_dump(exclude_unset=True) for exactly that reason.
    notify_on_new_message: bool | None = None
    message_frequency: MessageNotificationFrequency | None = None
    notify_on_booking_status_change: bool | None = None
    notify_on_new_review: bool | None = None
    notify_on_verification_decision: bool | None = None
    notify_on_report_decision: bool | None = None
