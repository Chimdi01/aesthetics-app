"""
Central place for all configuration. Everything comes from environment
variables (loaded from a .env file locally, or real env vars in production)
so we never hardcode secrets like database passwords into the codebase.

hydrate_environment() runs BEFORE Settings is defined/constructed —
see app/secrets_provider.py. It populates os.environ with secret values
fetched from whichever backend SECRETS_BACKEND names (default "env", a
no-op, since secrets are already in the environment). Settings below
then reads those same environment variables exactly as it always has;
this module never needs to know whether a value came from a real env
var, a .env file, or a vault.
"""
from pydantic_settings import BaseSettings

from app.secrets_provider import hydrate_environment

hydrate_environment()


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://aesthetics_user:aesthetics_pass@localhost:5433/aesthetics_db"
    environment: str = "development"

    # Dev-only default so the app runs out of the box. Any real deployment
    # MUST override this via a JWT_SECRET_KEY env var — anyone who has this
    # value can forge valid login tokens for any user.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    # Comma-separated — keys that are no longer used to SIGN new access
    # tokens but are still ACCEPTED when verifying one, so rotating
    # jwt_secret_key doesn't instantly break every already-issued access
    # token. app/security.py's decode_access_token() tries jwt_secret_key
    # first, then each of these in order. See SECRETS_ROTATION.md for
    # the actual rotation procedure (routine vs. emergency) — in an
    # emergency (suspected key leak), do NOT put the leaked key here;
    # leave it out entirely so tokens forged with it stop verifying
    # immediately, which is the whole point.
    jwt_previous_secret_keys: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # Refresh tokens (app/refresh_tokens.py) are deliberately much
    # longer-lived than the access token itself — the whole point of the
    # pair is "short-lived token for routine requests, long-lived token
    # that can be revoked (logout, deactivation, password reset) to get
    # a new one without forcing a password re-entry every hour."
    refresh_token_expire_days: int = 30

    # Local-disk storage for portfolio media (see app/storage.py). A path
    # relative to the project root; not meant to survive a redeploy on most
    # hosting platforms — swap this layer for S3 before a real launch.
    media_root: str = "media"
    max_upload_size_bytes: int = 25 * 1024 * 1024  # 25 MB

    # Local-disk storage for identity verification documents (see
    # app/verification_storage.py) — deliberately a SEPARATE directory
    # from media_root, never mounted as a public StaticFiles route
    # anywhere. These are government ID photos, not portfolio content;
    # mixing them into the same root as publicly-served media would make
    # "is this one actually private" a fact you have to remember per file
    # instead of a fact that's true of the whole directory.
    verification_root: str = "verification_documents"

    # DB connection pool, per app process/instance. These are conservative
    # dev-appropriate defaults, NOT a scale setting to crank up — the real
    # constraint is (number of app instances x db_pool_size) staying under
    # Postgres's max_connections (default 100). At enough concurrent app
    # instances that this math gets tight, the fix is a connection pooler
    # (e.g. PgBouncer) in front of Postgres, not a bigger pool_size here.
    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout: int = 30

    # DEBUG locally when chasing something specific; INFO is the normal
    # run level (see app/logging_config.py for what each level is used for
    # across the app).
    log_level: str = "INFO"

    # The global safety-net rate limit applied to every route that doesn't
    # have its own tighter @limiter.limit(...) (see app/rate_limit.py).
    # Configurable, not hardcoded, specifically so a load test run from a
    # single machine (and therefore a single client IP, which is what
    # slowapi keys on) can raise this without touching code — every VU in
    # a local k6 run shares one real IP, so the per-IP default would
    # otherwise cap aggregate throughput at 200/minute regardless of how
    # much headroom the app/DB actually have. Never override this in a
    # real deployment; it exists for local load testing, not production
    # tuning.
    rate_limit_default: str = "200/minute"

    # app/email.py's swap point: "console" logs the email instead of
    # sending it (see that module's docstring) — the only backend built
    # so far, since no email-provider account/credentials exist yet.
    # A real deployment MUST override this once one does; left as
    # "console" here would mean verification/reset links never actually
    # reach a real user.
    email_backend: str = "console"
    # app/sms.py's swap point — same reasoning/posture as email_backend
    # above, no SMS-provider account exists yet either.
    sms_backend: str = "console"
    # app/push.py's swap point — no FCM/APNs account exists yet either,
    # and (unlike email/SMS) no mobile app exists to generate a real
    # device token regardless of backend — see that module's docstring.
    push_backend: str = "console"
    # Where email-verification and password-reset links point — the
    # frontend route that takes the token from the URL and calls the
    # corresponding API endpoint. No frontend exists yet (see CLAUDE.md),
    # so this is a placeholder host; the FRONTEND_BASE_URL env var
    # overrides it once a real one does.
    frontend_base_url: str = "http://localhost:3000"
    # Verification links are low-stakes (worst case: someone else clicks
    # it, which just marks an email verified a little early) so a long
    # expiry favors "it still works whenever they get around to checking
    # their inbox" over tight security. Reset links grant control of the
    # account, so they expire fast on purpose.
    email_verification_token_expire_hours: int = 24
    password_reset_token_expire_minutes: int = 60

    class Config:
        env_file = ".env"


# Created once, imported everywhere else that needs settings.
settings = Settings()
