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
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import Response

from app.config import settings
from app.database import engine
from app.errors import AppError, ErrorCode, build_field_errors, fallback_error_code
from app.logging_config import configure_logging
from app.rate_limit import limiter
from app.request_context import current_user_id_var, request_id_var
from app.routers import v1
from app.schemas.error import ErrorResponse

# Called at import time, before any route module below can log anything —
# uvicorn configures its own "uvicorn"/"uvicorn.access" loggers separately
# and isn't affected by this (it never touches the root logger), so its
# access/error logs keep working unchanged alongside ours.
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="Aesthetics App API")

# app.add_middleware() builds a LIFO stack (the most-recently-added call
# ends up OUTERMOST, closest to the client) — so GZip is added FIRST here
# even though rate limiting is conceptually "more outer." That's
# deliberate: GZipMiddleware's minimum_size check breaks (compresses
# every response regardless of size) if the layer directly beneath it is
# itself BaseHTTPMiddleware-based — which SlowAPIMiddleware is. Adding
# GZip first means it wraps the router directly, with nothing
# BaseHTTPMiddleware-shaped in between; verified empirically (not just
# reasoned about), since this is a real, reproducible Starlette gotcha,
# not a hypothetical one — see tests/regression/test_response_compression.py.
#
# Compresses response bodies over minimum_size when the client sends
# Accept-Encoding: gzip — cuts bandwidth egress on JSON responses
# (search/review/message listings) for free. Starlette's GZipMiddleware
# already excludes image/video content-types by default, so it won't
# waste CPU re-compressing already-compressed /media bytes.
app.add_middleware(GZipMiddleware, minimum_size=500)

# Rate limiting (see app/rate_limit.py for the limiter itself and its
# single-instance caveat). app.state.limiter is where slowapi's
# @limiter.limit(...) decorator (used in routers/auth.py, routers/users.py)
# looks up the shared limiter instance; the exception handler turns a
# limit breach into a proper 429 instead of an unhandled error; the
# middleware applies `default_limits` to every route that doesn't
# override it with its own @limiter.limit(...).
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


# Every error response gets a stable, machine-readable `error_code`
# alongside the existing human-readable `detail` (always a string —
# see app/errors.py's docstring) and a `request_id` for support/log
# correlation. Each handler also sets request.state.error_code so the
# log_requests middleware below can include it on the SAME log line
# as the rest of that request's outcome, rather than logging a second,
# separate line here.
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request.state.error_code = exc.error_code.value
    content: dict[str, object] = {
        "error_code": exc.error_code.value,
        "detail": exc.detail,
        "request_id": request_id_var.get(),
    }
    if exc.params is not None:
        content["params"] = exc.params
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request.state.error_code = ErrorCode.validation_failed.value
    return JSONResponse(
        status_code=422,
        content={
            "error_code": ErrorCode.validation_failed.value,
            "detail": "One or more fields are invalid",
            # Per-field detail as data, not text — see
            # app/errors.py's build_field_errors for why `input` is
            # deliberately never included (it's the raw submitted
            # value for ANY field, a password included).
            "fields": build_field_errors(exc.errors()),
            "request_id": request_id_var.get(),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_fallback_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Catches every plain HTTPException not yet migrated to AppError
    — registered against Starlette's OWN base HTTPException class,
    not fastapi.HTTPException (a subclass of it), because Starlette's
    router raises the BASE class directly for cases that never reach
    application code at all: an unmatched route (404) or a wrong
    method (405). Registering against the subclass alone misses both
    — confirmed empirically (`fastapi.HTTPException is
    starlette.exceptions.HTTPException` is False) before this fix;
    they used to return the framework's raw `{"detail": "Not Found"}`
    with no error_code at all. Never reached for AppError itself:
    that's a more specific subclass with its own handler above, which
    Starlette's dispatch always prefers over a base-class handler."""
    request.state.error_code = fallback_error_code(exc.status_code).value
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": fallback_error_code(exc.status_code).value,
            "detail": str(exc.detail),
            "request_id": request_id_var.get(),
        },
        headers=exc.headers,
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    request.state.error_code = ErrorCode.rate_limited.value
    content: dict[str, object] = {
        "error_code": ErrorCode.rate_limited.value,
        "detail": "Too many requests, try again later",
        "request_id": request_id_var.get(),
    }
    retry_after_seconds = _retry_after_seconds(request)
    if retry_after_seconds is not None:
        content["params"] = {"retry_after_seconds": retry_after_seconds}
    response = JSONResponse(status_code=429, content=content)
    # Set directly rather than via limiter._inject_headers(): that
    # method only works with Limiter(headers_enabled=True), and turning
    # that on globally breaks slowapi's own internal per-route wrapper
    # (used by the @limiter.limit(...) overrides on login/signup) in
    # this environment. retry_after_seconds is already computed
    # independently above, so the header and the body's params can
    # never disagree.
    if retry_after_seconds is not None:
        response.headers["Retry-After"] = str(retry_after_seconds)
    return response


def _retry_after_seconds(request: Request) -> int | None:
    current_limit = getattr(request.state, "view_rate_limit", None)
    if current_limit is None:
        return None
    # Mirrors slowapi's own Limiter._inject_headers calculation
    # exactly, so the body's retry_after_seconds and the Retry-After
    # header it sets can never disagree. The login rate limiter (and
    # every other one in this app) is keyed purely by client IP (see
    # app/rate_limit.py) — never by account/email — so this can never
    # become a side channel revealing account-lockout state.
    window_stats = limiter.limiter.get_window_stats(current_limit[0], *current_limit[1])
    return max(0, int(1 + window_stats[0] - time.time()))


#: Status codes that are normal, expected churn rather than something
#: worth a human noticing at WARNING volume — a bad/expired token, a
#: bad id, a typo in a form. See log_requests below.
_INFO_LEVEL_STATUS_CODES = frozenset({401, 404, 422})
#: Status codes worth a closer look even though they're not server
#: errors: a permissions mismatch, a conflict, or being rate-limited.
_WARNING_LEVEL_STATUS_CODES = frozenset({403, 409, 429})


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Reuse a caller-supplied X-Request-ID (useful once there's a load
    # balancer/API gateway in front of this assigning its own) instead of
    # always minting a fresh one, so a request can be traced end-to-end
    # across multiple hops, not just within this service.
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request_id_token = request_id_var.set(request_id)
    # Reset to the default at the START of every request too, not just
    # the end (see the finally block) — belt-and-suspenders against any
    # stale value if a context ever got reused across requests.
    user_id_token = current_user_id_var.set("-")
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
        status_code = response.status_code
        # Level follows outcome, not path: a successful request (2xx/3xx)
        # is DEBUG, not INFO — meaningful business events (booking created,
        # review posted, login, ...) already get a purpose-built INFO log
        # with real context from whichever router handled them, so a
        # generic "METHOD /path -> 200" line for every single request
        # would otherwise dominate production logs without adding
        # information. Among error responses, level reflects how notable
        # the CODE is, not just ">= 400": a bad/expired token or a typo'd
        # form field (401/404/422) is normal, expected churn at INFO; a
        # permissions mismatch, conflict or rate limit (403/409/429) is
        # worth a closer look at WARNING; anything else 4xx defaults to
        # WARNING too (the old blanket behavior); 5xx is always ERROR.
        if status_code >= 500:
            level = logging.ERROR
        elif status_code in _INFO_LEVEL_STATUS_CODES:
            level = logging.INFO
        elif status_code in _WARNING_LEVEL_STATUS_CODES or status_code >= 400:
            level = logging.WARNING
        else:
            level = logging.DEBUG
        # Set by an AppError/validation/fallback/rate-limit handler
        # (see above) when this request ended in an error — absent for
        # a successful response, in which case RequestIdFilter's own
        # getattr-based default ("-") fills the log line's placeholder.
        error_code = getattr(request.state, "error_code", None)
        extra = {"error_code": error_code} if error_code is not None else {}
        logger.log(
            level,
            "%s %s -> %d (%.1fms)",
            request.method, request.url.path, status_code, duration_ms,
            extra=extra,
        )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(request_id_token)
        current_user_id_var.reset(user_id_token)


@app.middleware("http")
async def cache_immutable_media(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/media/"):
        # Filenames under /media are always server-generated UUIDs (see
        # app/storage.py) and never change content once uploaded — safe
        # to tell browsers/any future CDN to cache forever instead of
        # re-fetching the same bytes on every view, which is pure repeat
        # bandwidth cost for no benefit (the content literally cannot
        # change without the URL changing too).
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Baseline hardening headers, applied to every response. No
    Content-Security-Policy here, deliberately: a CSP strict enough to
    mean anything would need real tuning to not break /docs's Swagger UI
    (it loads its JS/CSS from a CDN), and the actual exploitability of
    missing CSP on a pure JSON API is low — there's no page here
    rendering user-controlled content as HTML for an XSS payload to run
    in. Revisit if/when a web frontend served by this app exists."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # Safe to send unconditionally: a browser that receives this over
    # plain HTTP (e.g. local dev) just ignores it per spec — HSTS only
    # takes effect on a response actually delivered over HTTPS.
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Every feature router is assembled under /v1 in app/routers/v1.py — see
# that file for why (URL-path versioning) and for the route-ordering
# notes that still apply within it (/search vs /{profile_id}, /as-customer
# vs /{booking_id}). Health checks and static media are deliberately NOT
# versioned (see below) — they're infrastructure, not the API contract.
app.include_router(v1.router)

#: Status codes documented as returning the error envelope on every
#: path, by default — not all of these are actually reachable on
#: every single endpoint (e.g. a GET with no body can't 422), but
#: documenting them uniformly is simpler and more honest than hand-
#: curating per endpoint, and a generated TypeScript client only
#: needs the shape to exist somewhere it can import from.
_ERROR_RESPONSE_STATUS_CODES = ("400", "401", "403", "404", "409", "422", "429")


def custom_openapi() -> dict:
    """Adds ErrorResponse/FieldError to the generated OpenAPI schema's
    components and a default `responses` entry for every error status
    code on every path, so a client generated from this schema
    (openapi-typescript — see docs/frontend-brief.md) has a typed
    shape for every error response, not just the happy path FastAPI
    documents automatically from each route's response_model."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)

    error_response_schema = ErrorResponse.model_json_schema(ref_template="#/components/schemas/{model}")
    field_error_schema = error_response_schema.pop("$defs")["FieldError"]
    components_schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    components_schemas["ErrorResponse"] = error_response_schema
    components_schemas["FieldError"] = field_error_schema

    error_response_ref = {
        "description": "Error",
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}},
    }
    for methods in schema.get("paths", {}).values():
        for operation in methods.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.setdefault("responses", {})
            for status_code in _ERROR_RESPONSE_STATUS_CODES:
                if status_code == "422":
                    # FastAPI auto-documents 422 as HTTPValidationError
                    # for every route with request validation — stale
                    # now that validation_error_handler always returns
                    # our ErrorResponse shape instead, so overwrite
                    # rather than setdefault.
                    responses[status_code] = error_response_ref
                else:
                    responses.setdefault(status_code, error_response_ref)

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi  # type: ignore[method-assign]

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
        # from None: the real exception is already captured above by
        # logger.exception (full traceback, server-side only) — chaining
        # it onto the client-facing HTTPException too would be redundant,
        # not additionally informative.
        raise HTTPException(status_code=503, detail="Database unreachable") from None
    return {"status": "ok", "database": "ok"}
