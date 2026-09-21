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

    class Config:
        env_file = ".env"


# Created once, imported everywhere else that needs settings.
settings = Settings()
