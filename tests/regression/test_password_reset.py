import re

from tests.conftest import register_user


def _extract_token(caplog_text: str) -> str:
    match = re.search(r"token=(\S+)", caplog_text)
    assert match, f"no token found in logged email: {caplog_text!r}"
    return match.group(1)


async def test_forgot_password_for_registered_email_sends_reset_link(client, caplog):
    await register_user(client, "resetme@example.com")

    # caplog.clear(): the app's root logger already runs at INFO by
    # default (app/logging_config.py), so caplog captures every INFO
    # line for the whole test regardless of any `with caplog.at_level`
    # scoping — register_user above already triggered its own
    # verify-email send. Without clearing first, _extract_token would
    # happily match THAT token instead of the reset-password one this
    # test actually cares about (caught the hard way: a 400 from
    # reset-password, not an assertion failure here).
    caplog.clear()
    response = await client.post("/v1/auth/forgot-password", json={"email": "resetme@example.com"})
    assert response.status_code == 200
    assert "token=" in caplog.text
    assert "resetme@example.com" in caplog.text


async def test_forgot_password_for_unknown_email_returns_the_same_generic_response(client):
    await register_user(client, "known@example.com")

    known_response = await client.post("/v1/auth/forgot-password", json={"email": "known@example.com"})
    unknown_response = await client.post(
        "/v1/auth/forgot-password", json={"email": "no-such-account@example.com"}
    )

    # No information leak about which emails are registered, in the
    # RESPONSE specifically: same status, same body either way. (Server-
    # side logging the attempted email either way is fine and expected —
    # same precedent as login's "Failed login attempt for %s" — the
    # property being tested is about what the caller gets back, not
    # what lands in the server's own logs.)
    assert known_response.status_code == unknown_response.status_code == 200
    assert known_response.json() == unknown_response.json()


async def test_reset_password_with_valid_token_changes_the_password(client, caplog):
    await register_user(client, "changeme@example.com")

    caplog.clear()
    await client.post("/v1/auth/forgot-password", json={"email": "changeme@example.com"})
    token = _extract_token(caplog.text)

    response = await client.post(
        "/v1/auth/reset-password", json={"token": token, "new_password": "brandnewpassword123"}
    )
    assert response.status_code == 204

    old_password_login = await client.post(
        "/v1/auth/login", data={"username": "changeme@example.com", "password": "secret123"}
    )
    assert old_password_login.status_code == 401

    new_password_login = await client.post(
        "/v1/auth/login", data={"username": "changeme@example.com", "password": "brandnewpassword123"}
    )
    assert new_password_login.status_code == 200


async def test_reset_password_with_invalid_token_returns_400(client):
    response = await client.post(
        "/v1/auth/reset-password", json={"token": "not-a-real-token", "new_password": "whatever123"}
    )
    assert response.status_code == 400


async def test_reset_password_rejects_a_too_short_new_password(client, caplog):
    await register_user(client, "shortpw@example.com")
    caplog.clear()
    await client.post("/v1/auth/forgot-password", json={"email": "shortpw@example.com"})
    token = _extract_token(caplog.text)

    response = await client.post("/v1/auth/reset-password", json={"token": token, "new_password": "short"})
    assert response.status_code == 422


async def test_reset_password_token_is_single_use(client, caplog):
    await register_user(client, "singleuse@example.com")
    caplog.clear()
    await client.post("/v1/auth/forgot-password", json={"email": "singleuse@example.com"})
    token = _extract_token(caplog.text)

    first = await client.post(
        "/v1/auth/reset-password", json={"token": token, "new_password": "firstnewpassword123"}
    )
    assert first.status_code == 204

    second = await client.post(
        "/v1/auth/reset-password", json={"token": token, "new_password": "secondnewpassword123"}
    )
    assert second.status_code == 400


async def test_a_second_forgot_password_request_invalidates_the_first_link(client, caplog):
    await register_user(client, "superseded-reset@example.com")

    caplog.clear()
    await client.post("/v1/auth/forgot-password", json={"email": "superseded-reset@example.com"})
    first_token = _extract_token(caplog.text)

    caplog.clear()
    await client.post("/v1/auth/forgot-password", json={"email": "superseded-reset@example.com"})

    response = await client.post(
        "/v1/auth/reset-password", json={"token": first_token, "new_password": "whatever123456"}
    )
    assert response.status_code == 400


async def test_reset_password_revokes_every_existing_refresh_token(client, caplog):
    await register_user(client, "revokeall@example.com")
    session_a = await client.post(
        "/v1/auth/login", data={"username": "revokeall@example.com", "password": "secret123"}
    )
    session_b = await client.post(
        "/v1/auth/login", data={"username": "revokeall@example.com", "password": "secret123"}
    )

    caplog.clear()
    await client.post("/v1/auth/forgot-password", json={"email": "revokeall@example.com"})
    token = _extract_token(caplog.text)
    await client.post("/v1/auth/reset-password", json={"token": token, "new_password": "postresetpassword123"})

    # A password reset is a credential-compromise-recovery action — every
    # session issued before it must stop working, not just the device
    # that triggered it.
    refresh_a = await client.post(
        "/v1/auth/refresh", json={"refresh_token": session_a.json()["refresh_token"]}
    )
    refresh_b = await client.post(
        "/v1/auth/refresh", json={"refresh_token": session_b.json()["refresh_token"]}
    )
    assert refresh_a.status_code == 401
    assert refresh_b.status_code == 401


async def test_forgot_password_without_registered_account_does_not_crash(client):
    # No account exists at all for this email — the endpoint must still
    # behave identically to the "known" case, not 500.
    response = await client.post("/v1/auth/forgot-password", json={"email": "truly-nobody@example.com"})
    assert response.status_code == 200
