from datetime import UTC, datetime, timedelta

from tests.conftest import login, register_user

FUTURE = (datetime.now(UTC) + timedelta(days=1)).isoformat()
PAST = (datetime.now(UTC) - timedelta(days=1)).isoformat()


async def _create_provider_with_profile(client, email="jane@example.com", categories=None):
    await register_user(client, email, password="secret123", role="provider", full_name="Jane Stylist")
    token = await login(client, email, "secret123")
    headers = {"Authorization": f"Bearer {token}"}
    profile = (
        await client.post(
            "/v1/providers/",
            json={"business_name": "Jane's Studio", "categories": categories or ["hair"]},
            headers=headers,
        )
    ).json()
    return profile, headers


async def _create_customer_headers(client, email="cust@example.com"):
    await register_user(client, email, password="secret123", role="customer")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def test_create_booking_success(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)

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
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "requested"
    assert body["provider_profile_id"] == profile["id"]


async def test_create_booking_without_token_returns_401(client):
    profile, _ = await _create_provider_with_profile(client)
    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
    )
    assert response.status_code == 401


async def test_create_booking_for_unoffered_category_returns_400(client):
    # Provider only does hair — booking them for nails must fail, not
    # silently succeed with a category they don't actually offer.
    profile, _ = await _create_provider_with_profile(client, categories=["hair"])
    customer_headers = await _create_customer_headers(client)

    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "nails",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
        headers=customer_headers,
    )
    assert response.status_code == 400


async def test_create_booking_for_unknown_provider_returns_404(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": "00000000-0000-0000-0000-000000000000",
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
        headers=customer_headers,
    )
    assert response.status_code == 404


async def test_provider_cannot_book_their_own_profile(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
        headers=provider_headers,
    )
    assert response.status_code == 400


async def test_create_booking_in_the_past_returns_400(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": PAST,
        },
        headers=customer_headers,
    )
    assert response.status_code == 400


async def test_create_house_call_booking_without_address_returns_422(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "house_call",
            "scheduled_at": FUTURE,
        },
        headers=customer_headers,
    )
    assert response.status_code == 422


async def test_create_house_call_booking_with_address_succeeds(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "house_call",
            "address": "123 Main St",
            "scheduled_at": FUTURE,
        },
        headers=customer_headers,
    )
    assert response.status_code == 201
    assert response.json()["address"] == "123 Main St"


async def test_get_booking_visible_to_customer_and_provider_not_to_stranger(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = (
        await client.post(
            "/v1/bookings/",
            json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
            headers=customer_headers,
        )
    ).json()

    as_customer = await client.get(f"/v1/bookings/{booking['id']}", headers=customer_headers)
    assert as_customer.status_code == 200

    as_provider = await client.get(f"/v1/bookings/{booking['id']}", headers=provider_headers)
    assert as_provider.status_code == 200

    stranger_headers = await _create_customer_headers(client, "stranger@example.com")
    as_stranger = await client.get(f"/v1/bookings/{booking['id']}", headers=stranger_headers)
    assert as_stranger.status_code == 403


async def test_get_booking_not_found_returns_404(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.get("/v1/bookings/00000000-0000-0000-0000-000000000000", headers=customer_headers)
    assert response.status_code == 404


async def test_list_as_customer_route_is_not_swallowed_by_booking_id_route(client):
    # Regression guard for the route-ordering gotcha documented at the top
    # of app/routers/bookings.py: if /{booking_id} were registered before
    # /as-customer, this request would try (and fail) UUID conversion on
    # the literal string "as-customer" and return 422 instead of a list.
    customer_headers = await _create_customer_headers(client)
    response = await client.get("/v1/bookings/as-customer", headers=customer_headers)
    assert response.status_code == 200
    assert response.json() == []


async def test_list_as_customer_returns_only_own_bookings(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client, "cust1@example.com")
    other_customer_headers = await _create_customer_headers(client, "cust2@example.com")

    await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
        headers=customer_headers,
    )
    await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
        headers=other_customer_headers,
    )

    response = await client.get("/v1/bookings/as-customer", headers=customer_headers)
    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_list_as_provider_without_profile_returns_404(client):
    await register_user(client, "noprof@example.com", password="secret123", role="provider")
    token = await login(client, "noprof@example.com", "secret123")
    response = await client.get("/v1/bookings/as-provider", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404


async def test_list_as_provider_as_customer_role_returns_403(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.get("/v1/bookings/as-provider", headers=customer_headers)
    assert response.status_code == 403


async def test_provider_can_confirm_then_complete_booking(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = (
        await client.post(
            "/v1/bookings/",
            json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
            headers=customer_headers,
        )
    ).json()

    confirmed = await client.patch(
        f"/v1/bookings/{booking['id']}/status", json={"status": "confirmed"}, headers=provider_headers
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    completed = await client.patch(
        f"/v1/bookings/{booking['id']}/status", json={"status": "completed"}, headers=provider_headers
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


async def test_customer_cannot_confirm_booking(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = (
        await client.post(
            "/v1/bookings/",
            json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
            headers=customer_headers,
        )
    ).json()

    response = await client.patch(
        f"/v1/bookings/{booking['id']}/status", json={"status": "confirmed"}, headers=customer_headers
    )
    assert response.status_code == 403


async def test_cannot_complete_a_booking_that_was_never_confirmed(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = (
        await client.post(
            "/v1/bookings/",
            json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
            headers=customer_headers,
        )
    ).json()

    response = await client.patch(
        f"/v1/bookings/{booking['id']}/status", json={"status": "completed"}, headers=provider_headers
    )
    assert response.status_code == 400


async def test_customer_can_cancel_a_requested_booking(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = (
        await client.post(
            "/v1/bookings/",
            json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
            headers=customer_headers,
        )
    ).json()

    response = await client.patch(
        f"/v1/bookings/{booking['id']}/status", json={"status": "cancelled"}, headers=customer_headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


async def test_cannot_change_status_of_a_cancelled_booking(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = (
        await client.post(
            "/v1/bookings/",
            json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
            headers=customer_headers,
        )
    ).json()
    await client.patch(f"/v1/bookings/{booking['id']}/status", json={"status": "cancelled"}, headers=customer_headers)

    response = await client.patch(
        f"/v1/bookings/{booking['id']}/status", json={"status": "confirmed"}, headers=customer_headers
    )
    assert response.status_code == 400


async def test_stranger_cannot_update_booking_status(client):
    profile, _ = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = (
        await client.post(
            "/v1/bookings/",
            json={
            "provider_profile_id": profile["id"],
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
            headers=customer_headers,
        )
    ).json()

    stranger_headers = await _create_customer_headers(client, "stranger@example.com")
    response = await client.patch(
        f"/v1/bookings/{booking['id']}/status", json={"status": "cancelled"}, headers=stranger_headers
    )
    assert response.status_code == 403
