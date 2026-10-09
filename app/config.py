"""
Central place for all configuration. Everything comes from environment
variables (loaded from a .env file locally, or real env vars in production)
so we never hardcode secrets like database passwords into the codebase.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://aesthetics_user:aesthetics_pass@localhost:5433/aesthetics_db"
    environment: str = "development"

    # Dev-only default so the app runs out of the box. Any real deployment
    # MUST override this via a JWT_SECRET_KEY env var — anyone who has this
    # value can forge valid login tokens for any user.
    jwt_secret_key: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

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

    class Config:
        env_file = ".env"


# Created once, imported everywhere else that needs settings.
settings = Settings()
