from sqlalchemy import text

from tests.conftest import login, register_user, test_engine


async def _promote_to_admin(email: str) -> None:
    # Matches the real provisioning path (see CLAUDE.md): there is no API
    # that grants the admin role — only a direct DB update.
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email})


async def _create_admin_headers(client, email="admin@example.com"):
    await register_user(client, email, role="customer")
    await _promote_to_admin(email)
    # Re-login so the promotion takes effect on this session's token.
    token = await login(client, email)
    return {"Authorization": f"Bearer {token}"}


async def test_revoke_all_sessions_requires_admin(client):
    await register_user(client, "notadmin@example.com")
    token = await login(client, "notadmin@example.com")

    response = await client.post(
        "/v1/admin/revoke-all-sessions",
        json={"confirm": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_revoke_all_sessions_without_token_returns_401(client):
    response = await client.post("/v1/admin/revoke-all-sessions", json={"confirm": True})
    assert response.status_code == 401


async def test_revoke_all_sessions_requires_explicit_confirm(client):
    admin_headers = await _create_admin_headers(client)

    missing_confirm = await client.post("/v1/admin/revoke-all-sessions", json={}, headers=admin_headers)
    assert missing_confirm.status_code == 400

    false_confirm = await client.post(
        "/v1/admin/revoke-all-sessions", json={"confirm": False}, headers=admin_headers
    )
    assert false_confirm.status_code == 400


async def test_revoke_all_sessions_revokes_every_users_refresh_tokens(client):
    # Two ordinary users, each with a live refresh token from login.
    await register_user(client, "a-sessions@example.com")
    tokens_a = (
        await client.post(
            "/v1/auth/login", data={"username": "a-sessions@example.com", "password": "secret123"}
        )
    ).json()
    await register_user(client, "b-sessions@example.com")
    tokens_b = (
        await client.post(
            "/v1/auth/login", data={"username": "b-sessions@example.com", "password": "secret123"}
        )
    ).json()
    admin_headers = await _create_admin_headers(client, "revoker@example.com")

    response = await client.post(
        "/v1/admin/revoke-all-sessions", json={"confirm": True}, headers=admin_headers
    )
    assert response.status_code == 200
    # At least the two ordinary-user sessions plus the admin's own —
    # exact count depends on test ordering/fixtures, so just check it's
    # at least the sessions this test itself created.
    assert response.json()["revoked_count"] >= 2

    refresh_a = await client.post("/v1/auth/refresh", json={"refresh_token": tokens_a["refresh_token"]})
    refresh_b = await client.post("/v1/auth/refresh", json={"refresh_token": tokens_b["refresh_token"]})
    assert refresh_a.status_code == 401
    assert refresh_b.status_code == 401


async def test_revoke_all_sessions_counts_only_previously_active_tokens(client):
    await register_user(client, "onlyone@example.com")
    tokens = (
        await client.post(
            "/v1/auth/login", data={"username": "onlyone@example.com", "password": "secret123"}
        )
    ).json()
    # Already revoked via ordinary logout — must not be double-counted.
    await client.post("/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    admin_headers = await _create_admin_headers(client, "counter-admin@example.com")
    response = await client.post(
        "/v1/admin/revoke-all-sessions", json={"confirm": True}, headers=admin_headers
    )
    assert response.status_code == 200
    # The admin's own login session is the only still-active one left —
    # the already-logged-out one above isn't counted again.
    assert response.json()["revoked_count"] == 1
