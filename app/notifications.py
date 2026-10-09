"""
Central dispatch for every user-facing notification this app sends
(new message, booking status change, new review, verification/report
decisions) across every channel it supports: email (always — every
user has one), SMS (when the recipient has added a phone number via
PATCH /v1/users/me/phone-number), and push (to every device token the
recipient has registered via POST /v1/users/me/device-tokens — see
app/push.py's docstring for why this one can't reach a real device yet
regardless, no mobile app existing to generate a real token).

Every notify_*  function here follows the same shape:
  1. Load the recipient's NotificationPreference row.
  2. If that event type is turned off (or, for messages, if the
     frequency setting says to skip this particular one), do nothing —
     on EVERY channel. Preferences are a single on/off per event type,
     not a per-channel choice; if an event is enabled, it goes out on
     every channel the recipient has available (email always, SMS if
     they've added a number, push to every device they've registered).
  3. Otherwise send the same message body via all of them.

Callers (the routers that trigger these events) never construct
email/SMS/push content themselves and never duplicate the "check
preferences first" logic — they call one of these functions after
whatever the triggering action was, same pattern as how
app/refresh_tokens.py centralizes token lifecycle logic instead of
scattering it across routers.

A failure to actually send (e.g. a real provider's API call fails, once
one exists) must never fail the triggering request — a review, a status
change, a message are all real and already committed before any of
these functions runs; notifying about them is a best-effort side effect,
not part of that transaction. Each notify_* call is wrapped in a
try/except by its caller for exactly this reason (see e.g.
app/routers/users.py's signup, which already does this for the
verification email) — this module itself doesn't swallow errors, so a
genuine bug here still surfaces in logs/tests. Each individual PUSH send
is additionally wrapped per-device inside _dispatch, so one stale/
invalid device token (a real possibility once a real push backend
exists — e.g. an uninstalled app) doesn't stop the others, or email/SMS,
from going out.
"""
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.email import send_email
from app.models.device_token import DeviceToken
from app.models.notification_preference import MessageNotificationFrequency, NotificationPreference
from app.models.user import User
from app.push import send_push
from app.sms import send_sms

logger = logging.getLogger(__name__)


async def _get_preferences(db: AsyncSession, user_id: uuid.UUID) -> NotificationPreference:
    result = await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    prefs = result.scalar_one_or_none()
    if prefs is not None:
        return prefs
    # Defensive fallback, not the expected path: every account gets a
    # NotificationPreference row at signup (app/routers/users.py). This
    # only matters for an account that somehow predates that — treat it
    # as "everything on, default frequency" rather than silently
    # notifying nobody.
    logger.warning("No NotificationPreference row for user %s; using defaults", user_id)
    return NotificationPreference()


async def _dispatch(db: AsyncSession, user: User, subject: str, body: str) -> None:
    await send_email(user.email, subject, body)
    if user.phone_number:
        await send_sms(user.phone_number, body)

    result = await db.execute(select(DeviceToken).where(DeviceToken.user_id == user.id))
    for device in result.scalars().all():
        try:
            await send_push(device.token, subject, body)
        except Exception:
            # Per-device, not per-recipient: one stale token failing
            # must not stop the same push reaching this user's OTHER
            # devices, or stop email/SMS above, which already succeeded.
            logger.exception("Failed to send push to device %s (user=%s)", device.id, user.id)


def _should_notify_new_message(prefs: NotificationPreference, is_first_message: bool) -> bool:
    """Pure, no DB — the one genuinely non-trivial decision here (the
    other event types are a single boolean check each, not worth a
    separate function). Split out specifically so this is unit-testable
    without a session/DB, unlike the notify_* functions themselves,
    which need one to load `prefs` in the first place."""
    if not prefs.notify_on_new_message:
        return False
    return prefs.message_frequency != MessageNotificationFrequency.first_message_only or is_first_message


async def notify_new_message(
    db: AsyncSession, recipient: User, sender_name: str, message_body: str, is_first_message: bool
) -> None:
    prefs = await _get_preferences(db, recipient.id)
    if not _should_notify_new_message(prefs, is_first_message):
        return
    await _dispatch(db, recipient, "New message", f"{sender_name}: {message_body}")


async def notify_booking_status_changed(db: AsyncSession, recipient: User, new_status: str) -> None:
    prefs = await _get_preferences(db, recipient.id)
    if not prefs.notify_on_booking_status_change:
        return
    await _dispatch(db, recipient, "Booking update", f"Your booking is now {new_status}.")


async def notify_new_review(db: AsyncSession, recipient: User, rating: int) -> None:
    prefs = await _get_preferences(db, recipient.id)
    if not prefs.notify_on_new_review:
        return
    await _dispatch(db, recipient, "New review", f"You received a new {rating}-star review.")


async def notify_verification_decision(
    db: AsyncSession, recipient: User, approved: bool, rejection_reason: str | None
) -> None:
    prefs = await _get_preferences(db, recipient.id)
    if not prefs.notify_on_verification_decision:
        return
    if approved:
        body = "Your identity verification was approved."
    else:
        body = f"Your identity verification was rejected: {rejection_reason}"
    await _dispatch(db, recipient, "Verification update", body)


async def notify_report_decision(db: AsyncSession, recipient: User, status: str) -> None:
    """recipient is the REPORTER, not the reported user — telling the
    reported person that a report about them was filed/resolved would
    tip off exactly the people this feature exists to catch, and
    nothing else in the moderation flow reveals that someone's been
    flagged to them either (see app/routers/bookings.py's 404-not-403
    on a deactivated profile for the same reasoning)."""
    prefs = await _get_preferences(db, recipient.id)
    if not prefs.notify_on_report_decision:
        return
    await _dispatch(db, recipient, "Report update", f"A report you filed has been {status}.")
