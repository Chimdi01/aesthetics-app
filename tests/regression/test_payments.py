"""
The payments skeleton: a provider's payout account is staged
automatically at profile creation (app/routers/providers.py), already
pointed at the right processor for their country, and the webhook
receipt endpoint (app/routers/payment_webhooks.py) deliberately 501s
rather than process anything — no real Stripe/Flutterwave keys exist
yet (see CLAUDE.md).
"""
from tests.conftest import login, register_user


async def _create_provider_headers(client, email="jane@example.com"):
    await register_user(client, email, password="secret123", role="provider", full_name="Jane Stylist")
    token = await login(client, email, "secret123")
    return {"Authorization": f"Bearer {token}"}


async def _create_provider_profile(client, headers, country="GB", currency="GBP", timezone="Europe/London"):
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Jane's Studio",
            "currency": currency,
            "timezone": timezone,
            "country": country,
            "categories": ["hair"],
        },
        headers=headers,
    )
    return response.json()


async def test_creating_a_uk_provider_profile_stages_a_stripe_payout_account(client):
    headers = await _create_provider_headers(client, "uk-provider@example.com")
    await _create_provider_profile(client, headers, country="GB", currency="GBP", timezone="Europe/London")

    response = await client.get("/v1/providers/me/payout-account", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["payment_provider"] == "stripe"
    assert body["status"] == "pending"
    assert body["external_account_id"] is None


async def test_creating_a_nigerian_provider_profile_stages_a_flutterwave_payout_account(client):
    headers = await _create_provider_headers(client, "ng-provider@example.com")
    await _create_provider_profile(client, headers, country="NG", currency="NGN", timezone="Africa/Lagos")

    response = await client.get("/v1/providers/me/payout-account", headers=headers)
    assert response.status_code == 200
    assert response.json()["payment_provider"] == "flutterwave"


async def test_get_my_payout_account_without_token_returns_401(client):
    response = await client.get("/v1/providers/me/payout-account")
    assert response.status_code == 401


async def test_get_my_payout_account_without_a_provider_profile_returns_404(client):
    await register_user(client, "noprofile@example.com", password="secret123", role="provider")
    token = await login(client, "noprofile@example.com", "secret123")
    response = await client.get(
        "/v1/providers/me/payout-account", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


async def test_create_provider_profile_rejects_an_unconfigured_country(client):
    headers = await _create_provider_headers(client, "badcountry@example.com")
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "Jane's Studio",
            "currency": "GBP",
            "timezone": "Europe/London",
            "country": "US",
            "categories": ["hair"],
        },
        headers=headers,
    )
    assert response.status_code == 422


# --- webhook receipt skeleton (POST /v1/payments/webhooks/{provider}) ---


async def test_stripe_webhook_returns_501_not_implemented(client):
    response = await client.post("/v1/payments/webhooks/stripe", json={"anything": "goes"})
    assert response.status_code == 501


async def test_flutterwave_webhook_returns_501_not_implemented(client):
    response = await client.post("/v1/payments/webhooks/flutterwave", json={"anything": "goes"})
    assert response.status_code == 501


async def test_webhook_for_an_unknown_provider_returns_422(client):
    response = await client.post("/v1/payments/webhooks/not-a-real-processor", json={})
    assert response.status_code == 422
