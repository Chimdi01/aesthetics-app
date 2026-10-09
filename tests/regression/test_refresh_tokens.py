from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from tests.conftest import register_user, test_engine


async def _create_user_and_login(client, email="user@example.com"):
    await register_user(client, email, password="secret123")
    response = await client.post("/v1/auth/login", data={"username": email, "password": "secret123"})
    return response.json()


async def _promote_to_admin(email: str) -> None:
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email})


async def _expire_refresh_token(raw_token: str) -> None:
    # No API expires a token early — this reaches into the DB directly to
    # set up the "your refresh token expired" case, the same way other
    # regression tests reach in for admin promotion (see _promote_to_admin
    # above and tests/regression/test_identity_verification.py).
    from app.secret_tokens import hash_token

    async with test_engine.begin() as conn:
        await conn.execute(
            text("UPDATE refresh_tokens SET expires_at = :expires_at WHERE token_hash = :token_hash"),
            {"expires_at": datetime.now(UTC) - timedelta(days=1), "token_hash": hash_token(raw_token)},
        )


async def test_login_returns_both_access_and_refresh_token(client):
    await register_user(client, "pair@example.com")
    response = await client.post(
        "/v1/auth/login", data={"username": "pair@example.com", "password": "secret123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["access_token"] != body["refresh_token"]


async def test_refresh_issues_a_new_token_pair(client):
    tokens = await _create_user_and_login(client)
    response = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"]
    # NOT asserting new_tokens["access_token"] != tokens["access_token"]:
    # a JWT's "exp" claim is encoded as whole seconds, and this access
    # token has only {sub, exp} as claims — two tokens minted for the
    # same user within the same wall-clock second are legitimately
    # byte-for-byte identical, not a rotation bug. The opaque,
    # randomly-generated refresh token has no such collision case.
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


async def test_new_access_token_from_refresh_actually_authenticates(client):
    tokens = await _create_user_and_login(client)
    new_tokens = (
        await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).json()

    response = await client.get(
        "/v1/bookings/as-customer", headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
    )
    assert response.status_code == 200


async def test_refresh_rotates_the_old_token_so_it_cannot_be_reused(client):
    tokens = await _create_user_and_login(client)

    first = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert first.status_code == 200

    # Reusing the SAME (now-rotated) refresh token a second time must
    # fail — this is the whole point of rotation: a stolen copy of an
    # already-used token is worthless once the legitimate client has
    # moved on to the new one.
    second = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert second.status_code == 401


async def test_refresh_with_unknown_token_returns_401(client):
    response = await client.post("/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


async def test_refresh_with_expired_token_returns_401(client):
    tokens = await _create_user_and_login(client)
    await _expire_refresh_token(tokens["refresh_token"])

    response = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


async def test_refresh_rejects_deactivated_account(client):
    signup = await register_user(client, "deactivated@example.com")
    target_user_id = signup.json()["id"]
    tokens = (
        await client.post(
            "/v1/auth/login", data={"username": "deactivated@example.com", "password": "secret123"}
        )
    ).json()

    admin_email = "admin-refresh@example.com"
    await register_user(client, admin_email)
    await _promote_to_admin(admin_email)
    # Re-login so the promotion takes effect on this session's token
    # (mirrors the same re-login step in tests/regression/test_identity_verification.py).
    admin_login = await client.post("/v1/auth/login", data={"username": admin_email, "password": "secret123"})
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    deactivate = await client.patch(
        f"/v1/admin/users/{target_user_id}/status", json={"is_active": False}, headers=admin_headers
    )
    assert deactivate.status_code == 200

    # The refresh token was issued before deactivation — it must stop
    # working immediately, not keep minting fresh access tokens, the
    # same "no lingering access" guarantee get_current_user already gives
    # an already-issued ACCESS token (see app/security.py).
    response = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 403


async def test_logout_revokes_the_refresh_token(client):
    tokens = await _create_user_and_login(client)

    logout = await client.post("/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout.status_code == 204

    refresh = await client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 401


async def test_logout_with_unknown_token_still_returns_204(client):
    # No information leak about whether a given token string ever
    # existed — logout always succeeds from the caller's point of view.
    response = await client.post("/v1/auth/logout", json={"refresh_token": "never-issued"})
    assert response.status_code == 204


async def test_logout_all_revokes_every_session_but_only_for_that_user(client):
    tokens_a = await _create_user_and_login(client, "multi-session@example.com")
    second_login = await client.post(
        "/v1/auth/login", data={"username": "multi-session@example.com", "password": "secret123"}
    )
    tokens_b = second_login.json()

    other_user_tokens = await _create_user_and_login(client, "unaffected@example.com")

    logout_all = await client.post(
        "/v1/auth/logout-all", headers={"Authorization": f"Bearer {tokens_a['access_token']}"}
    )
    assert logout_all.status_code == 204

    refresh_a = await client.post("/v1/auth/refresh", json={"refresh_token": tokens_a["refresh_token"]})
    assert refresh_a.status_code == 401
    refresh_b = await client.post("/v1/auth/refresh", json={"refresh_token": tokens_b["refresh_token"]})
    assert refresh_b.status_code == 401

    # A different user's session is untouched by someone else's logout-all.
    refresh_other = await client.post(
        "/v1/auth/refresh", json={"refresh_token": other_user_tokens["refresh_token"]}
    )
    assert refresh_other.status_code == 200


async def test_logout_all_without_token_returns_401(client):
    response = await client.post("/v1/auth/logout-all")
    assert response.status_code == 401
