# Secrets rotation runbook

Every secret this app uses, what rotating it actually does, and the
step-by-step procedure — both for routine rotation (no suspected
compromise, just good hygiene) and emergency rotation (a secret is
known or suspected to have leaked, e.g. a `gitleaks` CI finding, a
compromised deploy pipeline, a leaked laptop).

None of these secrets are in a vault (AWS Secrets Manager, HashiCorp
Vault, etc.) yet — they're plain environment variables (`.env` locally,
real env vars in production). This runbook assumes manual rotation;
moving to a vault with automatic rotation is the natural next step
before real launch, but needs a hosting decision first (see
`CLAUDE.md`), so it isn't built now.

## `JWT_SECRET_KEY`

**What it protects:** signs and verifies every access token. This is
the single most sensitive secret in the app — anyone who has it can
forge a valid access token for ANY user, any role, instantly, with no
other access needed.

**Rotation support already built** (`app/security.py`): verification
tries `JWT_SECRET_KEY` first, then each key listed in
`JWT_PREVIOUS_SECRET_KEYS` (comma-separated), in order. New tokens are
always signed with `JWT_SECRET_KEY` only — `JWT_PREVIOUS_SECRET_KEYS`
exists purely so an access token signed BEFORE a rotation keeps
verifying until it naturally expires, instead of every active user
being logged out the instant you rotate.

**Routine rotation** (e.g. quarterly, no suspected leak):
1. Move the current `JWT_SECRET_KEY` value into `JWT_PREVIOUS_SECRET_KEYS`.
2. Generate a new one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
3. Set that as the new `JWT_SECRET_KEY`. Deploy with both set.
4. Wait at least `ACCESS_TOKEN_EXPIRE_MINUTES` (default 60) plus a
   safety margin (e.g. 24h, to cover clock skew and any client that
   cached a token a little past its nominal expiry) for every
   old-signed access token to have naturally expired.
5. Remove the old key from `JWT_PREVIOUS_SECRET_KEYS`. Deploy again.

**Emergency rotation** (suspected leak):
1. Generate a new `JWT_SECRET_KEY` immediately. Deploy with **only**
   the new key set — do NOT add the compromised key to
   `JWT_PREVIOUS_SECRET_KEYS`. That would still accept forged tokens
   signed with the leaked key, defeating the entire point.
2. This invalidates every access token everywhere, immediately. That's
   expected and correct, not a side effect to work around.
3. Refresh tokens are **not** affected — they're not JWTs at all (see
   `app/refresh_tokens.py`: opaque, random, DB-backed, only their hash
   stored). Every legitimate client with a valid, un-revoked refresh
   token gets a new access token (signed with the new key) on its next
   `POST /v1/auth/refresh` call, with no need to re-enter a password.
   This is exactly why access tokens are short-lived and refresh tokens
   carry actual session continuity — a JWT-key rotation is a one-time
   silent refresh for everyone legitimate, not a mass logout.
4. If the compromise might also extend to the database (not just the
   JWT key alone — e.g. a DB leak), additionally revoke refresh tokens
   for every affected user via `revoke_all_refresh_tokens_for_user`
   (currently exposed per-user through `POST /v1/auth/logout-all`;
   there's no single "revoke everyone, platform-wide" admin action
   today — flagged here as a gap, not built, since it's a severe/rare
   enough scenario that it hasn't been worth the extra API surface yet).

## Database credentials (`DATABASE_URL`)

**What it protects:** direct read/write access to the entire database —
the highest-blast-radius secret if leaked (every user, booking, review,
message; verification-document *file paths*, though not the documents
themselves, which live on disk under `settings.verification_root`, not
in the DB).

**Rotation:** `ALTER USER aesthetics_user WITH PASSWORD '...';` against
Postgres, update `DATABASE_URL`, restart the app. No in-app code support
needed or applicable — this is a connection-string credential, not
something the app verifies against multiple valid values the way the
JWT key does.

**Emergency:** same procedure, done immediately. Also check whatever
connection/access logs the hosting provider exposes for connections from
unexpected sources during the suspected window.

## Email provider API key

Not applicable yet — `app/email.py` only has a `"console"` backend (logs
instead of sending; no provider account exists). Once a real provider
(SES/SendGrid/Postmark) is wired in: rotation is provider-side (revoke
and regenerate in their dashboard), then update whichever env var that
backend reads, then restart. No in-app multi-key support needed — unlike
the JWT key, a leaked email-provider key mostly risks someone sending
email *as* this app, which the provider's own dashboard/sending-limits
typically contain; it doesn't grant account takeover the way a leaked
JWT key or DB credential does. Revoke the leaked key at the provider
immediately regardless of whether a replacement is ready yet.

## General

- `gitleaks` (CI's `secrets-scan` job, see `CLAUDE.md`) is the main
  automated defense against a secret landing in git history in the
  first place. If it ever fires on a real finding (not a false
  positive), treat whichever secret it flagged as needing **emergency**
  rotation, not routine. Deleting the commit afterward doesn't undo the
  exposure — anyone who already cloned the repo (or any CI runner,
  cache, or fork) still has the old history with the secret in it.
- Rotating a secret doesn't retroactively protect anything already
  taken with the old one (data already exfiltrated, actions already
  performed) — rotation stops *future* misuse of that credential, it's
  not an undo button.
