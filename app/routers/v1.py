"""
Aggregates every feature router under a single /v1 prefix.

URL-path versioning (not a header like `Accept: application/vnd.foo.v1+json`)
— the simplest scheme to reason about from a mobile client, visible in
logs/traces without inspecting headers, and the standard choice for an
API like this one. Picked now, before any real client exists: once a
mobile app is installed on real phones, you can't force-update it the
way you can redeploy a web frontend, so a breaking change with no
versioning would strand whoever hasn't updated yet. Easier to establish
the convention before v1 has real traffic than to retrofit it onto a
live API later.

Health checks (/health, /health/ready) and static media (/media) are
deliberately mounted directly on `app` in app/main.py, NOT included here
— they're infrastructure/asset endpoints, not part of the versioned API
contract. A load balancer's health-check config shouldn't need to change
just because the API moved to /v2.

When a v2 is eventually needed: a new app/routers/v2.py assembling
whichever routers v2 actually changes (re-exporting the v1 ones unchanged
where nothing did), both included side by side in app/main.py. Nothing
about this structure forces an all-or-nothing rewrite — that's a
per-router decision made when it actually happens.
"""
from fastapi import APIRouter

from app.routers import (
    admin,
    auth,
    bookings,
    messages,
    portfolio,
    provider_availability,
    providers,
    reports,
    reviews,
    users,
    verification,
)

router = APIRouter(prefix="/v1")

router.include_router(users.router)
router.include_router(providers.router)
router.include_router(provider_availability.router)
router.include_router(portfolio.router)
router.include_router(auth.router)
router.include_router(bookings.router)
router.include_router(reviews.router)
router.include_router(messages.router)
router.include_router(verification.router)
router.include_router(reports.router)
router.include_router(admin.router)
