from tests.conftest import register_user


async def test_login_with_correct_credentials_returns_token(client):
    # Also a regression guard for a missing "python-multipart" install:
    # OAuth2PasswordRequestForm needs it to parse this form body. Without
    # it, the app fails to even start (RuntimeError at route registration),
    # so the whole test session would error out at collection rather than
    # just this test failing.
    await register_user(client, "jane@example.com", password="secret123")
    response = await client.post("/v1/auth/login", data={"username": "jane@example.com", "password": "secret123"})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_with_wrong_password_returns_401(client):
    await register_user(client, "jane@example.com", password="secret123")
    response = await client.post("/v1/auth/login", data={"username": "jane@example.com", "password": "wrong"})
    assert response.status_code == 401


async def test_login_with_unknown_email_returns_401(client):
    response = await client.post(
        "/v1/auth/login", data={"username": "nobody@example.com", "password": "whatever"}
    )
    assert response.status_code == 401


async def test_login_is_case_insensitive_on_email(client):
    # Signup normalizes to lowercase (app/schemas/user.py); login must
    # normalize the same way or this becomes a false "incorrect email or
    # password" for anyone who types their email differently than they
    # registered it.
    await register_user(client, "Jane@Example.com", password="secret123")
    response = await client.post(
        "/v1/auth/login", data={"username": "jane@example.com", "password": "secret123"}
    )
    assert response.status_code == 200
