"""
Entry point. Run with: uvicorn app.main:app --reload

Schema changes now go through Alembic migrations (see /alembic) instead
of Base.metadata.create_all() — run `alembic upgrade head` to bring a
database up to date. Run it once against a fresh DB before starting the
app; the app itself no longer creates tables on startup.
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import users, providers, auth, bookings

app = FastAPI(title="Aesthetics App API")

app.include_router(users.router)
app.include_router(providers.router)
app.include_router(auth.router)
app.include_router(bookings.router)

# Local-disk portfolio media (see app/storage.py), served directly as
# static files. check_dir=False: a fresh checkout has no media/ directory
# yet (nothing uploaded), and StaticFiles would otherwise fail app
# startup over a directory that's created lazily on first upload.
app.mount("/media", StaticFiles(directory=settings.media_root, check_dir=False), name="media")


@app.get("/health")
async def health_check():
    return {"status": "ok"}
