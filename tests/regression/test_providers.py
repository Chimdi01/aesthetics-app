from tests.conftest import login, register_user


async def _create_provider(client, email="jane@example.com", password="secret123"):
    await register_user(client, email, password=password, role="provider", full_name="Jane Stylist")
    token = await login(client, email, password)
    return {"Authorization": f"Bearer {token}"}


async def test_create_provider_profile_without_token_returns_401(client):
    response = await client.post("/providers/", json={"business_name": "Salon Co", "categories": ["hair"]})
    assert response.status_code == 401


async def test_create_provider_profile_as_customer_returns_403(client):
    await register_user(client, "cust@example.com", role="customer")
    token = await login(client, "cust@example.com")
    response = await client.post(
        "/providers/",
        json={"business_name": "Salon Co", "categories": ["hair"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_create_provider_profile_success(client):
    headers = await _create_provider(client)
    response = await client.post(
        "/providers/",
        json={
            "business_name": "Jane's Hair Studio",
            "bio": "10 years",
            "years_experience": 10,
            "categories": ["hair"],
        },
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["business_name"] == "Jane's Hair Studio"
    assert body["years_experience"] == 10
    assert body["categories"] == ["hair"]


async def test_create_provider_profile_with_multiple_categories(client):
    # The actual point of the categories field: a provider who does more
    # than one thing (e.g. hair AND makeup) needs a single profile that
    # reflects both, not a forced choice of one.
    headers = await _create_provider(client)
    response = await client.post(
        "/providers/",
        json={"business_name": "Jane's Studio", "categories": ["hair", "makeup"]},
        headers=headers,
    )
    assert response.status_code == 201
    assert set(response.json()["categories"]) == {"hair", "makeup"}


async def test_create_provider_profile_requires_at_least_one_category(client):
    headers = await _create_provider(client)
    response = await client.post(
        "/providers/",
        json={"business_name": "Jane's Studio", "categories": []},
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_duplicate_provider_profile_returns_409_not_500(client):
    # Regression guard: the endpoint used to check for an existing profile
    # via `user.provider_profile` (a lazy-loaded relationship) after an
    # `await db.get(...)` call had already returned. Accessing a lazy
    # relationship outside that await raises MissingGreenlet in async
    # SQLAlchemy, turning this into a 500 instead of a clean 409. Fixed by
    # querying explicitly instead of touching the relationship attribute.
    headers = await _create_provider(client)
    first = await client.post(
        "/providers/", json={"business_name": "First", "categories": ["hair"]}, headers=headers
    )
    assert first.status_code == 201

    second = await client.post(
        "/providers/", json={"business_name": "Second", "categories": ["nails"]}, headers=headers
    )
    assert second.status_code == 409


async def test_get_provider_profile_success(client):
    headers = await _create_provider(client)
    created = (
        await client.post(
            "/providers/", json={"business_name": "Jane's Hair Studio", "categories": ["hair"]}, headers=headers
        )
    ).json()

    response = await client.get(f"/providers/{created['id']}")
    assert response.status_code == 200
    assert response.json()["business_name"] == "Jane's Hair Studio"


async def test_get_provider_profile_not_found_returns_404(client):
    response = await client.get("/providers/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
