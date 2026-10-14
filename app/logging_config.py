"""
Central logging setup for the whole app — configure_logging() is called
once, at import time in app/main.py, before anything else logs. Every
other module just does `logger = logging.getLogger(__name__)` and uses it
normally; module loggers propagate up to the root logger configured here,
so there's one place controlling format/level/output instead of each
module wiring up its own handler.

Deliberately plain-text output, not structured/JSON, for now — easier to
read in a local dev console, and there's no log aggregator (CloudWatch,
Datadog, ELK) consuming these yet. Swapping the "default" formatter below
for a JSON one is a contained, one-file change whenever that's needed —
nothing else has to change, since every other module only ever calls
logging.getLogger(__name__).

Never log secrets or full request/response bodies here or anywhere else
that uses this logger setup: no passwords, no JWTs/Authorization headers,
no raw user-generated message content. See the per-call comments in
routers/security.py for where this is actually enforced.
"""
import logging
import logging.config

from app.request_context import current_user_id_var, request_id_var


class RequestIdFilter(logging.Filter):
    """Injects per-request context into every log record: the
    correlation id and current user id (both contextvars, see
    app/request_context.py — "-" when not set, e.g. before auth
    resolves) and error_code. error_code is call-site-specific, not a
    contextvar — only app/main.py's request-outcome log line ever
    passes one via `extra={"error_code": ...}`; every other call site
    gets the same "-" default via getattr below, so the format string
    can include the placeholder unconditionally without every log
    call in the app needing to supply it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = current_user_id_var.get()
        if not hasattr(record, "error_code"):
            record.error_code = "-"
        return True


def configure_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {"()": RequestIdFilter},
            },
            "formatters": {
                "default": {
                    "format": (
                        "%(asctime)s %(levelname)-8s [%(request_id)s] "
                        "[user=%(user_id)s] [error=%(error_code)s] %(name)s: %(message)s"
                    ),
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "filters": ["request_id"],
                },
            },
            "root": {
                "handlers": ["console"],
                "level": level,
            },
            "loggers": {
                # SQLAlchemy's engine logger emits one line per SQL
                # statement at INFO when app/database.py's echo=True (dev
                # only) — leave it at INFO regardless of our own app-wide
                # level so DEBUG elsewhere doesn't also pull in per-row
                # parameter binding, which echo doesn't even log at INFO
                # but would at DEBUG.
                "sqlalchemy.engine": {"level": "INFO"},
            },
        }
    )
