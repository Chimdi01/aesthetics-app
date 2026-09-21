"""
Pure logic in app/security.py — no DB, no HTTP. These don't exercise
get_current_user/get_current_provider directly since those need a live
request + DB session; that behavior is covered by the regression tests
in tests/regression/test_providers.py instead.
"""
import pytest
from jose import JWTError, jwt

from app.config import settings
from app.security import create_access_token, hash_password, verify_password


def test_hash_password_roundtrip():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_hash_password_handles_long_passwords_without_crashing():
    # Regression guard: passlib==1.7.4 + bcrypt>=4.0 crashes on this with
    # "password cannot be longer than 72 bytes" — not just for inputs
    # over 72 bytes, but for EVERY hash() call, because the crash happens
    # in passlib's own internal self-test. A short password (see the test
    # above) would already have caught it, but a >72-byte one is the
    # input the underlying bug report was actually about.
    long_password = "x" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)


def test_create_access_token_contains_correct_subject_and_expiry():
    user_id = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    token = create_access_token(user_id)

    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == user_id
    assert "exp" in payload


def test_decoding_token_with_wrong_secret_fails():
    token = create_access_token("3fa85f64-5717-4562-b3fc-2c963f66afa6")
    with pytest.raises(JWTError):
        jwt.decode(token, "not-the-real-secret", algorithms=[settings.jwt_algorithm])
