"""
Pure logic, no real Vault/DB/HTTP — the "env" no-op path, and the
"vault" path against a mocked hvac client (never a real network call).
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from app.secrets_provider import SECRET_ENV_VARS, hydrate_environment


def test_env_backend_is_a_no_op(monkeypatch):
    monkeypatch.delenv("SECRETS_BACKEND", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    hydrate_environment()
    assert "DATABASE_URL" not in os.environ


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setenv("SECRETS_BACKEND", "aws_secrets_manager")
    with pytest.raises(NotImplementedError):
        hydrate_environment()


def test_vault_backend_requires_a_token(monkeypatch):
    monkeypatch.setenv("SECRETS_BACKEND", "vault")
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="VAULT_TOKEN"):
        hydrate_environment()


def test_vault_backend_fails_loudly_when_not_authenticated(monkeypatch):
    monkeypatch.setenv("SECRETS_BACKEND", "vault")
    monkeypatch.setenv("VAULT_TOKEN", "fake-token")

    fake_client = MagicMock()
    fake_client.is_authenticated.return_value = False
    with patch("hvac.Client", return_value=fake_client), pytest.raises(RuntimeError, match="authenticate"):
        hydrate_environment()


def test_vault_backend_hydrates_only_the_allowlisted_secret_names(monkeypatch):
    monkeypatch.setenv("SECRETS_BACKEND", "vault")
    monkeypatch.setenv("VAULT_TOKEN", "fake-token")
    for name in SECRET_ENV_VARS:
        monkeypatch.delenv(name, raising=False)

    fake_client = MagicMock()
    fake_client.is_authenticated.return_value = True
    fake_client.secrets.kv.v2.read_secret_version.return_value = {
        "data": {
            "data": {
                "JWT_SECRET_KEY": "from-vault",
                "DATABASE_URL": "postgresql://from-vault",
                # Not in SECRET_ENV_VARS — proves the allowlist, not
                # "whatever Vault happens to return", decides what lands
                # in os.environ.
                "SOME_UNRELATED_KEY": "should-not-leak-into-environ",
            }
        }
    }
    try:
        with patch("hvac.Client", return_value=fake_client):
            hydrate_environment()

        assert os.environ["JWT_SECRET_KEY"] == "from-vault"
        assert os.environ["DATABASE_URL"] == "postgresql://from-vault"
        assert "SOME_UNRELATED_KEY" not in os.environ
    finally:
        # hydrate_environment sets these via plain os.environ[...] = ...,
        # not monkeypatch.setenv — monkeypatch has no record of them and
        # won't revert them on teardown, so this test cleans up after
        # itself explicitly rather than leaking values into later tests.
        os.environ.pop("JWT_SECRET_KEY", None)
        os.environ.pop("DATABASE_URL", None)
