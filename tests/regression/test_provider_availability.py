from tests.conftest import login, register_user


async def _create_provider_headers(client, email="jane@example.com"):
    await register_user(client, email, password="secret123", role="provider", full_name="Jane Stylist")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def _create_provider_profile(client, headers, categories=None):
    response = await client.post(
        "/providers/",
        json={"business_name": "Jane's Studio", "categories": categories or ["hair"]},
        headers=headers,
    )
    return response.json()


async def _create_customer_headers(client, email="cust@example.com"):
    await register_user(client, email, password="secret123", role="customer")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def test_set_availability_success(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.put(
        "/providers/me/availability",
        json={"schedule": [{"day_of_week": "monday", "start_time": "09:00", "end_time": "17:00"}]},
        headers=provider_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["day_of_week"] == "monday"
    assert body[0]["start_time"] == "09:00:00"
    assert body[0]["end_time"] == "17:00:00"


async def test_set_availability_supports_split_shifts_on_same_day(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.put(
        "/providers/me/availability",
        json={
            "schedule": [
                {"day_of_week": "monday", "start_time": "09:00", "end_time": "12:00"},
                {"day_of_week": "monday", "start_time": "14:00", "end_time": "18:00"},
            ]
        },
        headers=provider_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert [b["start_time"] for b in body] == ["09:00:00", "14:00:00"]


async def test_set_availability_rejects_overlapping_ranges(client):
    provider_headers = await _create_provider_headers(client)
    await _create_provider_profile(client, provider_headers)

    response = await client.put(
        "/providers/me/availability",
        json={
            "schedule": [
                {"day_of_week": "monday", "start_time": "09:00", "end_time": "13:00"},
                {"day_of_week": "monday", "start_time": "12:00", "end_time": "17:00"},
            ]
        },
        headers=provider_headers,
    )
    assert response.status_code == 422


async def test_set_availability_replaces_previous_schedule(client):
    provider_headers = await _create_provider_headers(client)
    profile = await _create_provider_profile(client, provider_headers)

    await client.put(
        "/providers/me/availability",
        json={"schedule": [{"day_of_week": "monday", "start_time": "09:00", "end_time": "17:00"}]},
        headers=provider_headers,
    )
    response = await client.put(
        "/providers/me/availability",
        json={"schedule": [{"day_of_week": "tuesday", "start_time": "10:00", "end_time": "16:00"}]},
        headers=provider_headers,
    )
    assert response.status_code == 200

    listing = await client.get(f"/providers/{profile['id']}/availability")
    days = [entry["day_of_week"] for entry in listing.json()]
    assert days == ["tuesday"]


async def test_set_availability_without_token_returns_401(client):
    response = await client.put("/providers/me/availability", json={"schedule": []})
    assert response.status_code == 401


async def test_set_availability_as_customer_returns_403(client):
    customer_headers = await _create_customer_headers(client)
    response = await client.put(
        "/providers/me/availability", json={"schedule": []}, headers=customer_headers
    )
    assert response.status_code == 403


async def test_set_availability_without_provider_profile_returns_404(client):
    provider_headers = await _create_provider_headers(client)
    response = await client.put(
        "/providers/me/availability", json={"schedule": []}, headers=provider_headers
    )
    assert response.status_code == 404


async def test_get_availability_is_public_and_sorted(client):
    provider_headers = await _create_provider_headers(client)
    profile = await _create_provider_profile(client, provider_headers)
    await client.put(
        "/providers/me/availability",
        json={
            "schedule": [
                {"day_of_week": "friday", "start_time": "09:00", "end_time": "17:00"},
                {"day_of_week": "monday", "start_time": "09:00", "end_time": "12:00"},
                {"day_of_week": "monday", "start_time": "14:00", "end_time": "18:00"},
            ]
        },
        headers=provider_headers,
    )

    response = await client.get(f"/providers/{profile['id']}/availability")
    assert response.status_code == 200
    days_and_starts = [(e["day_of_week"], e["start_time"]) for e in response.json()]
    assert days_and_starts == [
        ("monday", "09:00:00"),
        ("monday", "14:00:00"),
        ("friday", "09:00:00"),
    ]


async def test_get_availability_for_unknown_provider_returns_404(client):
    response = await client.get("/providers/00000000-0000-0000-0000-000000000000/availability")
    assert response.status_code == 404


async def test_get_availability_scoped_to_the_right_provider(client):
    provider_a_headers = await _create_provider_headers(client, "jane@example.com")
    profile_a = await _create_provider_profile(client, provider_a_headers)
    await client.put(
        "/providers/me/availability",
        json={"schedule": [{"day_of_week": "monday", "start_time": "09:00", "end_time": "17:00"}]},
        headers=provider_a_headers,
    )

    provider_b_headers = await _create_provider_headers(client, "amy@example.com")
    await _create_provider_profile(client, provider_b_headers, categories=["nails"])
    await client.put(
        "/providers/me/availability",
        json={"schedule": [{"day_of_week": "tuesday", "start_time": "10:00", "end_time": "16:00"}]},
        headers=provider_b_headers,
    )

    response = await client.get(f"/providers/{profile_a['id']}/availability")
    days = [entry["day_of_week"] for entry in response.json()]
    assert days == ["monday"]
