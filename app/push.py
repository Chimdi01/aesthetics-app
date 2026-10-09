"""
Push-notification abstraction — isolated here exactly the way
app/email.py and app/sms.py isolate their channels. Every other module
calls send_push(...) and knows nothing about HOW the push actually gets
delivered. Swapping in a real backend (FCM for Android/web, APNs for
iOS — needs a Firebase project / Apple Developer Program enrollment
first, same reasoning as every other external-account dependency in
this codebase, not something to build blind) means rewriting the body
of send_push() in this one file.

Bigger caveat than email/SMS: this can't be exercised against a real
device at all yet, even with a real provider wired in — a device token
only exists once a real mobile app is installed and granted
notification permission, and no mobile app exists in this project yet
(see CLAUDE.md). The "console" backend below, and the DeviceToken
registry (app/models/device_token.py, app/routers/users.py's
/me/device-tokens endpoints) that feeds it, are real, tested backend
plumbing regardless — once a mobile app exists, it just needs to POST
a real token to the registration endpoint and this file gets a real
backend; nothing else in app/notifications.py or the routers that call
it changes.
"""
import logging

from app.config import settings

logger = logging.getLogger(__name__)


async def send_push(device_token: str, title: str, body: str) -> None:
    if settings.push_backend == "console":
        logger.info("Push to %s | %s: %s", device_token, title, body)
        return
    raise NotImplementedError(f"Unknown push backend: {settings.push_backend!r}")
