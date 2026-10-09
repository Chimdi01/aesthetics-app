"""
Pure logic, no DB/HTTP — these functions only ever touch the two fields
on a plain User() instance, never a session.
"""
from datetime import UTC, datetime, timedelta

from app.login_lockout import FAILURE_THRESHOLD, is_locked_out, record_failed_login, record_successful_login
from app.models.user import User


def _bare_user() -> User:
    # No id/email/etc. needed — only the two lockout fields matter here,
    # and this never touches a session/DB.
    return User(failed_login_attempts=0, login_locked_until=None)


def test_no_lockout_below_the_threshold():
    user = _bare_user()
    for _ in range(FAILURE_THRESHOLD - 1):
        record_failed_login(user)
    assert not is_locked_out(user)


def test_lockout_kicks_in_at_the_threshold():
    user = _bare_user()
    for _ in range(FAILURE_THRESHOLD):
        record_failed_login(user)
    assert is_locked_out(user)


def test_lockout_window_increases_with_more_consecutive_failures():
    user = _bare_user()
    for _ in range(FAILURE_THRESHOLD):
        record_failed_login(user)
    first_lockout_until = user.login_locked_until

    # One more failure, past the threshold, should extend the window
    # further out than the first lockout did.
    record_failed_login(user)
    assert user.login_locked_until > first_lockout_until


def test_lockout_duration_caps_rather_than_growing_forever():
    user = _bare_user()
    for _ in range(FAILURE_THRESHOLD + 10):
        record_failed_login(user)
    capped_until = user.login_locked_until

    record_failed_login(user)
    # The 11th-and-later failures all land on the same capped duration —
    # successive lockouts should land close together (same schedule
    # entry), not keep climbing without bound.
    assert abs((user.login_locked_until - capped_until).total_seconds()) < 1


def test_is_locked_out_false_when_never_locked():
    assert not is_locked_out(_bare_user())


def test_is_locked_out_false_once_the_window_has_passed():
    user = _bare_user()
    user.login_locked_until = datetime.now(UTC) - timedelta(seconds=1)
    assert not is_locked_out(user)


def test_is_locked_out_true_while_the_window_is_still_active():
    user = _bare_user()
    user.login_locked_until = datetime.now(UTC) + timedelta(minutes=5)
    assert is_locked_out(user)


def test_successful_login_clears_the_lockout_state():
    user = _bare_user()
    for _ in range(FAILURE_THRESHOLD):
        record_failed_login(user)
    assert is_locked_out(user)

    record_successful_login(user)
    assert user.failed_login_attempts == 0
    assert user.login_locked_until is None
    assert not is_locked_out(user)
