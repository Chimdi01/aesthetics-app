"""
The error envelope (app/errors.py, app/main.py's exception handlers)
exercised through the real app — every error response path, not just
the ones with a dedicated AppError call site yet.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.conftest import login, register_user, test_engine


async def test_unknown_route_returns_the_envelope(client):
    response = await client.get("/v1/this-route-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "not_found"
    assert "request_id" in body


async def test_wrong_method_returns_the_envelope(client):
    response = await client.delete("/v1/users/")
    assert response.status_code == 405
    body = response.json()
    # Not in the explicit fallback map (nothing asked for a dedicated
    # code for this rare case) — the deliberate generic default.
    assert body["error_code"] == "invalid_state"


async def test_validation_error_shape(client):
    response = await client.post("/v1/users/", json={"email": "not-an-email", "password": "x"})
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "validation_failed"
    assert isinstance(body["detail"], str)  # never the raw Pydantic array
    assert "fields" in body
    field_names = {f["field"] for f in body["fields"]}
    assert "email" in field_names  # "body" location prefix dropped, not "body.email"
    assert "password" in field_names
    for f in body["fields"]:
        assert set(f.keys()) == {"field", "code", "message"}  # never "input"


async def test_validation_error_never_echoes_submitted_values_via_input(client):
    # A custom allowlist validator's own message DOES echo the value
    # (pre-existing, deliberate UX for a non-sensitive enum field —
    # see app/categories.py) — but Pydantic's own `input` key, which
    # would echo ANY field's raw value including a password, must
    # never appear.
    await register_user(client, "fieldcheck@example.com", role="provider", full_name="T")
    token = await login(client, "fieldcheck@example.com")
    response = await client.post(
        "/v1/providers/",
        json={
            "business_name": "X",
            "currency": "GBP",
            "timezone": "Europe/London",
            "country": "GB",
            "categories": ["not-a-real-category"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    for f in response.json()["fields"]:
        assert "input" not in f


async def test_app_error_includes_request_id(client):
    await register_user(client, "apperr@example.com")
    token = await login(client, "apperr@example.com")
    response = await client.get("/v1/providers/me/payout-account", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "provider_profile_required"
    assert body["request_id"]
    # Echoed back as a response header too, and the two agree.
    assert response.headers["X-Request-ID"] == body["request_id"]


async def test_rate_limit_envelope_and_retry_after_header(client):
    for _ in range(6):
        response = await client.post("/v1/auth/login", data={"username": "nobody@example.com", "password": "x"})
    assert response.status_code == 429
    body = response.json()
    assert body["error_code"] == "rate_limited"
    assert "retry_after_seconds" in body["params"]
    # The header and the body's params must never disagree — both are
    # built from the exact same calculation (see app/main.py's
    # _retry_after_seconds).
    assert str(body["params"]["retry_after_seconds"]) == response.headers["Retry-After"]


async def test_locked_out_login_is_byte_for_byte_identical_to_wrong_password(client):
    # See app/login_lockout.py's docstring and CLAUDE.md's rule: an
    # account/credential-state security control must never change the
    # HTTP response in a way that reveals that state. Directly
    # simulates lockout via SQL (rather than 5 real failed attempts)
    # specifically so this test isn't itself gated by the very rate
    # limiter test_rate_limit_envelope_and_retry_after_header exercises.
    await register_user(client, "locked@example.com", password="secret123")
    await register_user(client, "notlocked@example.com", password="secret123")
    async with test_engine.begin() as conn:
        await conn.execute(
            text("UPDATE users SET login_locked_until = :until WHERE email = :email"),
            {"until": datetime.now(UTC) + timedelta(minutes=15), "email": "locked@example.com"},
        )

    locked_response = await client.post(
        "/v1/auth/login", data={"username": "locked@example.com", "password": "wrong-password"}
    )
    normal_response = await client.post(
        "/v1/auth/login", data={"username": "notlocked@example.com", "password": "wrong-password"}
    )
    assert locked_response.status_code == normal_response.status_code == 401
    # Compare bodies minus request_id (which legitimately differs per
    # request) — everything else must match exactly.
    locked_body = {k: v for k, v in locked_response.json().items() if k != "request_id"}
    normal_body = {k: v for k, v in normal_response.json().items() if k != "request_id"}
    assert locked_body == normal_body


async def test_openapi_schema_has_error_response_components(client):
    response = await client.get("/openapi.json")
    schema = response.json()
    assert "ErrorResponse" in schema["components"]["schemas"]
    assert "FieldError" in schema["components"]["schemas"]
    booking_responses = schema["paths"]["/v1/bookings/"]["post"]["responses"]
    for status_code in ("401", "403", "404", "409", "422", "429"):
        assert status_code in booking_responses
        assert booking_responses[status_code]["content"]["application/json"]["schema"]["$ref"] == (
            "#/components/schemas/ErrorResponse"
        )
