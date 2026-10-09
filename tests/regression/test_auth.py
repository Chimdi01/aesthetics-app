import logging

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


async def test_login_strips_control_characters_before_logging_username(client, caplog):
    # OAuth2PasswordRequestForm.username is a raw form field, never
    # validated through EmailStr the way signup's email is — nothing
    # stops a crafted value containing a newline from reaching the
    # "Failed login attempt for %s" warning below and forging a fake
    # extra line in a file-based log (CWE-117). Confirms the fix holds
    # by inspecting the actual logged message, not just the HTTP status.
    with caplog.at_level(logging.WARNING, logger="app.routers.auth"):
        response = await client.post(
            "/v1/auth/login",
            data={"username": "evil@example.com\nFAKE LOG LINE: admin logged in", "password": "whatever"},
        )
    assert response.status_code == 401
    messages = [record.message for record in caplog.records]
    assert any("Failed login attempt" in m for m in messages)
    assert not any("\n" in m for m in messages)
