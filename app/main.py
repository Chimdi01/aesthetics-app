"""
Entry point. Run with: uvicorn app.main:app --reload

Schema changes now go through Alembic migrations (see /alembic) instead
of Base.metadata.create_all() — run `alembic upgrade head` to bring a
database up to date. Run it once against a fresh DB before starting the
app; the app itself no longer creates tables on startup.
"""
from fastapi import FastAPI

from app.routers import users, providers, auth, bookings

app = FastAPI(title="Aesthetics App API")

app.include_router(users.router)
app.include_router(providers.router)
app.include_router(auth.router)
app.include_router(bookings.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
