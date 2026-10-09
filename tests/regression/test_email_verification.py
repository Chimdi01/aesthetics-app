import re

from tests.conftest import login, register_user


def _extract_token(caplog_text: str) -> str:
    # app/email.py's console backend logs the whole email body, which
    # contains "...?token=<raw_token>" — this is how a test "receives"
    # the email without a real provider wired up yet.
    match = re.search(r"token=(\S+)", caplog_text)
    assert match, f"no token found in logged email: {caplog_text!r}"
    return match.group(1)


async def test_signup_sends_a_verification_email(client, caplog):
    with caplog.at_level("INFO"):
        await register_user(client, "newuser@example.com")
    assert "newuser@example.com" in caplog.text
    assert "Verify your email" in caplog.text
    assert "token=" in caplog.text


async def test_new_signup_is_unverified_until_the_link_is_used(client):
    response = await register_user(client, "unverified@example.com")
    assert response.json()["email_verified"] is False


async def test_verify_email_with_valid_token_returns_204(client, caplog):
    with caplog.at_level("INFO"):
        await register_user(client, "toverify@example.com")
    token = _extract_token(caplog.text)

    response = await client.post("/v1/auth/verify-email", json={"token": token})
    assert response.status_code == 204


async def test_verify_email_actually_persists_on_the_user(client, caplog):
    with caplog.at_level("INFO"):
        signup = await register_user(client, "persists@example.com")
    user_id = signup.json()["id"]
    token = _extract_token(caplog.text)

    await client.post("/v1/auth/verify-email", json={"token": token})

    access_token = await login(client, "persists@example.com")
    response = await client.get(f"/v1/users/{user_id}", headers={"Authorization": f"Bearer {access_token}"})
    assert response.json()["email_verified"] is True


async def test_verify_email_with_invalid_token_returns_400(client):
    response = await client.post("/v1/auth/verify-email", json={"token": "not-a-real-token"})
    assert response.status_code == 400


async def test_verify_email_token_is_single_use(client, caplog):
    with caplog.at_level("INFO"):
        await register_user(client, "onceonly@example.com")
    token = _extract_token(caplog.text)

    first = await client.post("/v1/auth/verify-email", json={"token": token})
    assert first.status_code == 204

    second = await client.post("/v1/auth/verify-email", json={"token": token})
    assert second.status_code == 400


async def test_resend_verification_without_token_returns_401(client):
    response = await client.post("/v1/auth/resend-verification")
    assert response.status_code == 401


async def test_resend_verification_sends_a_new_working_link(client, caplog):
    await register_user(client, "resend@example.com")
    access_token = await login(client, "resend@example.com")

    # Cleared first: signup above already logged its own verify-email
    # token, and the app's root logger runs at INFO by default, so
    # caplog already holds that line regardless of the `with
    # caplog.at_level` below — without clearing, _extract_token would
    # grab signup's (now-invalidated-by-resend) token instead of this
    # call's new one.
    caplog.clear()
    with caplog.at_level("INFO"):
        response = await client.post(
            "/v1/auth/resend-verification", headers={"Authorization": f"Bearer {access_token}"}
        )
    assert response.status_code == 204
    new_token = _extract_token(caplog.text)

    verify = await client.post("/v1/auth/verify-email", json={"token": new_token})
    assert verify.status_code == 204


async def test_resend_verification_invalidates_the_earlier_link(client, caplog):
    with caplog.at_level("INFO"):
        await register_user(client, "superseded@example.com")
    original_token = _extract_token(caplog.text)
    access_token = await login(client, "superseded@example.com")

    caplog.clear()
    with caplog.at_level("INFO"):
        await client.post("/v1/auth/resend-verification", headers={"Authorization": f"Bearer {access_token}"})

    # The link from signup no longer works — only the one just resent does.
    response = await client.post("/v1/auth/verify-email", json={"token": original_token})
    assert response.status_code == 400


async def test_resend_verification_rejected_once_already_verified(client, caplog):
    with caplog.at_level("INFO"):
        await register_user(client, "alreadyverified@example.com")
    token = _extract_token(caplog.text)
    await client.post("/v1/auth/verify-email", json={"token": token})

    access_token = await login(client, "alreadyverified@example.com")
    response = await client.post(
        "/v1/auth/resend-verification", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 400
