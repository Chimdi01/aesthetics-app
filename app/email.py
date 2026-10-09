"""
Email-sending abstraction. Isolated here exactly the way app/storage.py
isolates file storage: every other module calls send_email(...) and
knows nothing about HOW the email actually gets sent. Swapping in a real
provider (SES/SendGrid/Postmark — needs an external account/credentials
first, same reasoning as Stripe in CLAUDE.md, not something to build
blind) means rewriting the body of send_email() in this one file;
nothing in app/routers/auth.py or anywhere else that calls it changes.

Current implementation ("console"): logs the email instead of actually
sending it — a deliberate placeholder so email verification and
password reset can be built, tested, and used in local dev right now,
without waiting on a provider decision. In dev/test, the
verification/reset LINK itself shows up in this log line — that's how
you "receive" the email locally.
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, body: str) -> None:
    if settings.email_backend == "console":
        # INFO, not DEBUG: right now this is the only way to see a
        # verification/reset link in local dev, so it needs to be
        # visible at the normal run level, not hidden behind
        # LOG_LEVEL=DEBUG. Email bodies here are always ones THIS app
        # generated (a verification link, a reset link) — never
        # user-authored content, so this doesn't run into the "never log
        # user-generated content" rule in app/logging_config.py.
        logger.info("Email to %s | subject: %s\n%s", to, subject, body)
        return
    # Real providers plug in here later, each as its own branch (or its
    # own module this dispatches to) — not written yet, since no
    # account/credentials exist for any of them.
    raise NotImplementedError(f"Unknown email backend: {settings.email_backend!r}")
