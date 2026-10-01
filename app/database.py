"""
Sets up the connection to Postgres. We use SQLAlchemy's ASYNC engine
(not the classic sync one) because FastAPI is async-native — using a
blocking database driver would defeat the point of an async framework
once you have real concurrent traffic.

Base: every model class inherits from this so SQLAlchemy knows about it.
get_db: a "dependency" FastAPI injects into route functions, giving each
        request its own database session and cleaning it up afterward.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=(settings.environment == "development"),
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    # Checks a pooled connection is still alive before handing it to a
    # request, instead of that request failing with a stale-connection
    # error (e.g. Postgres closed it after an idle timeout) — cheap
    # insurance that matters more as connection churn grows with traffic.
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
