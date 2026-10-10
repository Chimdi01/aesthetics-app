"""
2FA (app/totp.py, app/mfa_challenge.py) exercised through the real
enrollment endpoints and the real two-step login flow.

pyotp is used directly here to generate a REAL valid code against the
secret the enrollment endpoint actually returned — not a hardcoded
"123456", which would just test that the test itself is wired up, not
that TOTP verification works.
"""
import pyotp

from tests.conftest import login, register_user


async def _enroll_and_confirm(client, headers):
    """Returns (secret, backup_codes) for a freshly 2FA-enabled account."""
    enroll = await client.post("/v1/users/me/2fa/enroll", headers=headers)
    secret = enroll.json()["secret"]
    code = pyotp.TOTP(secret).now()
    confirm = await client.post("/v1/users/me/2fa/confirm", json={"code": code}, headers=headers)
    return secret, confirm.json()["backup_codes"]


# --- enrollment ---


async def test_enroll_requires_auth(client):
    response = await client.post("/v1/users/me/2fa/enroll")
    assert response.status_code == 401


async def test_enroll_returns_a_secret_and_provisioning_uri(client):
    await register_user(client, "enroll@example.com")
    token = await login(client, "enroll@example.com")
    response = await client.post(
        "/v1/users/me/2fa/enroll", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["secret"]
    assert body["provisioning_uri"].startswith("otpauth://totp/")


async def test_reenrolling_before_confirming_generates_a_new_secret(client):
    await register_user(client, "reenroll@example.com")
    token = await login(client, "reenroll@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    first = (await client.post("/v1/users/me/2fa/enroll", headers=headers)).json()
    second = (await client.post("/v1/users/me/2fa/enroll", headers=headers)).json()
    assert first["secret"] != second["secret"]


async def test_enroll_fails_if_2fa_already_enabled(client):
    await register_user(client, "alreadyon@example.com")
    token = await login(client, "alreadyon@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _enroll_and_confirm(client, headers)

    response = await client.post("/v1/users/me/2fa/enroll", headers=headers)
    assert response.status_code == 400


# --- confirmation ---


async def test_confirm_without_enrolling_first_returns_400(client):
    await register_user(client, "noenroll@example.com")
    token = await login(client, "noenroll@example.com")
    response = await client.post(
        "/v1/users/me/2fa/confirm", json={"code": "123456"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 400


async def test_confirm_with_wrong_code_returns_400(client):
    await register_user(client, "wrongcode@example.com")
    token = await login(client, "wrongcode@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/v1/users/me/2fa/enroll", headers=headers)

    response = await client.post("/v1/users/me/2fa/confirm", json={"code": "000000"}, headers=headers)
    assert response.status_code == 400


async def test_confirm_with_correct_code_enables_2fa_and_returns_ten_backup_codes(client):
    await register_user(client, "confirm@example.com")
    token = await login(client, "confirm@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    _, backup_codes = await _enroll_and_confirm(client, headers)
    assert len(backup_codes) == 10
    assert len(set(backup_codes)) == 10  # all distinct

    status = await client.get("/v1/users/me/2fa/status", headers=headers)
    assert status.json() == {"enabled": True, "backup_codes_remaining": 10}


# --- login flow ---


async def test_login_without_2fa_enabled_returns_tokens_directly(client):
    await register_user(client, "no2fa@example.com")
    response = await client.post(
        "/v1/auth/login", data={"username": "no2fa@example.com", "password": "secret123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mfa_required"] is False
    assert "access_token" in body


async def test_login_with_2fa_enabled_returns_a_challenge_not_tokens(client):
    await register_user(client, "login2fa@example.com")
    token = await login(client, "login2fa@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _enroll_and_confirm(client, headers)

    response = await client.post(
        "/v1/auth/login", data={"username": "login2fa@example.com", "password": "secret123"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mfa_required"] is True
    assert "mfa_token" in body
    assert "access_token" not in body


async def test_verify_2fa_with_correct_code_completes_login(client):
    await register_user(client, "verify2fa@example.com")
    token = await login(client, "verify2fa@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    secret, _ = await _enroll_and_confirm(client, headers)

    challenge = (
        await client.post(
            "/v1/auth/login", data={"username": "verify2fa@example.com", "password": "secret123"}
        )
    ).json()
    code = pyotp.TOTP(secret).now()
    response = await client.post(
        "/v1/auth/login/verify-2fa", json={"mfa_token": challenge["mfa_token"], "code": code}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mfa_required"] is False
    assert body["access_token"]


async def test_verify_2fa_with_a_backup_code_completes_login(client):
    await register_user(client, "backupcode@example.com")
    token = await login(client, "backupcode@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    _, backup_codes = await _enroll_and_confirm(client, headers)

    challenge = (
        await client.post(
            "/v1/auth/login", data={"username": "backupcode@example.com", "password": "secret123"}
        )
    ).json()
    response = await client.post(
        "/v1/auth/login/verify-2fa", json={"mfa_token": challenge["mfa_token"], "code": backup_codes[0]}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_a_used_backup_code_cannot_be_reused(client):
    await register_user(client, "reusebackup@example.com")
    token = await login(client, "reusebackup@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    _, backup_codes = await _enroll_and_confirm(client, headers)

    async def _attempt_login_with_backup_code(code):
        challenge = (
            await client.post(
                "/v1/auth/login", data={"username": "reusebackup@example.com", "password": "secret123"}
            )
        ).json()
        return await client.post(
            "/v1/auth/login/verify-2fa", json={"mfa_token": challenge["mfa_token"], "code": code}
        )

    first = await _attempt_login_with_backup_code(backup_codes[0])
    assert first.status_code == 200

    second = await _attempt_login_with_backup_code(backup_codes[0])
    assert second.status_code == 401


async def test_verify_2fa_with_wrong_code_returns_401(client):
    await register_user(client, "wrongverify@example.com")
    token = await login(client, "wrongverify@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _enroll_and_confirm(client, headers)

    challenge = (
        await client.post(
            "/v1/auth/login", data={"username": "wrongverify@example.com", "password": "secret123"}
        )
    ).json()
    response = await client.post(
        "/v1/auth/login/verify-2fa", json={"mfa_token": challenge["mfa_token"], "code": "000000"}
    )
    assert response.status_code == 401


async def test_verify_2fa_with_unknown_mfa_token_returns_401(client):
    response = await client.post(
        "/v1/auth/login/verify-2fa", json={"mfa_token": "not-a-real-token", "code": "123456"}
    )
    assert response.status_code == 401


async def test_mfa_challenge_is_single_use(client):
    await register_user(client, "singleusemfa@example.com")
    token = await login(client, "singleusemfa@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    secret, _ = await _enroll_and_confirm(client, headers)

    challenge = (
        await client.post(
            "/v1/auth/login", data={"username": "singleusemfa@example.com", "password": "secret123"}
        )
    ).json()
    code = pyotp.TOTP(secret).now()

    first = await client.post(
        "/v1/auth/login/verify-2fa", json={"mfa_token": challenge["mfa_token"], "code": code}
    )
    assert first.status_code == 200

    # Same challenge token again — even with a freshly valid code — must
    # not work a second time.
    second_code = pyotp.TOTP(secret).now()
    second = await client.post(
        "/v1/auth/login/verify-2fa", json={"mfa_token": challenge["mfa_token"], "code": second_code}
    )
    assert second.status_code == 401


# --- disable ---


async def test_disable_requires_auth(client):
    response = await client.post("/v1/users/me/2fa/disable", json={"password": "secret123"})
    assert response.status_code == 401


async def test_disable_with_wrong_password_returns_403(client):
    await register_user(client, "wrongpwdisable@example.com")
    token = await login(client, "wrongpwdisable@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _enroll_and_confirm(client, headers)

    response = await client.post(
        "/v1/users/me/2fa/disable", json={"password": "wrong-password"}, headers=headers
    )
    assert response.status_code == 403


async def test_disable_fails_if_2fa_not_enabled(client):
    await register_user(client, "notenableddisable@example.com")
    token = await login(client, "notenableddisable@example.com")
    response = await client.post(
        "/v1/users/me/2fa/disable",
        json={"password": "secret123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


async def test_disable_with_correct_password_turns_off_2fa(client):
    await register_user(client, "realdisable@example.com")
    token = await login(client, "realdisable@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _enroll_and_confirm(client, headers)

    response = await client.post(
        "/v1/users/me/2fa/disable", json={"password": "secret123"}, headers=headers
    )
    assert response.status_code == 204

    status = await client.get("/v1/users/me/2fa/status", headers=headers)
    assert status.json() == {"enabled": False, "backup_codes_remaining": 0}

    # Login no longer challenges for 2FA.
    login_response = await client.post(
        "/v1/auth/login", data={"username": "realdisable@example.com", "password": "secret123"}
    )
    assert login_response.json()["mfa_required"] is False


# --- backup code regeneration ---


async def test_regenerate_backup_codes_requires_correct_password(client):
    await register_user(client, "regen@example.com")
    token = await login(client, "regen@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await _enroll_and_confirm(client, headers)

    response = await client.post(
        "/v1/users/me/2fa/backup-codes/regenerate", json={"password": "wrong"}, headers=headers
    )
    assert response.status_code == 403


async def test_regenerate_backup_codes_invalidates_the_old_batch(client):
    await register_user(client, "regen2@example.com")
    token = await login(client, "regen2@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    _, old_codes = await _enroll_and_confirm(client, headers)

    regen = await client.post(
        "/v1/users/me/2fa/backup-codes/regenerate", json={"password": "secret123"}, headers=headers
    )
    assert regen.status_code == 200
    new_codes = regen.json()["backup_codes"]
    assert len(new_codes) == 10
    assert set(new_codes).isdisjoint(set(old_codes))

    # An old code no longer works to complete a login.
    challenge = (
        await client.post("/v1/auth/login", data={"username": "regen2@example.com", "password": "secret123"})
    ).json()
    response = await client.post(
        "/v1/auth/login/verify-2fa", json={"mfa_token": challenge["mfa_token"], "code": old_codes[0]}
    )
    assert response.status_code == 401
