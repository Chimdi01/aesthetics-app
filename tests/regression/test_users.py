from tests.conftest import register_user


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


async def test_get_user_by_id_success(client):
    created = (await register_user(client, "jane@example.com")).json()
    response = await client.get(f"/v1/users/{created['id']}")
    assert response.status_code == 200
    assert response.json()["email"] == "jane@example.com"


async def test_get_user_by_id_not_found_returns_404(client):
    response = await client.get("/v1/users/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
