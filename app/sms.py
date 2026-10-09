"""
SMS-sending abstraction — isolated here exactly the way app/email.py
isolates email sending. Every other module calls send_sms(...) and
knows nothing about HOW the text actually gets sent. Swapping in a real
provider (Twilio/Vonage/AWS SNS — needs an external account/credentials
first, same reasoning as Stripe/email in CLAUDE.md, not something to
build blind) means rewriting the body of send_sms() in this one file.

Current implementation ("console"): logs the text instead of actually
sending it — same placeholder posture as app/email.py's console
backend, so notifications can be built, tested, and used in local dev
right now, without waiting on a provider decision.
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def send_sms(to: str, body: str) -> None:
    if settings.sms_backend == "console":
        # INFO, not DEBUG — same reasoning as app/email.py: this is
        # currently the only way to "receive" a text in local dev.
        logger.info("SMS to %s: %s", to, body)
        return
    raise NotImplementedError(f"Unknown SMS backend: {settings.sms_backend!r}")
