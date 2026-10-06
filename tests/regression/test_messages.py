from datetime import datetime, timedelta, timezone

from tests.conftest import login, register_user

FUTURE = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()


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


async def _create_booking(client, provider_profile_id, customer_headers):
    response = await client.post(
        "/v1/bookings/",
        json={
            "provider_profile_id": provider_profile_id,
            "category": "hair",
            "visit_type": "shop_visit",
            "scheduled_at": FUTURE,
        },
        headers=customer_headers,
    )
    return response.json()


async def test_customer_can_send_message(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    response = await client.post(
        f"/v1/bookings/{booking['id']}/messages", json={"body": "Hi, see you Friday!"}, headers=customer_headers
    )
    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "Hi, see you Friday!"
    assert body["booking_id"] == booking["id"]


async def test_provider_can_send_message(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    response = await client.post(
        f"/v1/bookings/{booking['id']}/messages", json={"body": "Looking forward to it!"}, headers=provider_headers
    )
    assert response.status_code == 201
    assert response.json()["sender_id"] is not None


async def test_send_message_without_token_returns_401(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    response = await client.post(f"/v1/bookings/{booking['id']}/messages", json={"body": "hi"})
    assert response.status_code == 401


async def test_send_message_by_stranger_returns_403(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    stranger_headers = await _create_customer_headers(client, "stranger@example.com")
    response = await client.post(
        f"/v1/bookings/{booking['id']}/messages", json={"body": "hi"}, headers=stranger_headers
    )
    assert response.status_code == 403


async def test_send_message_to_unknown_booking_returns_404(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.post(
        "/v1/bookings/00000000-0000-0000-0000-000000000000/messages",
        json={"body": "hi"},
        headers=customer_headers,
    )
    assert response.status_code == 404


async def test_send_message_with_blank_body_returns_422(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    response = await client.post(
        f"/v1/bookings/{booking['id']}/messages", json={"body": "   "}, headers=customer_headers
    )
    assert response.status_code == 422


async def test_list_messages_returns_conversation_oldest_first(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    await client.post(f"/v1/bookings/{booking['id']}/messages", json={"body": "first"}, headers=customer_headers)
    await client.post(f"/v1/bookings/{booking['id']}/messages", json={"body": "second"}, headers=provider_headers)
    await client.post(f"/v1/bookings/{booking['id']}/messages", json={"body": "third"}, headers=customer_headers)

    response = await client.get(f"/v1/bookings/{booking['id']}/messages", headers=customer_headers)
    assert response.status_code == 200
    assert [m["body"] for m in response.json()] == ["first", "second", "third"]


async def test_list_messages_visible_to_customer_and_provider_not_stranger(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)
    await client.post(f"/v1/bookings/{booking['id']}/messages", json={"body": "hi"}, headers=customer_headers)

    as_customer = await client.get(f"/v1/bookings/{booking['id']}/messages", headers=customer_headers)
    assert as_customer.status_code == 200

    as_provider = await client.get(f"/v1/bookings/{booking['id']}/messages", headers=provider_headers)
    assert as_provider.status_code == 200

    stranger_headers = await _create_customer_headers(client, "stranger@example.com")
    as_stranger = await client.get(f"/v1/bookings/{booking['id']}/messages", headers=stranger_headers)
    assert as_stranger.status_code == 403


async def test_list_messages_without_token_returns_401(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    response = await client.get(f"/v1/bookings/{booking['id']}/messages")
    assert response.status_code == 401


async def test_list_messages_for_unknown_booking_returns_404(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.get(
        "/v1/bookings/00000000-0000-0000-0000-000000000000/messages", headers=customer_headers
    )
    assert response.status_code == 404


async def test_list_messages_respects_limit_and_offset(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    for body in ["one", "two", "three"]:
        await client.post(f"/v1/bookings/{booking['id']}/messages", json={"body": body}, headers=customer_headers)

    first_page = await client.get(
        f"/v1/bookings/{booking['id']}/messages", params={"limit": 2, "offset": 0}, headers=customer_headers
    )
    second_page = await client.get(
        f"/v1/bookings/{booking['id']}/messages", params={"limit": 2, "offset": 2}, headers=customer_headers
    )
    assert [m["body"] for m in first_page.json()] == ["one", "two"]
    assert [m["body"] for m in second_page.json()] == ["three"]


async def test_list_messages_rejects_limit_over_200(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_booking(client, profile["id"], customer_headers)

    response = await client.get(
        f"/v1/bookings/{booking['id']}/messages", params={"limit": 201}, headers=customer_headers
    )
    assert response.status_code == 422


async def test_messages_are_scoped_to_their_booking(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking_a = await _create_booking(client, profile["id"], customer_headers)
    booking_b = await _create_booking(client, profile["id"], customer_headers)

    await client.post(f"/v1/bookings/{booking_a['id']}/messages", json={"body": "for A"}, headers=customer_headers)
    await client.post(f"/v1/bookings/{booking_b['id']}/messages", json={"body": "for B"}, headers=customer_headers)

    response = await client.get(f"/v1/bookings/{booking_a['id']}/messages", headers=customer_headers)
    assert [m["body"] for m in response.json()] == ["for A"]
