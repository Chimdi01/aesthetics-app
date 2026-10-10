"""
The admin-action audit trail (app/audit_log.py) exercised through the
real admin endpoints that write to it, and the real GET /admin/audit-log
listing that reads it back.
"""
import io

from PIL import Image
from sqlalchemy import text

from tests.conftest import login, register_user, test_engine


def _real_jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), (0, 128, 255)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _document_file():
    return {"file": ("id.jpg", io.BytesIO(_real_jpeg_bytes()), "image/jpeg")}


async def _promote_to_admin(email: str) -> None:
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email})


async def _create_admin_headers(client, email="admin@example.com"):
    await register_user(client, email, role="customer")
    await _promote_to_admin(email)
    token = await login(client, email)
    return {"Authorization": f"Bearer {token}"}


async def _get_entries(client, admin_headers, **params):
    response = await client.get("/v1/admin/audit-log", params=params, headers=admin_headers)
    assert response.status_code == 200
    return response.json()


async def test_audit_log_requires_admin(client):
    await register_user(client, "notadmin@example.com")
    token = await login(client, "notadmin@example.com")
    response = await client.get("/v1/admin/audit-log", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


async def test_audit_log_without_token_returns_401(client):
    response = await client.get("/v1/admin/audit-log")
    assert response.status_code == 401


async def test_audit_log_rejects_limit_over_100(client):
    admin_headers = await _create_admin_headers(client)
    response = await client.get(
        "/v1/admin/audit-log", params={"limit": 101}, headers=admin_headers
    )
    assert response.status_code == 422


async def test_verification_review_creates_an_audit_entry(client):
    await register_user(client, "verifysubmitter@example.com")
    submitter_token = await login(client, "verifysubmitter@example.com")
    submitted = (
        await client.post(
            "/v1/verification/me",
            files=_document_file(),
            data={"document_type": "passport"},
            headers={"Authorization": f"Bearer {submitter_token}"},
        )
    ).json()

    admin_headers = await _create_admin_headers(client, "verifyadmin@example.com")
    await client.patch(
        f"/v1/admin/verifications/{submitted['id']}", json={"status": "approved"}, headers=admin_headers
    )

    entries = await _get_entries(client, admin_headers, action="verification_reviewed")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["target_type"] == "identity_verification"
    assert entry["target_id"] == submitted["id"]
    assert entry["details"]["status"] == "approved"


async def test_report_review_creates_an_audit_entry(client):
    await register_user(client, "reporter@example.com")
    reporter_token = await login(client, "reporter@example.com")
    target = (await register_user(client, "reportedtarget@example.com")).json()

    report = (
        await client.post(
            f"/v1/users/{target['id']}/report",
            json={"reason": "spam"},
            headers={"Authorization": f"Bearer {reporter_token}"},
        )
    ).json()

    admin_headers = await _create_admin_headers(client, "reportadmin@example.com")
    await client.patch(
        f"/v1/admin/reports/{report['id']}", json={"status": "resolved"}, headers=admin_headers
    )

    entries = await _get_entries(client, admin_headers, action="report_reviewed")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["target_type"] == "report"
    assert entry["target_id"] == report["id"]
    assert entry["details"]["status"] == "resolved"
    assert entry["details"]["reported_user_id"] == target["id"]


async def test_user_status_change_creates_an_audit_entry_with_cascade_flag(client):
    # A PROVIDER account (with a real provider profile) — deactivating
    # it should cascade to the provider profile too, and the audit
    # entry's details should record that it happened.
    signup = await register_user(client, "provideruser@example.com", role="provider", full_name="Provider User")
    user_id = signup.json()["id"]
    provider_token = await login(client, "provideruser@example.com")
    await client.post(
        "/v1/providers/",
        json={"business_name": "Studio", "categories": ["hair"]},
        headers={"Authorization": f"Bearer {provider_token}"},
    )

    admin_headers = await _create_admin_headers(client, "statusadmin@example.com")
    response = await client.patch(
        f"/v1/admin/users/{user_id}/status", json={"is_active": False}, headers=admin_headers
    )
    assert response.status_code == 200

    entries = await _get_entries(client, admin_headers, action="user_status_changed", target_id=user_id)
    assert len(entries) == 1
    assert entries[0]["details"]["is_active"] is False
    assert entries[0]["details"]["cascaded_to_provider_profile"] is True
    assert entries[0]["target_type"] == "user"


async def test_user_status_change_without_a_provider_profile_does_not_cascade(client):
    signup = await register_user(client, "plaincustomer@example.com")
    user_id = signup.json()["id"]

    admin_headers = await _create_admin_headers(client, "nocascadeadmin@example.com")
    await client.patch(
        f"/v1/admin/users/{user_id}/status", json={"is_active": False}, headers=admin_headers
    )

    entries = await _get_entries(client, admin_headers, action="user_status_changed", target_id=user_id)
    assert entries[0]["details"]["cascaded_to_provider_profile"] is False


async def test_provider_status_change_creates_an_audit_entry(client):
    await register_user(client, "providerforstatus@example.com", role="provider", full_name="Jane")
    provider_token = await login(client, "providerforstatus@example.com")
    profile = (
        await client.post(
            "/v1/providers/",
            json={"business_name": "Jane's Studio", "categories": ["hair"]},
            headers={"Authorization": f"Bearer {provider_token}"},
        )
    ).json()

    admin_headers = await _create_admin_headers(client, "profilestatusadmin@example.com")
    response = await client.patch(
        f"/v1/admin/providers/{profile['id']}/status", json={"is_active": False}, headers=admin_headers
    )
    assert response.status_code == 200

    entries = await _get_entries(
        client, admin_headers, action="provider_status_changed", target_id=profile["id"]
    )
    assert len(entries) == 1
    assert entries[0]["target_type"] == "provider_profile"
    assert entries[0]["details"]["is_active"] is False


async def test_revoke_all_sessions_creates_an_audit_entry_with_no_target(client):
    admin_headers = await _create_admin_headers(client, "revokeauditadmin@example.com")
    response = await client.post(
        "/v1/admin/revoke-all-sessions", json={"confirm": True}, headers=admin_headers
    )
    assert response.status_code == 200
    revoked_count = response.json()["revoked_count"]

    entries = await _get_entries(client, admin_headers, action="sessions_revoked")
    assert len(entries) == 1
    assert entries[0]["target_type"] == "platform"
    assert entries[0]["target_id"] is None
    assert entries[0]["details"]["revoked_count"] == revoked_count


async def test_audit_log_is_visible_to_any_admin_not_just_the_one_who_acted(client):
    acting_admin_headers = await _create_admin_headers(client, "actingadmin@example.com")
    signup = await register_user(client, "someuser@example.com")
    user_id = signup.json()["id"]
    await client.patch(
        f"/v1/admin/users/{user_id}/status", json={"is_active": False}, headers=acting_admin_headers
    )

    other_admin_headers = await _create_admin_headers(client, "otheradmin@example.com")
    entries = await _get_entries(client, other_admin_headers, target_id=user_id)
    assert len(entries) == 1


async def test_audit_log_filters_by_admin_id(client):
    admin_a_signup = await register_user(client, "admina@example.com", role="customer")
    admin_a_id = admin_a_signup.json()["id"]
    await _promote_to_admin("admina@example.com")
    admin_a_headers = {"Authorization": f"Bearer {await login(client, 'admina@example.com')}"}

    admin_b_headers = await _create_admin_headers(client, "adminb@example.com")

    user_a = (await register_user(client, "targeta@example.com")).json()
    user_b = (await register_user(client, "targetb@example.com")).json()
    await client.patch(
        f"/v1/admin/users/{user_a['id']}/status", json={"is_active": False}, headers=admin_a_headers
    )
    await client.patch(
        f"/v1/admin/users/{user_b['id']}/status", json={"is_active": False}, headers=admin_b_headers
    )

    all_entries = await _get_entries(client, admin_a_headers)
    assert len(all_entries) == 2

    admin_a_entries = await _get_entries(client, admin_a_headers, admin_id=admin_a_id)
    assert len(admin_a_entries) == 1
    assert admin_a_entries[0]["target_id"] == user_a["id"]
