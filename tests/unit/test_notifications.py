"""
Pure logic, no DB/HTTP — app/notifications.py's one genuinely
non-trivial decision (message frequency). The rest of that module
(loading preferences, actually sending) needs a DB/real dispatch and is
covered through the real endpoints instead — see
tests/regression/test_notifications.py.
"""
from app.models.notification_preference import MessageNotificationFrequency, NotificationPreference
from app.notifications import _should_notify_new_message


def _prefs(**overrides) -> NotificationPreference:
    defaults = {
        "notify_on_new_message": True,
        "message_frequency": MessageNotificationFrequency.every_message,
    }
    defaults.update(overrides)
    return NotificationPreference(**defaults)


def test_notifies_for_every_message_when_frequency_is_every_message():
    prefs = _prefs(message_frequency=MessageNotificationFrequency.every_message)
    assert _should_notify_new_message(prefs, is_first_message=True)
    assert _should_notify_new_message(prefs, is_first_message=False)


def test_first_message_only_notifies_on_the_first_message():
    prefs = _prefs(message_frequency=MessageNotificationFrequency.first_message_only)
    assert _should_notify_new_message(prefs, is_first_message=True)


def test_first_message_only_skips_later_messages():
    prefs = _prefs(message_frequency=MessageNotificationFrequency.first_message_only)
    assert not _should_notify_new_message(prefs, is_first_message=False)


def test_disabled_entirely_skips_even_the_first_message():
    prefs = _prefs(notify_on_new_message=False, message_frequency=MessageNotificationFrequency.every_message)
    assert not _should_notify_new_message(prefs, is_first_message=True)
