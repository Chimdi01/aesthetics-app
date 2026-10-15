"""
Batch 2 of the error-code migration (docs/backend-slices.md Slice 1
Step 1): every error raised from app/booking_access.py and the bookings,
reviews and messages routers carries its approved error_code, with
`detail` unchanged.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.conftest import login, register_user, test_engine

FUTURE = (datetime.now(UTC) + timedelta(days=1)).isoformat()
PAST = (datetime.now(UTC) - timedelta(days=1)).isoformat()
MISSING_ID = "00000000-0000-0000-0000-000000000000"


async def _headers(client, email):
    await register_user(client, email)
    return {"Authorization": f"Bearer {await login(client, email)}"}


async def _provider(client, email="pro@example.com"):
    headers = await _headers(client, email)
    profile = (
        await client.post(
            "/v1/providers/",
            json={
                "business_name": "Studio",
                "currency": "GBP",
                "timezone": "Europe/London",
                "country": "GB",
                "categories": ["hair"],
            },
            headers=headers,
        )
    ).json()
    return profile, headers


async def _book(client, profile_id, headers, **overrides):
    payload = {
        "provider_profile_id": profile_id,
        "category": "hair",
        "visit_type": "shop_visit",
        "scheduled_at": FUTURE,
        **overrides,
    }
    return await client.post("/v1/bookings/", json=payload, headers=headers)


async def _set_status(client, booking_id, status, headers):
    return await client.patch(f"/v1/bookings/{booking_id}/status", json={"status": status}, headers=headers)


def _without_request_id(response):
    return {k: v for k, v in response.json().items() if k != "request_id"}


def _assert_error(response, status_code, error_code, detail):
    assert response.status_code == status_code
    body = response.json()
    assert body["error_code"] == error_code
    assert body["detail"] == detail


# --- create_booking ---


async def test_booking_unknown_provider_is_not_found(client):
    customer = await _headers(client, "c@example.com")
    response = await _book(client, MISSING_ID, customer)
    _assert_error(response, 404, "not_found", "Provider profile not found")


async def test_booking_deactivated_provider_matches_missing_provider(client):
    profile, _ = await _provider(client)
    customer = await _headers(client, "c@example.com")
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE provider_profiles SET is_active = false WHERE id = :id"), {"id": profile["id"]})
    deactivated = await _book(client, profile["id"], customer)
    missing = await _book(client, MISSING_ID, customer)
    assert deactivated.status_code == missing.status_code == 404
    assert _without_request_id(deactivated) == _without_request_id(missing)


async def test_booking_own_profile_is_cannot_target_self(client):
    profile, provider = await _provider(client)
    response = await _book(client, profile["id"], provider)
    _assert_error(response, 400, "cannot_target_self", "You can't book your own provider profile")


async def test_booking_unoffered_category_is_validation_failed_with_params(client):
    profile, _ = await _provider(client)
    customer = await _headers(client, "c@example.com")
    response = await _book(client, profile["id"], customer, category="nails")
    _assert_error(response, 422, "validation_failed", "This provider does not offer 'nails'")
    body = response.json()
    assert body["params"] == {"category": "nails"}
    assert body["fields"] == [
        {"field": "category", "code": "not_offered", "message": "This provider does not offer 'nails'"}
    ]


async def test_booking_in_the_past_is_validation_failed(client):
    profile, _ = await _provider(client)
    customer = await _headers(client, "c@example.com")
    response = await _book(client, profile["id"], customer, scheduled_at=PAST)
    _assert_error(response, 422, "validation_failed", "scheduled_at must be in the future")
    assert response.json()["fields"] == [
        {"field": "scheduled_at", "code": "must_be_future", "message": "scheduled_at must be in the future"}
    ]


# --- get_booking / authorize_booking_party ---


async def test_get_unknown_booking_is_not_found(client):
    customer = await _headers(client, "c@example.com")
    response = await client.get(f"/v1/bookings/{MISSING_ID}", headers=customer)
    _assert_error(response, 404, "not_found", "Booking not found")


async def test_stranger_on_booking_is_forbidden(client):
    profile, _ = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    stranger = await _headers(client, "s@example.com")
    response = await client.get(f"/v1/bookings/{booking['id']}", headers=stranger)
    _assert_error(response, 403, "forbidden", "Not your booking")


# --- update_booking_status ---


async def test_status_update_unknown_booking_is_not_found(client):
    customer = await _headers(client, "c@example.com")
    response = await _set_status(client, MISSING_ID, "cancelled", customer)
    _assert_error(response, 404, "not_found", "Booking not found")


async def test_customer_confirming_is_forbidden(client):
    profile, _ = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    response = await _set_status(client, booking["id"], "confirmed", customer)
    _assert_error(response, 403, "forbidden", "Only the provider can confirm a booking")


async def test_customer_completing_is_forbidden(client):
    profile, _ = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    response = await _set_status(client, booking["id"], "completed", customer)
    _assert_error(response, 403, "forbidden", "Only the provider can mark a booking completed")


async def test_completing_a_requested_booking_is_invalid_state(client):
    profile, provider = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    response = await _set_status(client, booking["id"], "completed", provider)
    _assert_error(response, 400, "invalid_state", "Only a confirmed booking can be completed")


async def test_confirming_a_confirmed_booking_is_invalid_state(client):
    profile, provider = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    await _set_status(client, booking["id"], "confirmed", provider)
    response = await _set_status(client, booking["id"], "confirmed", provider)
    _assert_error(response, 400, "invalid_state", "Only a requested booking can be confirmed")


async def test_moving_back_to_requested_is_invalid_state(client):
    profile, provider = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    response = await _set_status(client, booking["id"], "requested", provider)
    _assert_error(response, 400, "invalid_state", "Invalid status transition")


async def test_changing_a_cancelled_booking_is_invalid_state_with_params(client):
    profile, _ = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    await _set_status(client, booking["id"], "cancelled", customer)
    response = await _set_status(client, booking["id"], "cancelled", customer)
    _assert_error(response, 400, "invalid_state", "Booking is already cancelled, no further changes allowed")
    assert response.json()["params"] == {"status": "cancelled"}


# --- reviews ---


async def test_review_unknown_booking_is_not_found(client):
    customer = await _headers(client, "c@example.com")
    response = await client.post(f"/v1/bookings/{MISSING_ID}/review", json={"rating": 5}, headers=customer)
    _assert_error(response, 404, "not_found", "Booking not found")


async def test_review_by_provider_is_forbidden(client):
    profile, provider = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    response = await client.post(f"/v1/bookings/{booking['id']}/review", json={"rating": 5}, headers=provider)
    _assert_error(response, 403, "forbidden", "Only the customer on this booking can leave a review")


async def test_review_of_incomplete_booking_is_invalid_state(client):
    profile, _ = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    response = await client.post(f"/v1/bookings/{booking['id']}/review", json={"rating": 5}, headers=customer)
    _assert_error(response, 400, "invalid_state", "Only a completed booking can be reviewed")


async def test_second_review_is_duplicate_resource(client):
    profile, provider = await _provider(client)
    customer = await _headers(client, "c@example.com")
    booking = (await _book(client, profile["id"], customer)).json()
    await _set_status(client, booking["id"], "confirmed", provider)
    await _set_status(client, booking["id"], "completed", provider)
    await client.post(f"/v1/bookings/{booking['id']}/review", json={"rating": 5}, headers=customer)
    response = await client.post(f"/v1/bookings/{booking['id']}/review", json={"rating": 4}, headers=customer)
    _assert_error(response, 409, "duplicate_resource", "This booking has already been reviewed")


async def test_reviews_for_unknown_provider_is_not_found(client):
    response = await client.get(f"/v1/providers/{MISSING_ID}/reviews")
    _assert_error(response, 404, "not_found", "Provider profile not found")


# --- messages ---


async def test_message_on_unknown_booking_is_not_found(client):
    customer = await _headers(client, "c@example.com")
    response = await client.post(f"/v1/bookings/{MISSING_ID}/messages", json={"body": "hi"}, headers=customer)
    _assert_error(response, 404, "not_found", "Booking not found")


async def test_listing_messages_on_unknown_booking_is_not_found(client):
    customer = await _headers(client, "c@example.com")
    response = await client.get(f"/v1/bookings/{MISSING_ID}/messages", headers=customer)
    _assert_error(response, 404, "not_found", "Booking not found")
