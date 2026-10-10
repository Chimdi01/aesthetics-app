"""
Where this app's secrets actually come from, abstracted the same way
app/storage.py isolates file storage and app/email.py isolates email
sending: every secret-bearing setting in app/config.py is still read
from a plain environment variable by pydantic-settings, exactly as
before — this module's only job is to POPULATE those environment
variables at startup, from wherever the real secret lives, before
Settings() is ever constructed.

Backends:
- "env" (default): a no-op. Secrets are already wherever they normally
  are (a .env file locally via python-dotenv, real env vars in
  production) — nothing to fetch.
- "vault": fetches from a HashiCorp Vault KV v2 secret and injects each
  value into os.environ. Chosen over a cloud-specific secrets manager
  (AWS Secrets Manager, GCP Secret Manager) specifically because it's
  self-hostable and not tied to a cloud provider — no hosting/platform
  decision has been made yet (see CLAUDE.md), so a backend that doesn't
  require one is the one that can actually be built and tested today.
  Point this at a real production Vault cluster later by changing
  VAULT_ADDR; nothing else in this file or app/config.py needs to
  change — see docker-compose.yml for a local dev-mode Vault to test
  against now.

Chicken-and-egg note: which backend to use, and Vault's own connection
details (VAULT_ADDR, VAULT_TOKEN, VAULT_SECRET_PATH), are read directly
from os.environ here — NOT from app.config.settings — because this
runs BEFORE Settings exists; Settings is what gets hydrated BY this,
not the other way around.

Auth note: VAULT_TOKEN (a static token) is the simplest thing that
works for local dev and is good enough to build and test the
integration against. AppRole or another non-static auth method is the
production-grade choice and the next thing to swap in here — flagged,
not built, same as everything else in this file that's waiting on a
real deployment target to exist.
"""
import logging
import os

logger = logging.getLogger(__name__)

# The names of every secret-bearing setting this app has — kept as an
# explicit allowlist (not "whatever happens to be in the Vault path")
# so a real backend fetches exactly these and nothing else, and so a
# typo'd secret name in Vault fails loudly (the key just won't be
# present, Settings falls back to its hardcoded dev-only default) rather
# than silently injecting unrelated data into the process environment.
SECRET_ENV_VARS = (
    "DATABASE_URL",
    "JWT_SECRET_KEY",
    "JWT_PREVIOUS_SECRET_KEYS",
    "TOTP_ENCRYPTION_KEY",
)


def _hydrate_from_vault() -> None:
    import hvac

    addr = os.environ.get("VAULT_ADDR", "http://localhost:8200")
    token = os.environ.get("VAULT_TOKEN")
    secret_path = os.environ.get("VAULT_SECRET_PATH", "aesthetics-app")

    if not token:
        # Fails loudly at startup, not with a confusing downstream
        # "database connection refused" once Settings falls back to its
        # dev-only DATABASE_URL default — a missing VAULT_TOKEN when
        # SECRETS_BACKEND=vault is a configuration mistake, not a
        # recoverable state.
        raise RuntimeError("SECRETS_BACKEND=vault but VAULT_TOKEN is not set")

    client = hvac.Client(url=addr, token=token)
    if not client.is_authenticated():
        raise RuntimeError(f"Could not authenticate to Vault at {addr}")

    response = client.secrets.kv.v2.read_secret_version(path=secret_path)
    secret_data = response["data"]["data"]

    found = 0
    for name in SECRET_ENV_VARS:
        if name in secret_data:
            os.environ[name] = secret_data[name]
            found += 1
    logger.info("Hydrated %d/%d secret(s) from Vault at %s (path=%s)", found, len(SECRET_ENV_VARS), addr, secret_path)


def hydrate_environment() -> None:
    """Populates os.environ with every secret this app needs, from
    whichever backend SECRETS_BACKEND names. Must run exactly once, at
    import time, before app.config.Settings() is constructed — see
    app/config.py, which calls this before defining the Settings class."""
    backend = os.environ.get("SECRETS_BACKEND", "env")
    if backend == "env":
        return
    if backend == "vault":
        _hydrate_from_vault()
        return
    raise NotImplementedError(f"Unknown SECRETS_BACKEND: {backend!r}")
