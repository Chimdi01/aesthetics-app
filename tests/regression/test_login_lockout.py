"""
The per-account lockout (app/login_lockout.py) exercised through the
real POST /v1/auth/login endpoint.

app.state.limiter.reset() between simulated attempts: this is deliberate
and needed, not a workaround for a bug. Login's own per-IP rate limit
(5/minute, see app/routers/auth.py) would otherwise 429 these tests'
6th+ rapid call from the one "IP" the test client shares — that's a
DIFFERENT, already-covered protection layer (see
tests/regression/test_rate_limiting.py), and resetting it here isolates
the per-ACCOUNT lockout this file is actually testing from the per-IP
one.
"""
from app.main import app
from tests.conftest import register_user


async def _attempt_login(client, email, password):
    app.state.limiter.reset()
    return await client.post("/v1/auth/login", data={"username": email, "password": password})


async def test_account_locks_out_after_five_consecutive_failed_attempts(client):
    await register_user(client, "lockout@example.com")

    for _ in range(5):
        response = await _attempt_login(client, "lockout@example.com", "wrong-password")
        assert response.status_code == 401

    # The decisive check: even the CORRECT password now fails, because
    # the account itself is locked — if lockout weren't working, this
    # would succeed (200) on what would otherwise be a perfectly valid
    # 6th attempt.
    locked_attempt = await _attempt_login(client, "lockout@example.com", "secret123")
    assert locked_attempt.status_code == 401


async def test_fewer_than_five_failures_do_not_lock_the_account(client):
    await register_user(client, "notlocked@example.com")

    for _ in range(4):
        response = await _attempt_login(client, "notlocked@example.com", "wrong-password")
        assert response.status_code == 401

    success = await _attempt_login(client, "notlocked@example.com", "secret123")
    assert success.status_code == 200


async def test_successful_login_resets_the_failure_counter(client):
    await register_user(client, "resets@example.com")

    for _ in range(3):
        await _attempt_login(client, "resets@example.com", "wrong-password")
    # A real success in between should clear the slate — the 3 prior
    # failures must not carry over and combine with fresh ones.
    assert (await _attempt_login(client, "resets@example.com", "secret123")).status_code == 200

    for _ in range(4):
        response = await _attempt_login(client, "resets@example.com", "wrong-password")
        assert response.status_code == 401
    # Only 4 failures since the reset — one short of the threshold, so
    # this must still succeed.
    final = await _attempt_login(client, "resets@example.com", "secret123")
    assert final.status_code == 200


async def test_locked_out_response_is_identical_to_a_normal_wrong_password(client):
    # Anti-enumeration: a locked-out account must not be distinguishable
    # from a simple wrong-password response — otherwise the lockout
    # mechanism itself would leak which accounts exist.
    await register_user(client, "sameresponse@example.com")
    for _ in range(5):
        await _attempt_login(client, "sameresponse@example.com", "wrong-password")

    locked_response = await _attempt_login(client, "sameresponse@example.com", "secret123")
    wrong_password_response = await _attempt_login(client, "neverregistered@example.com", "whatever")

    assert locked_response.status_code == wrong_password_response.status_code == 401
    assert locked_response.json() == wrong_password_response.json()


async def test_lockout_does_not_affect_other_accounts(client):
    await register_user(client, "victim@example.com")
    await register_user(client, "innocent@example.com")

    for _ in range(5):
        await _attempt_login(client, "victim@example.com", "wrong-password")

    # A different account, never touched, logs in fine.
    response = await _attempt_login(client, "innocent@example.com", "secret123")
    assert response.status_code == 200
