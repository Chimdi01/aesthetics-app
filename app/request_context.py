"""
A per-request correlation id, set once per incoming HTTP request (see the
middleware in app/main.py) and read by every log line emitted while that
request is being handled (see RequestIdFilter in app/logging_config.py).

A contextvars.ContextVar, not a plain module-level variable — it has to
stay correct across concurrently in-flight requests sharing one asyncio
event loop, and a plain global would get overwritten by whichever request
set it last. ASGI servers (uvicorn) run each request in its own context,
so each request sees only the id it set.
"""
import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
