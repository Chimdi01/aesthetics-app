import io

import pytest
from PIL import Image
from sqlalchemy import text

from tests.conftest import login, register_user, test_engine


def _real_jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (50, 50), (0, 128, 255)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _document_file(content: bytes | None = None):
    return {"file": ("id.jpg", io.BytesIO(content or _real_jpeg_bytes()), "image/jpeg")}


async def _create_user_headers(client, email="user@example.com", role="customer"):
    await register_user(client, email, password="secret123", role=role)
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def _promote_to_admin(email: str) -> None:
    # Matches the real provisioning path (see CLAUDE.md): there is no API
    # that grants the admin role — only a direct DB update.
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email})


async def _create_admin_headers(client, email="admin@example.com"):
    headers = await _create_user_headers(client, email, role="customer")
    await _promote_to_admin(email)
    # Re-login: the existing token's "sub" is still valid (role isn't
    # embedded in the token), so this isn't strictly required for auth to
    # keep working — it's here to mirror how a real admin would pick up
    # the change after being promoted mid-session.
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


# --- the privilege-escalation fix, exercised through the real endpoint ---


async def test_signup_with_admin_role_is_rejected(client):
    response = await register_user(client, "wannabe-admin@example.com", role="admin")
    assert response.status_code == 422


# --- self-service submission ---


async def test_submit_verification_success(client):
    headers = await _create_user_headers(client)
    response = await client.post(
        "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["document_type"] == "passport"


async def test_submit_verification_without_token_returns_401(client):
    response = await client.post("/v1/verification/me", files=_document_file(), data={"document_type": "passport"})
    assert response.status_code == 401


async def test_submit_verification_rejects_invalid_image(client):
    headers = await _create_user_headers(client)
    response = await client.post(
        "/v1/verification/me",
        files=_document_file(content=b"not an image"),
        data={"document_type": "passport"},
        headers=headers,
    )
    assert response.status_code == 400


async def test_get_my_verification_before_submitting_returns_404(client):
    headers = await _create_user_headers(client)
    response = await client.get("/v1/verification/me", headers=headers)
    assert response.status_code == 404


async def test_get_my_verification_document_round_trips(client):
    headers = await _create_user_headers(client)
    content = _real_jpeg_bytes()
    await client.post(
        "/v1/verification/me", files=_document_file(content), data={"document_type": "national_id"}, headers=headers
    )

    response = await client.get("/v1/verification/me/document", headers=headers)
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"


async def test_resubmit_while_pending_replaces_previous_submission(client):
    headers = await _create_user_headers(client)
    await client.post("/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers)

    new_content = _real_jpeg_bytes()
    response = await client.post(
        "/v1/verification/me",
        files=_document_file(new_content),
        data={"document_type": "drivers_license"},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["document_type"] == "drivers_license"

    document = await client.get("/v1/verification/me/document", headers=headers)
    assert document.content == new_content


async def test_cannot_resubmit_after_approval(client):
    headers = await _create_user_headers(client, "toapprove@example.com")
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
        )
    ).json()

    admin_headers = await _create_admin_headers(client)
    await client.patch(
        f"/v1/admin/verifications/{submitted['id']}", json={"status": "approved"}, headers=admin_headers
    )

    response = await client.post(
        "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
    )
    assert response.status_code == 409


async def test_can_resubmit_after_rejection(client):
    headers = await _create_user_headers(client, "torejectresubmit@example.com")
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
        )
    ).json()

    admin_headers = await _create_admin_headers(client)
    await client.patch(
        f"/v1/admin/verifications/{submitted['id']}",
        json={"status": "rejected", "rejection_reason": "Blurry"},
        headers=admin_headers,
    )

    response = await client.post(
        "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
    )
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert response.json()["rejection_reason"] is None


# --- admin authorization boundaries ---


async def test_non_admin_cannot_list_verifications(client):
    headers = await _create_user_headers(client)
    response = await client.get("/v1/admin/verifications", headers=headers)
    assert response.status_code == 403


async def test_non_admin_cannot_view_verification_document(client):
    owner_headers = await _create_user_headers(client, "owner@example.com")
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=owner_headers
        )
    ).json()

    stranger_headers = await _create_user_headers(client, "stranger@example.com")
    response = await client.get(
        f"/v1/admin/verifications/{submitted['id']}/document", headers=stranger_headers
    )
    assert response.status_code == 403


async def test_non_admin_cannot_review_verification(client):
    owner_headers = await _create_user_headers(client, "owner2@example.com")
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=owner_headers
        )
    ).json()

    response = await client.patch(
        f"/v1/admin/verifications/{submitted['id']}", json={"status": "approved"}, headers=owner_headers
    )
    assert response.status_code == 403


# --- admin review flow ---


async def test_admin_can_list_and_filter_verifications(client):
    headers_a = await _create_user_headers(client, "a@example.com")
    await client.post("/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers_a)

    headers_b = await _create_user_headers(client, "b@example.com")
    submitted_b = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "national_id"}, headers=headers_b
        )
    ).json()

    admin_headers = await _create_admin_headers(client)
    await client.patch(
        f"/v1/admin/verifications/{submitted_b['id']}", json={"status": "approved"}, headers=admin_headers
    )

    all_response = await client.get("/v1/admin/verifications", headers=admin_headers)
    assert len(all_response.json()) == 2

    pending_response = await client.get(
        "/v1/admin/verifications", params={"status": "pending"}, headers=admin_headers
    )
    assert len(pending_response.json()) == 1
    assert pending_response.json()[0]["document_type"] == "passport"


async def test_admin_can_view_submitted_document(client):
    headers = await _create_user_headers(client)
    content = _real_jpeg_bytes()
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(content), data={"document_type": "passport"}, headers=headers
        )
    ).json()

    admin_headers = await _create_admin_headers(client)
    response = await client.get(f"/v1/admin/verifications/{submitted['id']}/document", headers=admin_headers)
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["cache-control"] == "no-store"


async def test_admin_approve_sets_reviewer_and_timestamp(client):
    headers = await _create_user_headers(client)
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
        )
    ).json()

    admin_headers = await _create_admin_headers(client)
    response = await client.patch(
        f"/v1/admin/verifications/{submitted['id']}", json={"status": "approved"}, headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] is not None
    assert body["reviewed_at"] is not None


async def test_admin_reject_requires_reason(client):
    headers = await _create_user_headers(client)
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
        )
    ).json()

    admin_headers = await _create_admin_headers(client)
    response = await client.patch(
        f"/v1/admin/verifications/{submitted['id']}", json={"status": "rejected"}, headers=admin_headers
    )
    assert response.status_code == 422


async def test_cannot_review_an_already_reviewed_verification(client):
    headers = await _create_user_headers(client)
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=headers
        )
    ).json()

    admin_headers = await _create_admin_headers(client)
    await client.patch(
        f"/v1/admin/verifications/{submitted['id']}", json={"status": "approved"}, headers=admin_headers
    )

    response = await client.patch(
        f"/v1/admin/verifications/{submitted['id']}",
        json={"status": "rejected", "rejection_reason": "too late"},
        headers=admin_headers,
    )
    assert response.status_code == 400


async def test_admin_cannot_review_their_own_verification_submission(client):
    admin_headers = await _create_admin_headers(client, "self-reviewer@example.com")
    submitted = (
        await client.post(
            "/v1/verification/me", files=_document_file(), data={"document_type": "passport"}, headers=admin_headers
        )
    ).json()

    response = await client.patch(
        f"/v1/admin/verifications/{submitted['id']}", json={"status": "approved"}, headers=admin_headers
    )
    assert response.status_code == 400


async def test_review_unknown_verification_returns_404(client):
    admin_headers = await _create_admin_headers(client)
    response = await client.patch(
        "/v1/admin/verifications/00000000-0000-0000-0000-000000000000",
        json={"status": "approved"},
        headers=admin_headers,
    )
    assert response.status_code == 404
