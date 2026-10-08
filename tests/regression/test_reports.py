from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from tests.conftest import login, register_user, test_engine

FUTURE = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


async def _create_user(client, email, role="customer"):
    response = await register_user(client, email, password="secret123", role=role)
    token = await login(client, email, "secret123")
    return response.json(), {"Authorization": f"Bearer {token}"}


async def _create_provider_profile(client, headers, categories=None, with_location=False):
    payload = {"business_name": "Jane's Studio", "categories": categories or ["hair"]}
    if with_location:
        payload.update({"latitude": 51.5074, "longitude": -0.1278, "address_type": "shop"})
    response = await client.post("/v1/providers/", json=payload, headers=headers)
    return response.json()


async def _promote_to_admin(email: str) -> None:
    # Matches the real provisioning path (see CLAUDE.md) — no API grants
    # the admin role, only a direct DB update.
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email})


async def _create_admin_headers(client, email="admin@example.com"):
    await register_user(client, email, password="secret123", role="customer")
    await _promote_to_admin(email)
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


# --- reporting is two-way: both a provider and a customer can be reported ---


async def test_report_a_provider(client):
    provider_user, provider_headers = await _create_user(client, "jane@example.com", role="provider")
    await _create_provider_profile(client, provider_headers)
    _, customer_headers = await _create_user(client, "cust@example.com")

    response = await client.post(
        f"/v1/users/{provider_user['id']}/report",
        json={"reason": "safety_concern", "details": "Felt unsafe during the appointment"},
        headers=customer_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["reported_user_id"] == provider_user["id"]


async def test_report_a_customer(client):
    # The point of the redesign: a provider can report a customer too,
    # not just the other way around.
    provider_user, provider_headers = await _create_user(client, "jane2@example.com", role="provider")
    await _create_provider_profile(client, provider_headers)
    customer_user, _ = await _create_user(client, "badcust@example.com")

    response = await client.post(
        f"/v1/users/{customer_user['id']}/report",
        json={"reason": "fraud_or_scam", "details": "No-showed and disputed the charge"},
        headers=provider_headers,
    )
    assert response.status_code == 201
    assert response.json()["reported_user_id"] == customer_user["id"]


async def test_report_without_token_returns_401(client):
    other_user, _ = await _create_user(client, "target@example.com")
    response = await client.post(f"/v1/users/{other_user['id']}/report", json={"reason": "spam"})
    assert response.status_code == 401


async def test_report_unknown_user_returns_404(client):
    _, headers = await _create_user(client, "reporter@example.com")
    response = await client.post(
        "/v1/users/00000000-0000-0000-0000-000000000000/report", json={"reason": "spam"}, headers=headers
    )
    assert response.status_code == 404


async def test_cannot_report_yourself(client):
    user, headers = await _create_user(client, "self@example.com")
    response = await client.post(f"/v1/users/{user['id']}/report", json={"reason": "spam"}, headers=headers)
    assert response.status_code == 400


# --- admin authorization boundaries ---


async def test_non_admin_cannot_list_reports(client):
    _, headers = await _create_user(client, "cust@example.com")
    response = await client.get("/v1/admin/reports", headers=headers)
    assert response.status_code == 403


async def test_non_admin_cannot_review_report(client):
    target_user, _ = await _create_user(client, "target2@example.com")
    _, reporter_headers = await _create_user(client, "reporter2@example.com")
    report = (
        await client.post(
            f"/v1/users/{target_user['id']}/report", json={"reason": "spam"}, headers=reporter_headers
        )
    ).json()

    response = await client.patch(
        f"/v1/admin/reports/{report['id']}", json={"status": "dismissed"}, headers=reporter_headers
    )
    assert response.status_code == 403


async def test_non_admin_cannot_set_provider_active_status(client):
    _, provider_headers = await _create_user(client, "jane3@example.com", role="provider")
    profile = await _create_provider_profile(client, provider_headers)

    response = await client.patch(
        f"/v1/admin/providers/{profile['id']}/status", json={"is_active": False}, headers=provider_headers
    )
    assert response.status_code == 403


async def test_non_admin_cannot_set_user_active_status(client):
    target_user, _ = await _create_user(client, "target3@example.com")
    _, other_headers = await _create_user(client, "other@example.com")

    response = await client.patch(
        f"/v1/admin/users/{target_user['id']}/status", json={"is_active": False}, headers=other_headers
    )
    assert response.status_code == 403


# --- admin report review ---


async def test_admin_can_list_and_filter_reports(client):
    target_a, _ = await _create_user(client, "targetA@example.com")
    target_b, _ = await _create_user(client, "targetB@example.com")
    _, reporter_headers = await _create_user(client, "reporter3@example.com")

    report_a = (
        await client.post(f"/v1/users/{target_a['id']}/report", json={"reason": "spam"}, headers=reporter_headers)
    ).json()
    await client.post(f"/v1/users/{target_b['id']}/report", json={"reason": "fraud_or_scam"}, headers=reporter_headers)

    admin_headers = await _create_admin_headers(client)
    await client.patch(f"/v1/admin/reports/{report_a['id']}", json={"status": "dismissed"}, headers=admin_headers)

    all_reports = await client.get("/v1/admin/reports", headers=admin_headers)
    assert len(all_reports.json()) == 2

    pending_only = await client.get("/v1/admin/reports", params={"status": "pending"}, headers=admin_headers)
    assert len(pending_only.json()) == 1
    assert pending_only.json()[0]["reason"] == "fraud_or_scam"


async def test_admin_resolve_sets_resolver_and_timestamp(client):
    target_user, _ = await _create_user(client, "target4@example.com")
    _, reporter_headers = await _create_user(client, "reporter4@example.com")
    report = (
        await client.post(f"/v1/users/{target_user['id']}/report", json={"reason": "spam"}, headers=reporter_headers)
    ).json()

    admin_headers = await _create_admin_headers(client)
    response = await client.patch(
        f"/v1/admin/reports/{report['id']}", json={"status": "resolved"}, headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolved_by"] is not None
    assert body["resolved_at"] is not None


async def test_cannot_review_an_already_reviewed_report(client):
    target_user, _ = await _create_user(client, "target5@example.com")
    _, reporter_headers = await _create_user(client, "reporter5@example.com")
    report = (
        await client.post(f"/v1/users/{target_user['id']}/report", json={"reason": "spam"}, headers=reporter_headers)
    ).json()

    admin_headers = await _create_admin_headers(client)
    await client.patch(f"/v1/admin/reports/{report['id']}", json={"status": "dismissed"}, headers=admin_headers)

    response = await client.patch(
        f"/v1/admin/reports/{report['id']}", json={"status": "resolved"}, headers=admin_headers
    )
    assert response.status_code == 400


async def test_admin_cannot_review_a_report_filed_against_themselves(client):
    # Promoting after the token is issued is fine — the token only
    # encodes the user id (see app/security.py); role is re-checked
    # fresh from the DB on every request, no re-login needed.
    admin_user, admin_headers = await _create_user(client, "self-admin@example.com")
    await _promote_to_admin("self-admin@example.com")

    _, reporter_headers = await _create_user(client, "reporter6@example.com")
    report = (
        await client.post(
            f"/v1/users/{admin_user['id']}/report", json={"reason": "spam"}, headers=reporter_headers
        )
    ).json()

    response = await client.patch(
        f"/v1/admin/reports/{report['id']}", json={"status": "dismissed"}, headers=admin_headers
    )
    assert response.status_code == 400


async def test_review_unknown_report_returns_404(client):
    admin_headers = await _create_admin_headers(client)
    response = await client.patch(
        "/v1/admin/reports/00000000-0000-0000-0000-000000000000",
        json={"status": "resolved"},
        headers=admin_headers,
    )
    assert response.status_code == 404


# --- ProviderProfile.is_active: hides the business listing, account still usable ---


async def test_admin_can_deactivate_and_reactivate_provider_profile(client):
    _, provider_headers = await _create_user(client, "jane4@example.com", role="provider")
    profile = await _create_provider_profile(client, provider_headers)
    admin_headers = await _create_admin_headers(client)

    deactivated = await client.patch(
        f"/v1/admin/providers/{profile['id']}/status", json={"is_active": False}, headers=admin_headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    reactivated = await client.patch(
        f"/v1/admin/providers/{profile['id']}/status", json={"is_active": True}, headers=admin_headers
    )
    assert reactivated.json()["is_active"] is True


async def test_set_provider_active_status_for_unknown_profile_returns_404(client):
    admin_headers = await _create_admin_headers(client)
    response = await client.patch(
        "/v1/admin/providers/00000000-0000-0000-0000-000000000000/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_deactivated_provider_profile_is_excluded_from_search(client):
    _, provider_headers = await _create_user(client, "jane5@example.com", role="provider")
    profile = await _create_provider_profile(client, provider_headers, with_location=True)
    admin_headers = await _create_admin_headers(client)

    search_before = await client.get("/v1/providers/search", params={"latitude": 51.5074, "longitude": -0.1278})
    assert len(search_before.json()) == 1

    await client.patch(
        f"/v1/admin/providers/{profile['id']}/status", json={"is_active": False}, headers=admin_headers
    )

    search_after = await client.get("/v1/providers/search", params={"latitude": 51.5074, "longitude": -0.1278})
    assert search_after.json() == []


async def test_deactivated_provider_profile_still_viewable_directly_by_id(client):
    _, provider_headers = await _create_user(client, "jane6@example.com", role="provider")
    profile = await _create_provider_profile(client, provider_headers)
    admin_headers = await _create_admin_headers(client)

    await client.patch(
        f"/v1/admin/providers/{profile['id']}/status", json={"is_active": False}, headers=admin_headers
    )

    response = await client.get(f"/v1/providers/{profile['id']}")
    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_cannot_create_booking_against_a_deactivated_provider_profile(client):
    _, provider_headers = await _create_user(client, "jane7@example.com", role="provider")
    profile = await _create_provider_profile(client, provider_headers)
    admin_headers = await _create_admin_headers(client)
    _, customer_headers = await _create_user(client, "cust2@example.com")

    await client.patch(
        f"/v1/admin/providers/{profile['id']}/status", json={"is_active": False}, headers=admin_headers
    )

    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
        headers=customer_headers,
    )
    assert response.status_code == 404


async def test_deactivated_provider_profile_still_usable_for_account_access(client):
    # The distinction this whole redesign is about: deactivating the
    # PROFILE must not touch the ACCOUNT. The provider can still log in.
    _, provider_headers = await _create_user(client, "jane8@example.com", role="provider")
    profile = await _create_provider_profile(client, provider_headers)
    admin_headers = await _create_admin_headers(client)

    await client.patch(
        f"/v1/admin/providers/{profile['id']}/status", json={"is_active": False}, headers=admin_headers
    )

    response = await client.post("/v1/auth/login", data={"username": "jane8@example.com", "password": "secret123"})
    assert response.status_code == 200


# --- User.is_active: cuts off the account entirely, either role ---


async def test_admin_can_deactivate_and_reactivate_a_user_account(client):
    target_user, _ = await _create_user(client, "target6@example.com")
    admin_headers = await _create_admin_headers(client)

    deactivated = await client.patch(
        f"/v1/admin/users/{target_user['id']}/status", json={"is_active": False}, headers=admin_headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    reactivated = await client.patch(
        f"/v1/admin/users/{target_user['id']}/status", json={"is_active": True}, headers=admin_headers
    )
    assert reactivated.json()["is_active"] is True


async def test_admin_cannot_deactivate_their_own_account(client):
    admin_user, admin_headers = await _create_user(client, "self-deactivate@example.com")
    await _promote_to_admin("self-deactivate@example.com")

    response = await client.patch(
        f"/v1/admin/users/{admin_user['id']}/status", json={"is_active": False}, headers=admin_headers
    )
    assert response.status_code == 400


async def test_set_user_active_status_for_unknown_user_returns_404(client):
    admin_headers = await _create_admin_headers(client)
    response = await client.patch(
        "/v1/admin/users/00000000-0000-0000-0000-000000000000/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert response.status_code == 404


async def test_deactivated_account_cannot_log_in(client):
    target_user, _ = await _create_user(client, "target7@example.com")
    admin_headers = await _create_admin_headers(client)

    await client.patch(
        f"/v1/admin/users/{target_user['id']}/status", json={"is_active": False}, headers=admin_headers
    )

    login_response = await client.post(
        "/v1/auth/login", data={"username": "target7@example.com", "password": "secret123"}
    )
    assert login_response.status_code == 403


async def test_existing_token_stops_working_after_deactivation(client):
    target_user, target_headers = await _create_user(client, "target8@example.com")
    admin_headers = await _create_admin_headers(client)

    # GET /v1/users/{id} is intentionally public (no auth at all), so it
    # can't be used to prove a TOKEN stopped working — use an endpoint
    # that actually depends on get_current_user instead.
    pre_check = await client.get("/v1/bookings/as-customer", headers=target_headers)
    assert pre_check.status_code == 200

    await client.patch(
        f"/v1/admin/users/{target_user['id']}/status", json={"is_active": False}, headers=admin_headers
    )

    post_check = await client.get("/v1/bookings/as-customer", headers=target_headers)
    assert post_check.status_code == 403


async def test_deactivating_a_provider_account_cascades_to_their_profile(client):
    provider_user, provider_headers = await _create_user(client, "jane9@example.com", role="provider")
    profile = await _create_provider_profile(client, provider_headers)
    admin_headers = await _create_admin_headers(client)

    await client.patch(
        f"/v1/admin/users/{provider_user['id']}/status", json={"is_active": False}, headers=admin_headers
    )

    profile_check = await client.get(f"/v1/providers/{profile['id']}")
    assert profile_check.json()["is_active"] is False


async def test_reactivating_account_does_not_cascade_reactivate_profile(client):
    provider_user, provider_headers = await _create_user(client, "jane10@example.com", role="provider")
    profile = await _create_provider_profile(client, provider_headers)
    admin_headers = await _create_admin_headers(client)

    await client.patch(
        f"/v1/admin/users/{provider_user['id']}/status", json={"is_active": False}, headers=admin_headers
    )
    await client.patch(
        f"/v1/admin/users/{provider_user['id']}/status", json={"is_active": True}, headers=admin_headers
    )

    profile_check = await client.get(f"/v1/providers/{profile['id']}")
    assert profile_check.json()["is_active"] is False
