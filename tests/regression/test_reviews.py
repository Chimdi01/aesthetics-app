from datetime import UTC, datetime, timedelta

from tests.conftest import login, register_user

FUTURE = (datetime.now(UTC) + timedelta(days=1)).isoformat()


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


async def _create_completed_booking(client, provider_headers, customer_headers, profile_id):
    booking = (
        await client.post(
            "/v1/bookings/",
            json={
                "provider_profile_id": profile_id,
                "category": "hair",
                "visit_type": "shop_visit",
                "scheduled_at": FUTURE,
            },
            headers=customer_headers,
        )
    ).json()
    await client.patch(f"/v1/bookings/{booking['id']}/status", json={"status": "confirmed"}, headers=provider_headers)
    await client.patch(f"/v1/bookings/{booking['id']}/status", json={"status": "completed"}, headers=provider_headers)
    return booking


async def test_create_review_on_completed_booking_succeeds(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])

    response = await client.post(
        f"/v1/bookings/{booking['id']}/review",
        json={"rating": 5, "comment": "Amazing cut"},
        headers=customer_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["rating"] == 5
    assert body["comment"] == "Amazing cut"
    assert body["booking_id"] == booking["id"]
    assert body["provider_profile_id"] == profile["id"]


async def test_create_review_without_token_returns_401(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])

    response = await client.post(f"/v1/bookings/{booking['id']}/review", json={"rating": 5})
    assert response.status_code == 401


async def test_create_review_on_unknown_booking_returns_404(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.post(
        "/v1/bookings/00000000-0000-0000-0000-000000000000/review",
        json={"rating": 5},
        headers=customer_headers,
    )
    assert response.status_code == 404


async def test_create_review_by_someone_other_than_the_customer_returns_403(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])

    stranger_headers = await _create_customer_headers(client, "stranger@example.com")
    response = await client.post(
        f"/v1/bookings/{booking['id']}/review", json={"rating": 1}, headers=stranger_headers
    )
    assert response.status_code == 403

    # The provider themself isn't "the customer" either.
    response = await client.post(
        f"/v1/bookings/{booking['id']}/review", json={"rating": 1}, headers=provider_headers
    )
    assert response.status_code == 403


async def test_create_review_on_a_not_yet_completed_booking_returns_400(client):
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

    response = await client.post(
        f"/v1/bookings/{booking['id']}/review", json={"rating": 5}, headers=customer_headers
    )
    assert response.status_code == 400


async def test_cannot_review_the_same_booking_twice(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])

    first = await client.post(
        f"/v1/bookings/{booking['id']}/review", json={"rating": 4}, headers=customer_headers
    )
    assert first.status_code == 201

    second = await client.post(
        f"/v1/bookings/{booking['id']}/review", json={"rating": 2}, headers=customer_headers
    )
    assert second.status_code == 409


async def test_create_review_with_out_of_range_rating_returns_422(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])

    response = await client.post(
        f"/v1/bookings/{booking['id']}/review", json={"rating": 6}, headers=customer_headers
    )
    assert response.status_code == 422


async def test_list_provider_reviews_returns_reviews_for_that_provider_only(client):
    profile_a, provider_a_headers = await _create_provider_with_profile(client, email="jane@example.com")
    profile_b, provider_b_headers = await _create_provider_with_profile(client, email="amy@example.com")
    customer_headers = await _create_customer_headers(client)

    booking_a = await _create_completed_booking(client, provider_a_headers, customer_headers, profile_a["id"])
    await client.post(f"/v1/bookings/{booking_a['id']}/review", json={"rating": 5}, headers=customer_headers)

    booking_b = await _create_completed_booking(client, provider_b_headers, customer_headers, profile_b["id"])
    await client.post(f"/v1/bookings/{booking_b['id']}/review", json={"rating": 2}, headers=customer_headers)

    response = await client.get(f"/v1/providers/{profile_a['id']}/reviews")
    assert response.status_code == 200
    reviews = response.json()
    assert len(reviews) == 1
    assert reviews[0]["rating"] == 5
    assert reviews[0]["provider_profile_id"] == profile_a["id"]


async def test_list_reviews_for_unknown_provider_returns_404(client):
    response = await client.get("/v1/providers/00000000-0000-0000-0000-000000000000/reviews")
    assert response.status_code == 404


async def test_create_review_with_embedded_null_byte_in_comment_returns_422(client):
    profile, provider_headers = await _create_provider_with_profile(client)
    customer_headers = await _create_customer_headers(client)
    booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])

    response = await client.post(
        f"/v1/bookings/{booking['id']}/review",
        json={"rating": 4, "comment": "great\x00cut"},
        headers=customer_headers,
    )
    assert response.status_code == 422


async def test_list_provider_reviews_respects_limit_and_offset(client):
    profile, provider_headers = await _create_provider_with_profile(client)

    # Three different customers each book + complete + review the same
    # provider, since a booking (and therefore a review) can't be reused.
    ratings_newest_first = []
    for i, rating in enumerate([3, 4, 5]):
        customer_headers = await _create_customer_headers(client, f"cust{i}@example.com")
        booking = await _create_completed_booking(client, provider_headers, customer_headers, profile["id"])
        await client.post(
            f"/v1/bookings/{booking['id']}/review", json={"rating": rating}, headers=customer_headers
        )
        ratings_newest_first.insert(0, rating)

    first_page = await client.get(f"/v1/providers/{profile['id']}/reviews", params={"limit": 2, "offset": 0})
    assert first_page.status_code == 200
    assert [r["rating"] for r in first_page.json()] == ratings_newest_first[:2]

    second_page = await client.get(f"/v1/providers/{profile['id']}/reviews", params={"limit": 2, "offset": 2})
    assert second_page.status_code == 200
    assert [r["rating"] for r in second_page.json()] == ratings_newest_first[2:]


async def test_list_provider_reviews_rejects_limit_over_100(client):
    profile, _ = await _create_provider_with_profile(client)
    response = await client.get(f"/v1/providers/{profile['id']}/reviews", params={"limit": 101})
    assert response.status_code == 422
