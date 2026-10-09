"""
Pure logic, no DB/HTTP — the shared primitive every token-backed feature
(refresh tokens now, email verification/password reset next) builds on.
"""
from app.secret_tokens import generate_raw_token, hash_token


def test_generate_raw_token_produces_unique_values():
    tokens = {generate_raw_token() for _ in range(1000)}
    assert len(tokens) == 1000


def test_hash_token_is_deterministic():
    raw = generate_raw_token()
    assert hash_token(raw) == hash_token(raw)


def test_hash_token_differs_for_different_inputs():
    assert hash_token(generate_raw_token()) != hash_token(generate_raw_token())


def test_hash_token_never_returns_the_raw_value():
    # The whole point: if the DB leaks, only this hash is exposed — it
    # must not just be the raw token unchanged or trivially reversible
    # back to it.
    raw = generate_raw_token()
    assert hash_token(raw) != raw
