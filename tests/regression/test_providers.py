import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.conftest import login, register_user, test_engine


async def _create_provider(client, email="jane@example.com", password="secret123"):
    await register_user(client, email, password=password, role="provider", full_name="Jane Stylist")
    token = await login(client, email, password)
    return {"Authorization": f"Bearer {token}"}


async def _promote_to_admin(email: str) -> None:
    # Matches the real provisioning path (see CLAUDE.md) — no API
    # grants the admin role, only a direct DB update.
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email})


async def test_create_provider_profile_without_token_returns_401(client):
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Salon Co",
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
            "categories": ["hair"],
        },
    )
    assert response.status_code == 401


async def test_create_provider_profile_as_existing_customer_succeeds(client):
    # The "become a provider" path — no separate endpoint, just this
    # same one, now open to any non-admin user (see CLAUDE.md's Roles
    # convention). This used to assert 403; a customer becoming a
    # provider is the intended behavior now, not an error case.
    await register_user(client, "cust@example.com", role="customer")
    token = await login(client, "cust@example.com")
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Salon Co",
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
            "categories": ["hair"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201


async def test_create_provider_profile_as_admin_returns_403(client):
    # Admin and provider are mutually exclusive (see CLAUDE.md) — an
    # admin account can never hold a ProviderProfile.
    await register_user(client, "admin@example.com", role="customer")
    await _promote_to_admin("admin@example.com")
    token = await login(client, "admin@example.com")
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Salon Co",
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
            "categories": ["hair"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_promoting_a_provider_to_admin_is_refused_by_the_db_trigger(client):
    # The other direction of the same exclusivity rule. The app itself
    # already refuses an admin creating a ProviderProfile (the test
    # above); THIS direction has no app code in the loop at all — admin
    # promotion is a direct DB UPDATE, not an API call (see CLAUDE.md)
    # — so it's enforced by a Postgres trigger instead (see
    # alembic/versions/c20b1323c9c1_....py), exercised here the same
    # way the real provisioning path would hit it.
    headers = await _create_provider(client, "provider-to-admin@example.com")
    await client.post(
        "/v1/providers/",
        json={
            "business_name": "Studio",
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
            "categories": ["hair"],
        },
        headers=headers,
    )

    with pytest.raises(DBAPIError):
        await _promote_to_admin("provider-to-admin@example.com")


async def test_create_provider_profile_success(client):
    headers = await _create_provider(client)
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Jane's Hair Studio",
            "bio": "10 years",
            "years_experience": 10,
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
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
        "/v1/providers/",
        json={
            "business_name": "Jane's Studio",
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
            "categories": ["hair", "makeup"],
        },
        headers=headers,
    )
    assert response.status_code == 201
    assert set(response.json()["categories"]) == {"hair", "makeup"}


async def test_create_provider_profile_requires_at_least_one_category(client):
    headers = await _create_provider(client)
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Jane's Studio",
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
            "categories": [],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_create_provider_profile_with_unknown_timezone_returns_422(client):
    headers = await _create_provider(client)
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Jane's Studio",
            "currency": "GBP",
            "timezone": "Not/A_Real_Zone",
            "categories": ["hair"],
        },
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
        "/v1/providers/",
        json={
            "business_name": "First",
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
            "categories": ["hair"],
        },
        headers=headers,
    )
    assert first.status_code == 201

    second = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Second",
            "currency": "GBP",
            "timezone": "Europe/London", "country": "GB",
            "categories": ["nails"],
        },
        headers=headers,
    )
    assert second.status_code == 409


async def test_get_provider_profile_success(client):
    headers = await _create_provider(client)
    created = (
        await client.post(
            "/v1/providers/",
            json={
                "business_name": "Jane's Hair Studio",
                "currency": "GBP",
                "timezone": "Europe/London", "country": "GB",
                "categories": ["hair"],
            },
            headers=headers,
        )
    ).json()

    response = await client.get(f"/v1/providers/{created['id']}")
    assert response.status_code == 200
    assert response.json()["business_name"] == "Jane's Hair Studio"


async def test_get_provider_profile_not_found_returns_404(client):
    response = await client.get("/v1/providers/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
