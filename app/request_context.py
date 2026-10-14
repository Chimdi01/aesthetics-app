"""
Per-request context, set once per incoming HTTP request and read by
every log line emitted while that request is being handled (see
RequestIdFilter in app/logging_config.py).

contextvars.ContextVar, not a plain module-level variable — it has to
stay correct across concurrently in-flight requests sharing one asyncio
event loop, and a plain global would get overwritten by whichever request
set it last. ASGI servers (uvicorn) run each request in its own context,
so each request sees only the values it set.
"""
import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

# Set inside app/security.py's get_current_user, once a token resolves
# to a real user — "-" (matching request_id_var's own default) for any
# request that never authenticates, most 401s included, rather than
# None, so a single %s-style log format string works for both cases.
current_user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("current_user_id", default="-")
