"""
Shared test setup.

DB strategy: a separate Postgres database (aesthetics_test_db) on the
same local Docker Postgres container, kept apart from your dev DB
(aesthetics_db) so running tests never touches data you're looking at
in manual testing. Tables are built straight from the SQLAlchemy models
(Base.metadata.create_all), not through Alembic — fast, and keeps
"does the app's schema work" separate from "does the migration file
work" (that's covered by tests/unit/test_alembic_support.py instead).

Talking to the app: app/database.py builds its real `engine` once, at
import time, pointed at the dev DB from settings.database_url — that
already happened by the time tests run, so we can't redirect it by
changing settings afterward. Instead we override FastAPI's `get_db`
dependency (see `app.dependency_overrides` below) so every request made
through the test client gets a session bound to the test DB instead.
"""
import asyncio

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import user, provider_profile, booking, review, portfolio_media, provider_availability, message, identity_verification  # noqa: F401  (import so Base knows about the tables)

TEST_DB_NAME = "aesthetics_test_db"
TEST_DATABASE_URL = f"{settings.database_url.rsplit('/', 1)[0]}/{TEST_DB_NAME}"
# asyncpg's own connect() wants a plain "postgresql://" URL, not SQLAlchemy's "postgresql+asyncpg://"
ADMIN_DATABASE_URL = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


# NullPool: tests span multiple event loops (a throwaway one in the
# session-setup fixture below via asyncio.run(), then pytest-asyncio's own
# loop for each test). asyncpg connections are tied to the loop that
# created them, so a normal pool trying to reuse one across loops raises
# "cannot perform operation: another operation is in progress" or similar.
# NullPool opens a fresh low-level connection per checkout instead of
# caching one, which sidesteps the whole problem.
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def _ensure_test_database_exists() -> None:
    conn = await asyncpg.connect(ADMIN_DATABASE_URL)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    asyncio.run(_ensure_test_database_exists())

    async def _create_schema():
        async with test_engine.begin() as conn:
            # Fresh CREATE DATABASE has no PostGIS; the Geography column on
            # provider_profiles can't be created without the extension.
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            # drop_all first: create_all only creates MISSING tables, it
            # never alters existing ones. Without this, a test DB left
            # over from before a model change (e.g. a new column) keeps
            # its stale schema and every test making a real query starts
            # failing with "column ... does not exist" — confusing, since
            # nothing about the failure points at "your test DB is stale".
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create_schema())
    yield
    asyncio.run(test_engine.dispose())


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables():
    """Runs before every test so one test's data can't leak into the
    next. TRUNCATE ... CASCADE clears identity_verifications, messages,
    provider_availability, portfolio_media, reviews, bookings,
    provider_profiles and users in one statement regardless of the FKs
    between them."""
    async with test_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE identity_verifications, messages, provider_availability, "
                "portfolio_media, reviews, bookings, provider_profiles, users RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest_asyncio.fixture(autouse=True)
async def _reset_rate_limiter():
    """Without this, slowapi's in-memory counters (shared by the one
    `app` instance imported once for the whole test session, not
    recreated per-test) would carry over between tests — e.g. the
    5/minute login limit would start rejecting logins partway through the
    suite, not because of anything a given test did, but because of what
    every prior test already did."""
    app.state.limiter.reset()
    yield


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = _override_get_db


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def register_user(client, email, password="secret123", role="customer", full_name="Test User"):
    response = await client.post(
        "/v1/users/",
        json={"email": email, "password": password, "full_name": full_name, "role": role},
    )
    return response


async def login(client, email, password="secret123"):
    response = await client.post("/v1/auth/login", data={"username": email, "password": password})
    return response.json()["access_token"]
