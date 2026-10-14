"""
Batch 1 of the error-code migration (docs/backend-slices.md Slice 1
Step 1): every error raised from app/security.py and app/routers/auth.py
carries its approved error_code, with `detail` unchanged.
"""
import pyotp
from sqlalchemy import text

from tests.conftest import login, register_user, test_engine

_UPDATES = {
    "is_active": text("UPDATE users SET is_active = :value WHERE email = :email"),
    "email_verified": text("UPDATE users SET email_verified = :value WHERE email = :email"),
}


async def _set_user_column(email: str, column: str, value: bool) -> None:
    async with test_engine.begin() as conn:
        await conn.execute(_UPDATES[column], {"value": value, "email": email})


def _assert_error(response, status_code: int, error_code: str, detail: str) -> None:
    assert response.status_code == status_code
    body = response.json()
    assert body["error_code"] == error_code
    assert body["detail"] == detail


# --- app/security.py ---


async def test_invalid_access_token_is_unauthenticated(client):
    response = await client.post("/v1/auth/logout-all", headers={"Authorization": "Bearer not-a-real-token"})
    _assert_error(response, 401, "unauthenticated", "Could not validate credentials")
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_missing_access_token_is_unauthenticated(client):
    # Raised by FastAPI's own OAuth2PasswordBearer, not our code — reaches
    # the envelope through the Starlette-level fallback handler.
    response = await client.post("/v1/auth/logout-all")
    assert response.status_code == 401
    assert response.json()["error_code"] == "unauthenticated"


async def test_token_for_deactivated_account_is_account_deactivated(client):
    await register_user(client, "deact-token@example.com")
    token = await login(client, "deact-token@example.com")
    await _set_user_column("deact-token@example.com", "is_active", False)
    response = await client.post("/v1/auth/logout-all", headers={"Authorization": f"Bearer {token}"})
    _assert_error(response, 403, "account_deactivated", "This account has been deactivated")


async def test_non_admin_on_admin_route_is_forbidden(client):
    await register_user(client, "notadmin@example.com")
    token = await login(client, "notadmin@example.com")
    response = await client.get("/v1/admin/verifications", headers={"Authorization": f"Bearer {token}"})
    _assert_error(response, 403, "forbidden", "Admins only")


# --- app/routers/auth.py ---


async def test_wrong_password_is_invalid_credentials(client):
    await register_user(client, "wrongpw@example.com")
    response = await client.post("/v1/auth/login", data={"username": "wrongpw@example.com", "password": "nope"})
    _assert_error(response, 401, "invalid_credentials", "Incorrect email or password")
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_unknown_email_is_invalid_credentials(client):
    response = await client.post("/v1/auth/login", data={"username": "ghost@example.com", "password": "nope"})
    _assert_error(response, 401, "invalid_credentials", "Incorrect email or password")


async def test_login_to_deactivated_account_is_account_deactivated(client):
    await register_user(client, "deact-login@example.com")
    await _set_user_column("deact-login@example.com", "is_active", False)
    response = await client.post(
        "/v1/auth/login", data={"username": "deact-login@example.com", "password": "secret123"}
    )
    _assert_error(response, 403, "account_deactivated", "This account has been deactivated")


async def test_bogus_mfa_challenge_is_unauthenticated(client):
    response = await client.post("/v1/auth/login/verify-2fa", json={"mfa_token": "bogus", "code": "123456"})
    _assert_error(response, 401, "unauthenticated", "Invalid or expired login challenge")


async def test_wrong_2fa_code_at_login_is_invalid_code(client):
    await register_user(client, "badcode@example.com")
    token = await login(client, "badcode@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    secret = (await client.post("/v1/users/me/2fa/enroll", headers=headers)).json()["secret"]
    await client.post("/v1/users/me/2fa/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=headers)

    challenge = await client.post("/v1/auth/login", data={"username": "badcode@example.com", "password": "secret123"})
    mfa_token = challenge.json()["mfa_token"]
    # A real code from a DIFFERENT secret: well-formed, just wrong.
    wrong_code = pyotp.TOTP(pyotp.random_base32()).now()
    response = await client.post("/v1/auth/login/verify-2fa", json={"mfa_token": mfa_token, "code": wrong_code})
    _assert_error(response, 401, "invalid_code", "Invalid code")


async def test_bogus_refresh_token_is_unauthenticated(client):
    response = await client.post("/v1/auth/refresh", json={"refresh_token": "bogus"})
    _assert_error(response, 401, "unauthenticated", "Invalid or expired refresh token")


async def test_refresh_for_deactivated_account_is_account_deactivated(client):
    await register_user(client, "deact-refresh@example.com")
    tokens = (
        await client.post("/v1/auth/login", data={"username": "deact-refresh@example.com", "password": "secret123"})
    ).json()
    await _set_user_column("deact-refresh@example.com", "is_active", False)
    response = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    _assert_error(response, 403, "account_deactivated", "This account has been deactivated")


async def test_bogus_verification_link_is_token_invalid_or_expired(client):
    response = await client.post("/v1/auth/verify-email", json={"token": "bogus"})
    _assert_error(response, 400, "token_invalid_or_expired", "Invalid or expired verification link")


async def test_resend_verification_when_already_verified_is_invalid_state(client):
    await register_user(client, "verified@example.com")
    token = await login(client, "verified@example.com")
    await _set_user_column("verified@example.com", "email_verified", True)
    response = await client.post("/v1/auth/resend-verification", headers={"Authorization": f"Bearer {token}"})
    _assert_error(response, 400, "invalid_state", "Email is already verified")


async def test_bogus_reset_link_is_token_invalid_or_expired(client):
    response = await client.post("/v1/auth/reset-password", json={"token": "bogus", "new_password": "new-secret-123"})
    _assert_error(response, 400, "token_invalid_or_expired", "Invalid or expired reset link")
