"""
Per-ACCOUNT login lockout — a second, independent layer on top of
app/rate_limit.py's per-IP limit on POST /auth/login (5/minute). The
per-IP limit doesn't stop a slow, distributed brute force spread across
many IPs against ONE account; this does, by tracking consecutive
failures on the account itself, regardless of which IP they came from.

Exponential backoff, not a permanent lock: each additional failure past
the threshold increases the cooldown, capped at _LOCKOUT_SCHEDULE's last
entry — long enough to make brute-forcing impractical, short enough that
a legitimate confused user (or an attacker just trying to lock someone
out as harassment) doesn't permanently strand the account. A genuinely
successful login clears the counter entirely.

Deliberately does NOT change the HTTP response when locked — see
app/routers/auth.py's login(): a locked-out attempt gets the exact same
generic "Incorrect email or password" 401 a wrong password gets, so
this can't be used to enumerate which accounts exist (same anti-
enumeration stance already applied to login's email case-normalization
and to /auth/forgot-password's generic response). Only the server-side
log line distinguishes it.

These functions mutate the given User object in place and never touch
the DB themselves — the caller (app/routers/auth.py's login()) commits,
same convention as app/refresh_tokens.py/app/email_tokens.py. That also
makes them trivially unit-testable: no session, no DB, just a plain
User() with two fields set.
"""
from datetime import UTC, datetime, timedelta

from app.models.user import User

# Failures allowed before any lockout kicks in — low enough to matter,
# high enough that a real user who mistypes their password a couple of
# times never notices this exists.
FAILURE_THRESHOLD = 5

# Index 0 applies at the threshold-th failure, index 1 at the next one,
# etc.; the last entry is reused for every failure beyond it (the cap) —
# see _lockout_duration.
_LOCKOUT_SCHEDULE = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(minutes=60),
]


def _lockout_duration(failed_attempts: int) -> timedelta | None:
    if failed_attempts < FAILURE_THRESHOLD:
        return None
    index = min(failed_attempts - FAILURE_THRESHOLD, len(_LOCKOUT_SCHEDULE) - 1)
    return _LOCKOUT_SCHEDULE[index]


def is_locked_out(user: User) -> bool:
    return user.login_locked_until is not None and user.login_locked_until > datetime.now(UTC)


def record_failed_login(user: User) -> None:
    """Increments the consecutive-failure counter and sets/extends the
    lockout window once the threshold is crossed."""
    user.failed_login_attempts += 1
    duration = _lockout_duration(user.failed_login_attempts)
    if duration is not None:
        user.login_locked_until = datetime.now(UTC) + duration


def record_successful_login(user: User) -> None:
    """A genuinely successful login clears the slate entirely."""
    user.failed_login_attempts = 0
    user.login_locked_until = None
