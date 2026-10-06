"""
Entry point. Run with: uvicorn app.main:app --reload

Schema changes now go through Alembic migrations (see /alembic) instead
of Base.metadata.create_all() — run `alembic upgrade head` to bring a
database up to date. Run it once against a fresh DB before starting the
app; the app itself no longer creates tables on startup.
"""
import logging
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.logging_config import configure_logging
from app.rate_limit import limiter
from app.request_context import request_id_var
from app.routers import v1

# Called at import time, before any route module below can log anything —
# uvicorn configures its own "uvicorn"/"uvicorn.access" loggers separately
# and isn't affected by this (it never touches the root logger), so its
# access/error logs keep working unchanged alongside ours.
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Aesthetics App API")

# Rate limiting (see app/rate_limit.py for the limiter itself and its
# single-instance caveat). app.state.limiter is where slowapi's
# @limiter.limit(...) decorator (used in routers/auth.py, routers/users.py)
# looks up the shared limiter instance; the exception handler turns a
# limit breach into a proper 429 instead of an unhandled error; the
# middleware applies `default_limits` to every route that doesn't
# override it with its own @limiter.limit(...).
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Reuse a caller-supplied X-Request-ID (useful once there's a load
    # balancer/API gateway in front of this assigning its own) instead of
    # always minting a fresh one, so a request can be traced end-to-end
    # across multiple hops, not just within this service.
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        # logger.exception (not logger.error) captures the full traceback —
        # without this, an unhandled exception's only record is whatever
        # uvicorn prints to stderr, with no request id to correlate it
        # against the rest of that request's log lines.
        logger.exception(
            "%s %s -> unhandled exception (%.1fms)", request.method, request.url.path, duration_ms
        )
        raise
    else:
        duration_ms = (time.perf_counter() - start) * 1000
        # Level follows outcome, not path: a successful request (2xx/3xx)
        # is DEBUG, not INFO. Meaningful business events (booking created,
        # review posted, login, ...) already get a purpose-built INFO log
        # with real context from whichever router handled them — a generic
        # "METHOD /path -> 200" line for every single request (every
        # search, every profile view, every health-check poll) would
        # otherwise dominate production logs at any real traffic volume
        # without adding information over those. 4xx/5xx stay visible
        # above DEBUG regardless of path, since those ARE actionable
        # regardless of volume.
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        else:
            level = logging.DEBUG
        logger.log(
            level, "%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, duration_ms
        )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(token)

# Every feature router is assembled under /v1 in app/routers/v1.py — see
# that file for why (URL-path versioning) and for the route-ordering
# notes that still apply within it (/search vs /{profile_id}, /as-customer
# vs /{booking_id}). Health checks and static media are deliberately NOT
# versioned (see below) — they're infrastructure, not the API contract.
app.include_router(v1.router)

# Local-disk portfolio media (see app/storage.py), served directly as
# static files. check_dir=False: a fresh checkout has no media/ directory
# yet (nothing uploaded), and StaticFiles would otherwise fail app
# startup over a directory that's created lazily on first upload.
app.mount("/media", StaticFiles(directory=settings.media_root, check_dir=False), name="media")


@app.get("/health")
async def health_check():
    """Liveness: is the process up at all. No dependency checks — must
    stay cheap and fast, since an orchestrator restarts the process on
    repeated failures here, which doesn't help if e.g. the database (not
    this process) is the thing that's actually down."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness_check():
    """Readiness: can this instance actually serve a real request right
    now. Checks the one hard dependency (Postgres) — a process can be
    alive (health_check above passes) but unable to do anything useful if
    its database is unreachable, and a load balancer/orchestrator should
    stop routing traffic here in that case rather than leave it serving
    errors to real users."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed: database unreachable")
        raise HTTPException(status_code=503, detail="Database unreachable")
    return {"status": "ok", "database": "ok"}
