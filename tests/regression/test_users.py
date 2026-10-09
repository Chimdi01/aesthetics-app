from sqlalchemy import text

from tests.conftest import login, register_user, test_engine


async def _promote_to_admin(email: str) -> None:
    async with test_engine.begin() as conn:
        await conn.execute(text("UPDATE users SET role = 'admin' WHERE email = :email"), {"email": email})


async def test_create_user_returns_201_with_no_password_field(client):
    # Regression guard: passlib==1.7.4 + bcrypt>=4.0 made every hash_password()
    # call raise ValueError, turning this into a 500. This is the same code
    # path tests/unit/test_security.py checks in isolation, exercised here
    # through the actual endpoint.
    response = await register_user(client, "jane@example.com")
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "jane@example.com"
    assert "password" not in body
    assert "hashed_password" not in body


async def test_create_user_defaults_role_to_customer(client):
    response = await register_user(client, "jane@example.com")
    assert response.json()["role"] == "customer"


async def test_create_user_duplicate_email_returns_409(client):
    await register_user(client, "jane@example.com")
    response = await register_user(client, "jane@example.com")
    assert response.status_code == 409


async def test_create_user_normalizes_email_and_catches_case_variant_duplicates(client):
    created = await register_user(client, "Jane@Example.com")
    assert created.json()["email"] == "jane@example.com"

    duplicate = await register_user(client, "JANE@EXAMPLE.COM")
    assert duplicate.status_code == 409


async def test_create_user_rejects_password_under_eight_characters(client):
    response = await register_user(client, "jane@example.com", password="short")
    assert response.status_code == 422


async def test_get_user_by_id_without_token_returns_401(client):
    created = (await register_user(client, "jane@example.com")).json()
    response = await client.get(f"/v1/users/{created['id']}")
    assert response.status_code == 401


async def test_get_own_user_returns_full_record(client):
    created = (await register_user(client, "jane@example.com")).json()
    token = await login(client, "jane@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(f"/v1/users/{created['id']}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "jane@example.com"
    assert "is_active" in body


async def test_get_a_stranger_returns_reduced_record_without_email(client):
    target = (await register_user(client, "jane@example.com")).json()
    await register_user(client, "stranger@example.com")
    stranger_token = await login(client, "stranger@example.com")
    stranger_headers = {"Authorization": f"Bearer {stranger_token}"}

    response = await client.get(f"/v1/users/{target['id']}", headers=stranger_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == target["full_name"]
    assert "email" not in body
    assert "is_active" not in body


async def test_admin_sees_full_record_for_a_stranger(client):
    target = (await register_user(client, "jane@example.com")).json()
    await register_user(client, "admin@example.com")
    await _promote_to_admin("admin@example.com")
    admin_token = await login(client, "admin@example.com")

    response = await client.get(
        f"/v1/users/{target['id']}", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "jane@example.com"


async def test_get_user_by_id_not_found_returns_404(client):
    await register_user(client, "jane@example.com")
    token = await login(client, "jane@example.com")
    response = await client.get(
        "/v1/users/00000000-0000-0000-0000-000000000000", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


# --- phone number (PATCH /v1/users/me/phone-number) ---


async def test_new_signup_has_no_phone_number(client):
    created = (await register_user(client, "jane@example.com")).json()
    assert created["phone_number"] is None


async def test_update_my_phone_number(client):
    created = (await register_user(client, "jane@example.com")).json()
    token = await login(client, "jane@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.patch(
        "/v1/users/me/phone-number", json={"phone_number": "+14155552671"}, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["phone_number"] == "+14155552671"

    # Persisted, not just echoed back.
    fetched = await client.get(f"/v1/users/{created['id']}", headers=headers)
    assert fetched.json()["phone_number"] == "+14155552671"


async def test_update_my_phone_number_rejects_invalid_format(client):
    await register_user(client, "badphone@example.com")
    token = await login(client, "badphone@example.com")
    response = await client.patch(
        "/v1/users/me/phone-number",
        json={"phone_number": "not-a-number"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_clear_my_phone_number(client):
    await register_user(client, "clearme@example.com")
    token = await login(client, "clearme@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await client.patch("/v1/users/me/phone-number", json={"phone_number": "+14155552671"}, headers=headers)

    response = await client.patch("/v1/users/me/phone-number", json={"phone_number": None}, headers=headers)
    assert response.status_code == 200
    assert response.json()["phone_number"] is None


async def test_update_my_phone_number_without_token_returns_401(client):
    response = await client.patch("/v1/users/me/phone-number", json={"phone_number": "+14155552671"})
    assert response.status_code == 401


# --- notification preferences (GET/PATCH /v1/users/me/notification-preferences) ---


async def test_new_signup_gets_default_notification_preferences(client):
    await register_user(client, "defaults@example.com")
    token = await login(client, "defaults@example.com")
    response = await client.get(
        "/v1/users/me/notification-preferences", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["notify_on_new_message"] is True
    assert body["message_frequency"] == "every_message"
    assert body["notify_on_booking_status_change"] is True
    assert body["notify_on_new_review"] is True
    assert body["notify_on_verification_decision"] is True
    assert body["notify_on_report_decision"] is True


async def test_update_notification_preferences_is_a_partial_patch(client):
    await register_user(client, "partial@example.com")
    token = await login(client, "partial@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.patch(
        "/v1/users/me/notification-preferences", json={"notify_on_new_message": False}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["notify_on_new_message"] is False
    # Untouched fields keep their default — a partial update must not
    # reset everything else to some blank state.
    assert body["notify_on_new_review"] is True
    assert body["message_frequency"] == "every_message"


async def test_update_notification_preferences_message_frequency(client):
    await register_user(client, "frequency@example.com")
    token = await login(client, "frequency@example.com")
    response = await client.patch(
        "/v1/users/me/notification-preferences",
        json={"message_frequency": "first_message_only"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["message_frequency"] == "first_message_only"


async def test_notification_preferences_without_token_returns_401(client):
    response = await client.get("/v1/users/me/notification-preferences")
    assert response.status_code == 401
