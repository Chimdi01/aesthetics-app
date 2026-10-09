#!/usr/bin/env bash
# Seeds the local dev-mode Vault (docker-compose.yml's `vault` service)
# with this app's secrets at the path app/secrets_provider.py reads by
# default. Runs the `vault` CLI INSIDE the container (via `docker
# compose exec`) rather than requiring it installed locally — matches
# how this project already does everything else through Docker (see
# CLAUDE.md's Postgres setup). Dev-mode Vault is in-memory, so this
# needs re-running every time that container restarts.
#
# Usage: ./scripts/seed_vault.sh
set -euo pipefail

docker compose exec \
  -e VAULT_ADDR=http://127.0.0.1:8200 \
  -e VAULT_TOKEN=dev-only-insecure-vault-token \
  vault vault kv put secret/aesthetics-app \
  JWT_SECRET_KEY="dev-vault-managed-jwt-secret" \
  DATABASE_URL="postgresql+asyncpg://aesthetics_user:aesthetics_pass@localhost:5433/aesthetics_db"

echo "Seeded. Run the app with SECRETS_BACKEND=vault VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=dev-only-insecure-vault-token to pull from it."
