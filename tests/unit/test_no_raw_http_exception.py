"""
Guard test: every error response must get an error_code (see
app/errors.py's docstring), which means every raise site should use
AppError, not a bare HTTPException. This fails loudly if new code adds
one outside the whitelist below, rather than silently falling back to
the generic by-status-code mapping.

The whitelist is the migration's own punch list — see
docs/backend-slices.md Slice 1 Step 1's four batches. Each batch
removes its files from here; by the end of the migration this list is
empty and the comment block below can go too.
"""
import re
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"

# Files still using a bare `HTTPException(...)` construction, grouped
# by the batch that will migrate them (docs/backend-slices.md). Remove
# each file's entry as its batch lands — if this list is wrong (a file
# listed here no longer needs to be, or a file not listed here does),
# the test below fails either way, so it can't silently go stale.
_NOT_YET_MIGRATED = {
    # Batch 2: bookings, reviews and messages.
    "booking_access.py",
    "routers/bookings.py",
    "routers/reviews.py",
    "routers/messages.py",
    # Batch 3: admin, users, verification and storage.
    "routers/admin.py",
    "routers/users.py",
    "routers/verification.py",
    "routers/provider_availability.py",  # shares a "provider profile not found" pattern with the above
    "routers/portfolio.py",
    "routers/providers.py",
    "storage.py",
    "verification_storage.py",
    # Batch 4: the rest.
    "routers/reports.py",
    # Deliberately permanent, not a migration gap: /health/ready isn't
    # part of the versioned API contract (see CLAUDE.md) — same reason
    # it's excluded from the OpenAPI error-response schemas in
    # app/main.py's custom_openapi().
    "main.py",
}

_CONSTRUCTION_PATTERN = re.compile(r"HTTPException\(")


def _files_with_raw_http_exception() -> set[str]:
    found = set()
    for path in APP_ROOT.rglob("*.py"):
        if path.name == "errors.py":
            continue  # the one file allowed to define/subclass it
        text = path.read_text()
        if _CONSTRUCTION_PATTERN.search(text):
            found.add(str(path.relative_to(APP_ROOT)))
    return found


def test_raw_http_exception_only_appears_in_the_known_whitelist():
    found = _files_with_raw_http_exception()
    unexpected = found - _NOT_YET_MIGRATED
    assert not unexpected, (
        f"New bare HTTPException(...) construction(s) outside the whitelist: {unexpected}. "
        "Use AppError (app/errors.py) instead, or add the file to _NOT_YET_MIGRATED "
        "with a comment explaining why, if it's a deliberate, permanent exception."
    )


def test_whitelist_has_no_stale_entries():
    # The other direction: a file listed as "not yet migrated" that's
    # actually clean should be removed from the list, not left behind
    # as a silently-irrelevant entry.
    found = _files_with_raw_http_exception()
    stale = _NOT_YET_MIGRATED - found
    assert not stale, f"These whitelist entries no longer construct HTTPException(...) — remove them: {stale}"
