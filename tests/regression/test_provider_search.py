from datetime import UTC, datetime, timedelta

from tests.conftest import login, register_user

FUTURE = (datetime.now(UTC) + timedelta(days=1)).isoformat()

# Search origin: central London.
ORIGIN = {"latitude": 51.5074, "longitude": -0.1278}
CAMDEN = (51.5390, -0.1426)  # ~3.7 km from origin
CROYDON = (51.3762, -0.0982)  # ~15 km from origin
MANCHESTER = (53.4808, -2.2426)  # ~260 km from origin


async def _create_provider(client, email, name="Studio", categories=None, location=None, address_type="shop"):
    await register_user(client, email, password="secret123", role="provider", full_name=name)
    token = await login(client, email, "secret123")
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"business_name": name, "categories": categories or ["hair"]}
    if location:
        payload.update({"latitude": location[0], "longitude": location[1], "address_type": address_type})
    response = await client.post("/v1/providers/", json=payload, headers=headers)
    return response.json(), headers


async def _create_customer_headers(client, email="cust@example.com"):
    await register_user(client, email, password="secret123", role="customer")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def test_create_profile_with_location_hides_exact_coordinates(client):
    profile, _ = await _create_provider(client, "a@example.com", location=CAMDEN, address_type="home")
    assert profile["address_type"] == "home"
    # A home provider's coordinates are effectively their home address.
    assert "latitude" not in profile and "longitude" not in profile and "location" not in profile


async def test_create_profile_with_partial_location_returns_422(client):
    await register_user(client, "a@example.com", password="secret123", role="provider")
    token = await login(client, "a@example.com", "secret123")
    response = await client.post(
        "/v1/providers/",
        json={"business_name": "X", "categories": ["hair"], "latitude": 51.5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_search_route_is_not_swallowed_by_profile_id_route(client):
    # Route-ordering guard (see the note in app/routers/providers.py): if
    # /{profile_id} were registered first, "search" would fail UUID
    # conversion and this would return 422 instead of an empty list.
    response = await client.get("/v1/providers/search", params=ORIGIN)
    assert response.status_code == 200
    assert response.json() == []


async def test_search_returns_nearby_providers_sorted_by_distance(client):
    await _create_provider(client, "far@example.com", name="Croydon", location=CROYDON)
    await _create_provider(client, "near@example.com", name="Camden", location=CAMDEN)

    response = await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 20})
    assert response.status_code == 200
    results = response.json()
    assert [r["business_name"] for r in results] == ["Camden", "Croydon"]
    assert 3.0 <= results[0]["distance_km"] <= 4.5
    assert 14.0 <= results[1]["distance_km"] <= 16.5


async def test_search_excludes_providers_outside_radius(client):
    await _create_provider(client, "near@example.com", name="Camden", location=CAMDEN)
    await _create_provider(client, "far@example.com", name="Manchester", location=MANCHESTER)

    response = await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 50})
    assert [r["business_name"] for r in response.json()] == ["Camden"]


async def test_search_excludes_providers_without_a_location(client):
    await _create_provider(client, "noloc@example.com", name="No Location")
    await _create_provider(client, "near@example.com", name="Camden", location=CAMDEN)

    response = await client.get("/v1/providers/search", params=ORIGIN)
    assert [r["business_name"] for r in response.json()] == ["Camden"]


async def test_search_filters_by_category(client):
    await _create_provider(client, "hair@example.com", name="Hair Pro", categories=["hair"], location=CAMDEN)
    await _create_provider(
        client, "multi@example.com", name="Hair And Nails", categories=["hair", "nails"], location=CROYDON
    )

    nails = await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 20, "category": "nails"})
    assert [r["business_name"] for r in nails.json()] == ["Hair And Nails"]

    hair = await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 20, "category": "hair"})
    assert len(hair.json()) == 2


async def test_search_results_do_not_expose_coordinates(client):
    await _create_provider(client, "near@example.com", location=CAMDEN, address_type="home")
    result = (await client.get("/v1/providers/search", params=ORIGIN)).json()[0]
    assert result["address_type"] == "home"
    assert not {"latitude", "longitude", "location"} & result.keys()


async def test_search_includes_average_rating_and_review_count(client):
    profile, provider_headers = await _create_provider(client, "rated@example.com", name="Rated", location=CAMDEN)
    await _create_provider(client, "unrated@example.com", name="Unrated", location=CROYDON)

    for i, rating in enumerate([5, 4]):
        customer_headers = await _create_customer_headers(client, f"cust{i}@example.com")
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
        for status in ("confirmed", "completed"):
            await client.patch(
                f"/v1/bookings/{booking['id']}/status", json={"status": status}, headers=provider_headers
            )
        await client.post(f"/v1/bookings/{booking['id']}/review", json={"rating": rating}, headers=customer_headers)

    results = (await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 20})).json()
    rated, unrated = results[0], results[1]
    assert rated["business_name"] == "Rated"
    assert rated["average_rating"] == 4.5
    assert rated["review_count"] == 2
    assert unrated["average_rating"] is None
    assert unrated["review_count"] == 0


async def test_search_respects_limit_and_offset(client):
    await _create_provider(client, "a@example.com", name="Camden", location=CAMDEN)
    await _create_provider(client, "b@example.com", name="Croydon", location=CROYDON)

    first = await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 20, "limit": 1})
    second = await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 20, "limit": 1, "offset": 1})
    assert [r["business_name"] for r in first.json()] == ["Camden"]
    assert [r["business_name"] for r in second.json()] == ["Croydon"]


async def test_search_rejects_invalid_parameters(client):
    assert (await client.get("/v1/providers/search")).status_code == 422  # origin is required
    assert (await client.get("/v1/providers/search", params={"latitude": 91, "longitude": 0})).status_code == 422
    assert (await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 51})).status_code == 422
    assert (await client.get("/v1/providers/search", params={**ORIGIN, "radius_km": 0})).status_code == 422
    assert (await client.get("/v1/providers/search", params={**ORIGIN, "limit": 101})).status_code == 422
    assert (await client.get("/v1/providers/search", params={**ORIGIN, "category": "bogus"})).status_code == 422
