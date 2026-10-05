"""
Verifies the actual logging behavior wired up in app/main.py and the
routers — not every individual log line (that would be brittle busywork),
but the load-bearing pieces: a request gets a correlation id that comes
back on the response, successful requests stay quiet at DEBUG (so real
traffic volume doesn't flood production logs at INFO), errors surface at
WARNING/ERROR regardless of path, and an authorization failure is logged
rather than disappearing silently into just an HTTP 403.
"""
import logging

from tests.conftest import login, register_user


async def test_response_includes_request_id_header(client):
    response = await client.get("/health")
    assert "X-Request-ID" in response.headers


async def test_response_reuses_caller_supplied_request_id(client):
    response = await client.get("/health", headers={"X-Request-ID": "caller-supplied-id"})
    assert response.headers["X-Request-ID"] == "caller-supplied-id"


async def test_successful_request_is_logged_at_debug_not_info(client, caplog):
    # At INFO, a successful request should be invisible — see the
    # comment in app/main.py's log_requests for why (volume at real
    # traffic levels, and business events already get their own INFO log).
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = await client.get("/health")
    assert response.status_code == 200
    assert not any("GET /health -> 200" in record.message for record in caplog.records)

    with caplog.at_level(logging.DEBUG, logger="app.main"):
        response = await client.get("/health")
    assert any("GET /health -> 200" in record.message for record in caplog.records)


async def test_client_error_response_is_logged_at_warning(client, caplog):
    with caplog.at_level(logging.WARNING, logger="app.main"):
        response = await client.get("/providers/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert any("-> 404" in record.message and record.levelname == "WARNING" for record in caplog.records)


async def test_readiness_check_reports_database_ok(client):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_authorization_denial_is_logged_at_warning(client, caplog):
    await register_user(client, "owner@example.com", password="secret123", role="provider")
    owner_token = await login(client, "owner@example.com", "secret123")
    profile = (
        await client.post(
            "/providers/",
            json={"business_name": "Studio", "categories": ["hair"]},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
    ).json()

    await register_user(client, "customer@example.com", password="secret123", role="customer")
    customer_token = await login(client, "customer@example.com", "secret123")
    from datetime import datetime, timedelta, timezone

    booking = (
        await client.post(
            "/bookings/",
            json={
                "provider_profile_id": profile["id"],
                "category": "hair",
                "visit_type": "shop_visit",
                "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            },
            headers={"Authorization": f"Bearer {customer_token}"},
        )
    ).json()

    await register_user(client, "stranger@example.com", password="secret123", role="customer")
    stranger_token = await login(client, "stranger@example.com", "secret123")

    with caplog.at_level(logging.WARNING, logger="app.routers.bookings"):
        response = await client.get(
            f"/bookings/{booking['id']}", headers={"Authorization": f"Bearer {stranger_token}"}
        )
    assert response.status_code == 403
    assert any("denied access to booking" in record.message for record in caplog.records)


async def test_failed_login_is_logged_at_warning_without_leaking_password(client, caplog):
    await register_user(client, "user@example.com", password="correct-password")

    with caplog.at_level(logging.WARNING, logger="app.routers.auth"):
        response = await client.post(
            "/auth/login", data={"username": "user@example.com", "password": "wrong-password"}
        )
    assert response.status_code == 401
    messages = [record.message for record in caplog.records]
    assert any("Failed login attempt" in m for m in messages)
    assert not any("wrong-password" in m for m in messages)
