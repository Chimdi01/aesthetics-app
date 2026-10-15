"""
Batch 3 of the error-code migration (docs/backend-slices.md Slice 1
Step 1): admin, users, verification, provider profile/availability/
portfolio, and upload storage. Each test asserts status, error_code and
the unchanged `detail` (and `params` where set).
"""
import io

import pyotp
from PIL import Image
from sqlalchemy import text

from tests.conftest import login, register_user, test_engine

MISSING_ID = "00000000-0000-0000-0000-000000000000"
PROVIDER_PAYLOAD = {
    "business_name": "Studio",
    "currency": "GBP",
    "timezone": "Europe/London",
    "country": "GB",
    "categories": ["hair"],
}

_USER_ID_BY_EMAIL = text("SELECT id FROM users WHERE email = :email")
_PROMOTE_TO_ADMIN = text("UPDATE users SET role = 'admin' WHERE email = :email")
_DELETE_NOTIFICATION_PREFS = text(
    "DELETE FROM notification_preferences WHERE user_id = (SELECT id FROM users WHERE email = :email)"
)


def _jpeg() -> dict:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), (10, 20, 30)).save(buffer, format="JPEG")
    return {"file": ("id.jpg", io.BytesIO(buffer.getvalue()), "image/jpeg")}


async def _headers(client, email):
    await register_user(client, email)
    return {"Authorization": f"Bearer {await login(client, email)}"}


async def _admin(client, email="admin@example.com"):
    await register_user(client, email)
    async with test_engine.begin() as conn:
        await conn.execute(_PROMOTE_TO_ADMIN, {"email": email})
    return {"Authorization": f"Bearer {await login(client, email)}"}


async def _user_id(email):
    async with test_engine.connect() as conn:
        return str((await conn.execute(_USER_ID_BY_EMAIL, {"email": email})).scalar_one())


async def _submit_verification(client, headers):
    response = await client.post(
        "/v1/verification/me", files=_jpeg(), data={"document_type": "passport"}, headers=headers
    )
    return response.json()


def _assert_error(response, status_code, error_code, detail):
    assert response.status_code == status_code
    body = response.json()
    assert body["error_code"] == error_code
    assert body["detail"] == detail


# --- admin: verifications ---


async def test_review_unknown_verification_is_not_found(client):
    admin = await _admin(client)
    response = await client.patch(f"/v1/admin/verifications/{MISSING_ID}", json={"status": "approved"}, headers=admin)
    _assert_error(response, 404, "not_found", "Verification not found")


async def test_reviewing_own_verification_is_cannot_target_self(client):
    admin = await _admin(client)
    verification = await _submit_verification(client, admin)
    response = await client.patch(
        f"/v1/admin/verifications/{verification['id']}", json={"status": "approved"}, headers=admin
    )
    _assert_error(response, 400, "cannot_target_self", "You can't review your own verification submission")


async def test_re_reviewing_verification_is_invalid_state_with_params(client):
    admin = await _admin(client)
    user = await _headers(client, "u@example.com")
    verification = await _submit_verification(client, user)
    url = f"/v1/admin/verifications/{verification['id']}"
    await client.patch(url, json={"status": "approved"}, headers=admin)
    response = await client.patch(url, json={"status": "approved"}, headers=admin)
    _assert_error(response, 400, "invalid_state", "Verification is already approved")
    assert response.json()["params"] == {"status": "approved"}


# --- admin: reports ---


async def test_review_unknown_report_is_not_found(client):
    admin = await _admin(client)
    response = await client.patch(f"/v1/admin/reports/{MISSING_ID}", json={"status": "resolved"}, headers=admin)
    _assert_error(response, 404, "not_found", "Report not found")


async def test_reviewing_report_against_self_is_cannot_target_self(client):
    admin = await _admin(client)
    reporter = await _headers(client, "reporter@example.com")
    admin_id = await _user_id("admin@example.com")
    report = (await client.post(f"/v1/users/{admin_id}/report", json={"reason": "spam"}, headers=reporter)).json()
    response = await client.patch(f"/v1/admin/reports/{report['id']}", json={"status": "resolved"}, headers=admin)
    _assert_error(response, 400, "cannot_target_self", "You can't review a report filed against yourself")


async def test_re_reviewing_report_is_invalid_state_with_params(client):
    admin = await _admin(client)
    reporter = await _headers(client, "reporter@example.com")
    await register_user(client, "target@example.com")
    target_id = await _user_id("target@example.com")
    report = (await client.post(f"/v1/users/{target_id}/report", json={"reason": "spam"}, headers=reporter)).json()
    url = f"/v1/admin/reports/{report['id']}"
    await client.patch(url, json={"status": "dismissed"}, headers=admin)
    response = await client.patch(url, json={"status": "resolved"}, headers=admin)
    _assert_error(response, 400, "invalid_state", "Report is already dismissed")
    assert response.json()["params"] == {"status": "dismissed"}


# --- admin: accounts and sessions ---


async def test_deactivating_self_is_cannot_target_self(client):
    admin = await _admin(client)
    admin_id = await _user_id("admin@example.com")
    response = await client.patch(f"/v1/admin/users/{admin_id}/status", json={"is_active": False}, headers=admin)
    _assert_error(response, 400, "cannot_target_self", "You can't deactivate your own account")


async def test_status_of_unknown_user_is_not_found(client):
    admin = await _admin(client)
    response = await client.patch(f"/v1/admin/users/{MISSING_ID}/status", json={"is_active": False}, headers=admin)
    _assert_error(response, 404, "not_found", "User not found")


async def test_status_of_unknown_provider_is_not_found(client):
    admin = await _admin(client)
    response = await client.patch(
        f"/v1/admin/providers/{MISSING_ID}/status", json={"is_active": False}, headers=admin
    )
    _assert_error(response, 404, "not_found", "Provider profile not found")


async def test_revoke_all_without_confirm_is_invalid_state(client):
    admin = await _admin(client)
    response = await client.post("/v1/admin/revoke-all-sessions", json={}, headers=admin)
    _assert_error(response, 400, "invalid_state", "Set confirm=true to revoke every session platform-wide")


# --- users ---


async def test_duplicate_signup_is_duplicate_resource(client):
    await register_user(client, "dupe@example.com")
    response = await register_user(client, "dupe@example.com")
    _assert_error(response, 409, "duplicate_resource", "Email already registered")


async def test_missing_notification_preferences_is_not_found(client):
    headers = await _headers(client, "noprefs@example.com")
    async with test_engine.begin() as conn:
        await conn.execute(_DELETE_NOTIFICATION_PREFS, {"email": "noprefs@example.com"})
    response = await client.get("/v1/users/me/notification-preferences", headers=headers)
    _assert_error(response, 404, "not_found", "Notification preferences not found")


async def test_deleting_unknown_device_token_is_not_found(client):
    headers = await _headers(client, "dev@example.com")
    response = await client.delete(f"/v1/users/me/device-tokens/{MISSING_ID}", headers=headers)
    _assert_error(response, 404, "not_found", "Device token not found")


async def test_unknown_user_is_not_found(client):
    headers = await _headers(client, "looker@example.com")
    response = await client.get(f"/v1/users/{MISSING_ID}", headers=headers)
    _assert_error(response, 404, "not_found", "User not found")


# --- users: 2FA ---


async def test_confirm_before_enroll_is_invalid_state(client):
    headers = await _headers(client, "noenroll@example.com")
    response = await client.post("/v1/users/me/2fa/confirm", json={"code": "123456"}, headers=headers)
    _assert_error(response, 400, "invalid_state", "Call POST /me/2fa/enroll first")


async def test_confirm_with_wrong_code_is_invalid_code(client):
    headers = await _headers(client, "wrongcode@example.com")
    await client.post("/v1/users/me/2fa/enroll", headers=headers)
    wrong_code = pyotp.TOTP(pyotp.random_base32()).now()
    response = await client.post("/v1/users/me/2fa/confirm", json={"code": wrong_code}, headers=headers)
    _assert_error(response, 400, "invalid_code", "Invalid code")


async def test_enroll_when_enabled_is_invalid_state(client):
    headers = await _headers(client, "enabled@example.com")
    secret = (await client.post("/v1/users/me/2fa/enroll", headers=headers)).json()["secret"]
    await client.post("/v1/users/me/2fa/confirm", json={"code": pyotp.TOTP(secret).now()}, headers=headers)
    response = await client.post("/v1/users/me/2fa/enroll", headers=headers)
    _assert_error(response, 400, "invalid_state", "2FA is already enabled")


async def test_step_up_wrong_password_is_invalid_credentials(client):
    headers = await _headers(client, "stepup@example.com")
    response = await client.post("/v1/users/me/2fa/disable", json={"password": "wrong"}, headers=headers)
    _assert_error(response, 403, "invalid_credentials", "Incorrect password")


async def test_disable_when_not_enabled_is_invalid_state(client):
    headers = await _headers(client, "notenabled@example.com")
    response = await client.post("/v1/users/me/2fa/disable", json={"password": "secret123"}, headers=headers)
    _assert_error(response, 400, "invalid_state", "2FA is not enabled")


async def test_regenerate_with_wrong_password_is_invalid_credentials(client):
    headers = await _headers(client, "regen@example.com")
    response = await client.post(
        "/v1/users/me/2fa/backup-codes/regenerate", json={"password": "wrong"}, headers=headers
    )
    _assert_error(response, 403, "invalid_credentials", "Incorrect password")


# --- verification ---


async def test_resubmitting_when_verified_is_duplicate_resource(client):
    admin = await _admin(client)
    user = await _headers(client, "verified@example.com")
    verification = await _submit_verification(client, user)
    await client.patch(f"/v1/admin/verifications/{verification['id']}", json={"status": "approved"}, headers=admin)
    response = await client.post(
        "/v1/verification/me", files=_jpeg(), data={"document_type": "passport"}, headers=user
    )
    _assert_error(response, 409, "duplicate_resource", "You're already verified")


async def test_own_verification_before_submitting_is_not_found(client):
    headers = await _headers(client, "nosubmit@example.com")
    response = await client.get("/v1/verification/me", headers=headers)
    _assert_error(response, 404, "not_found", "No verification submitted yet")


async def test_own_document_before_submitting_is_not_found(client):
    headers = await _headers(client, "nodoc@example.com")
    response = await client.get("/v1/verification/me/document", headers=headers)
    _assert_error(response, 404, "not_found", "No verification submitted yet")


async def test_verification_upload_of_non_image_is_validation_failed(client):
    headers = await _headers(client, "badimg@example.com")
    response = await client.post(
        "/v1/verification/me",
        files={"file": ("id.jpg", io.BytesIO(b"not an image"), "image/jpeg")},
        data={"document_type": "passport"},
        headers=headers,
    )
    _assert_error(response, 422, "validation_failed", "Uploaded file is not a valid image")


# --- providers, availability, portfolio ---


async def test_admin_creating_provider_profile_is_forbidden(client):
    admin = await _admin(client)
    response = await client.post("/v1/providers/", json=PROVIDER_PAYLOAD, headers=admin)
    _assert_error(response, 403, "forbidden", "Admin accounts cannot hold a provider profile")


async def test_second_provider_profile_is_duplicate_resource(client):
    headers = await _headers(client, "twice@example.com")
    await client.post("/v1/providers/", json=PROVIDER_PAYLOAD, headers=headers)
    response = await client.post("/v1/providers/", json=PROVIDER_PAYLOAD, headers=headers)
    _assert_error(response, 409, "duplicate_resource", "Provider profile already exists for this user")


async def test_missing_payout_account_is_not_found(client):
    headers = await _headers(client, "nopayout@example.com")
    profile = (await client.post("/v1/providers/", json=PROVIDER_PAYLOAD, headers=headers)).json()
    async with test_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM provider_payout_accounts WHERE provider_profile_id = :id"), {"id": profile["id"]}
        )
    response = await client.get("/v1/providers/me/payout-account", headers=headers)
    _assert_error(response, 404, "not_found", "No payout account found for this provider")


async def test_unknown_provider_profile_is_not_found(client):
    response = await client.get(f"/v1/providers/{MISSING_ID}")
    _assert_error(response, 404, "not_found", "Provider profile not found")


async def test_unknown_provider_availability_is_not_found(client):
    response = await client.get(f"/v1/providers/{MISSING_ID}/availability")
    _assert_error(response, 404, "not_found", "Provider profile not found")


async def test_unknown_provider_portfolio_is_not_found(client):
    response = await client.get(f"/v1/providers/{MISSING_ID}/portfolio")
    _assert_error(response, 404, "not_found", "Provider profile not found")


async def test_deleting_unknown_portfolio_media_is_not_found(client):
    headers = await _headers(client, "pf@example.com")
    await client.post("/v1/providers/", json=PROVIDER_PAYLOAD, headers=headers)
    response = await client.delete(f"/v1/providers/me/portfolio/{MISSING_ID}", headers=headers)
    _assert_error(response, 404, "not_found", "Portfolio media not found")


async def test_portfolio_upload_of_disallowed_type_does_not_echo_it(client):
    headers = await _headers(client, "pdf@example.com")
    await client.post("/v1/providers/", json=PROVIDER_PAYLOAD, headers=headers)
    response = await client.post(
        "/v1/providers/me/portfolio",
        files={"file": ("doc.pdf", io.BytesIO(b"x"), "application/x-evil")},
        headers=headers,
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "validation_failed"
    assert "application/x-evil" not in response.text
    assert "image/jpeg" in body["params"]["allowed_types"]
