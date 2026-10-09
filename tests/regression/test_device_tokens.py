from tests.conftest import login, register_user


async def test_register_device_token(client):
    await register_user(client, "devicea@example.com")
    token = await login(client, "devicea@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.post(
        "/v1/users/me/device-tokens",
        json={"token": "fake-fcm-token-1", "platform": "android"},
        headers=headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "android"
    assert "token" not in body  # never echoed back, see DeviceTokenPublic


async def test_register_device_token_without_auth_returns_401(client):
    response = await client.post(
        "/v1/users/me/device-tokens", json={"token": "fake-token", "platform": "ios"}
    )
    assert response.status_code == 401


async def test_list_my_device_tokens(client):
    await register_user(client, "deviceb@example.com")
    token = await login(client, "deviceb@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/v1/users/me/device-tokens", json={"token": "token-phone", "platform": "ios"}, headers=headers
    )
    await client.post(
        "/v1/users/me/device-tokens", json={"token": "token-tablet", "platform": "ios"}, headers=headers
    )

    response = await client.get("/v1/users/me/device-tokens", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_registering_the_same_token_twice_does_not_duplicate(client):
    await register_user(client, "devicec@example.com")
    token = await login(client, "devicec@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/v1/users/me/device-tokens", json={"token": "same-token", "platform": "android"}, headers=headers
    )
    await client.post(
        "/v1/users/me/device-tokens", json={"token": "same-token", "platform": "android"}, headers=headers
    )

    response = await client.get("/v1/users/me/device-tokens", headers=headers)
    assert len(response.json()) == 1


async def test_registering_an_existing_token_reassigns_it_to_the_new_user(client):
    # A real scenario: the same physical device/app-install logs out of
    # one account and into another (or the app was reinstalled and the
    # OS handed back the same token) — the row should move, not error
    # or create a duplicate owned by the wrong user.
    await register_user(client, "deviceowner1@example.com")
    token1 = await login(client, "deviceowner1@example.com")
    headers1 = {"Authorization": f"Bearer {token1}"}
    await client.post(
        "/v1/users/me/device-tokens", json={"token": "shared-device-token", "platform": "ios"}, headers=headers1
    )

    await register_user(client, "deviceowner2@example.com")
    token2 = await login(client, "deviceowner2@example.com")
    headers2 = {"Authorization": f"Bearer {token2}"}
    await client.post(
        "/v1/users/me/device-tokens", json={"token": "shared-device-token", "platform": "ios"}, headers=headers2
    )

    owner1_devices = (await client.get("/v1/users/me/device-tokens", headers=headers1)).json()
    owner2_devices = (await client.get("/v1/users/me/device-tokens", headers=headers2)).json()
    assert owner1_devices == []
    assert len(owner2_devices) == 1


async def test_unregister_my_device_token(client):
    await register_user(client, "deviced@example.com")
    token = await login(client, "deviced@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    registered = (
        await client.post(
            "/v1/users/me/device-tokens", json={"token": "to-remove", "platform": "web"}, headers=headers
        )
    ).json()

    response = await client.delete(f"/v1/users/me/device-tokens/{registered['id']}", headers=headers)
    assert response.status_code == 204

    remaining = (await client.get("/v1/users/me/device-tokens", headers=headers)).json()
    assert remaining == []


async def test_cannot_unregister_someone_elses_device_token(client):
    await register_user(client, "devicevictim@example.com")
    victim_token = await login(client, "devicevictim@example.com")
    victim_headers = {"Authorization": f"Bearer {victim_token}"}
    registered = (
        await client.post(
            "/v1/users/me/device-tokens",
            json={"token": "victims-token", "platform": "android"},
            headers=victim_headers,
        )
    ).json()

    await register_user(client, "devicestranger@example.com")
    stranger_token = await login(client, "devicestranger@example.com")
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}

    response = await client.delete(
        f"/v1/users/me/device-tokens/{registered['id']}", headers=stranger_headers
    )
    assert response.status_code == 404

    # Still there — the stranger's attempt had no effect.
    remaining = (await client.get("/v1/users/me/device-tokens", headers=victim_headers)).json()
    assert len(remaining) == 1


async def test_unregister_unknown_device_token_returns_404(client):
    await register_user(client, "devicee@example.com")
    token = await login(client, "devicee@example.com")
    response = await client.delete(
        "/v1/users/me/device-tokens/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
