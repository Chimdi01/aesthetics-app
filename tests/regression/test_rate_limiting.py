"""
Rate limiting on endpoints with a tighter-than-default limit (login,
signup, portfolio upload, reporting a user) — see app/rate_limit.py for
the global 200/minute default and the single-instance in-memory-storage
caveat. The `_reset_rate_limiter` autouse fixture in conftest.py clears
slowapi's counters before every test, so these limits never leak in from
(or out to) any other test.
"""
import io

import pytest
from PIL import Image

from app.config import settings
from tests.conftest import login, register_user


async def test_login_is_rate_limited_after_five_attempts_per_minute(client):
    await register_user(client, "user@example.com", password="correct-password")

    for _ in range(5):
        response = await client.post(
            "/v1/auth/login", data={"username": "user@example.com", "password": "wrong-password"}
        )
        assert response.status_code == 401

    response = await client.post(
        "/v1/auth/login", data={"username": "user@example.com", "password": "wrong-password"}
    )
    assert response.status_code == 429


async def test_login_rate_limit_applies_even_with_correct_password(client):
    # The limit is per-IP, not per-outcome — it has to apply before
    # credentials are checked, otherwise a correct-password retry loop
    # bypasses it entirely.
    await register_user(client, "user@example.com", password="correct-password")

    for _ in range(5):
        await client.post("/v1/auth/login", data={"username": "user@example.com", "password": "correct-password"})

    response = await client.post(
        "/v1/auth/login", data={"username": "user@example.com", "password": "correct-password"}
    )
    assert response.status_code == 429


async def test_signup_is_rate_limited_after_ten_attempts_per_hour(client):
    for i in range(10):
        response = await register_user(client, f"user{i}@example.com")
        assert response.status_code == 201

    response = await register_user(client, "user11@example.com")
    assert response.status_code == 429


async def test_other_endpoints_are_not_affected_by_the_tighter_login_limit(client):
    # Six logins' worth of failed attempts shouldn't make an unrelated
    # endpoint start failing too — each @limiter.limit() override is
    # independent, not a shared global counter.
    for _ in range(6):
        await client.post("/v1/auth/login", data={"username": "nobody@example.com", "password": "x"})

    response = await client.get("/health")
    assert response.status_code == 200


@pytest.fixture(autouse=True)
def _use_tmp_media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "media_root", str(tmp_path))
    yield


def _real_jpeg_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), (1, 2, 3)).save(buffer, format="JPEG")
    return buffer.getvalue()


async def test_portfolio_upload_is_rate_limited_after_twenty_per_hour(client):
    await register_user(client, "provider@example.com", password="secret123", role="provider")
    token = await login(client, "provider@example.com", "secret123")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/v1/providers/", json={"business_name": "Studio", "categories": ["hair"]}, headers=headers
    )

    for _ in range(20):
        response = await client.post(
            "/v1/providers/me/portfolio",
            files={"file": ("p.jpg", io.BytesIO(_real_jpeg_bytes()), "image/jpeg")},
            headers=headers,
        )
        assert response.status_code == 201

    response = await client.post(
        "/v1/providers/me/portfolio",
        files={"file": ("p.jpg", io.BytesIO(_real_jpeg_bytes()), "image/jpeg")},
        headers=headers,
    )
    assert response.status_code == 429


async def test_report_submission_is_rate_limited_after_ten_per_hour(client):
    target = (await register_user(client, "target@example.com", password="secret123")).json()
    await register_user(client, "reporter@example.com", password="secret123")
    token = await login(client, "reporter@example.com", "secret123")
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(10):
        response = await client.post(
            f"/v1/users/{target['id']}/report", json={"reason": "spam"}, headers=headers
        )
        assert response.status_code == 201

    response = await client.post(
        f"/v1/users/{target['id']}/report", json={"reason": "spam"}, headers=headers
    )
    assert response.status_code == 429
