"""
Basic abuse protection via slowapi (built on the `limits` library).

Keyed by client IP (get_remote_address) and backed by in-memory storage
by default — correct and sufficient for a single app instance, but a
real limitation once this runs behind a load balancer across multiple
instances: each instance counts independently, which quietly raises the
real effective limit by however many instances are running. The fix at
that point is a shared Redis-backed store (slowapi takes this via
Limiter(storage_uri=...)) — a contained, one-file change here, not an
application-wide one, same pattern as app/storage.py's local-disk-to-S3
swap point.

default_limits applies to every route that isn't given a tighter
@limiter.limit(...) override (see app/routers/auth.py and
app/routers/users.py for the tighter ones on login/signup specifically).
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit_default])
