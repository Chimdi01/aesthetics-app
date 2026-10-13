"""
The categories allowlist — a plain Python collection, not a Postgres
enum, so the taxonomy can grow (e.g. new categories later) without an
ALTER TYPE migration against a live column. See CLAUDE.md's Categories
convention.

This is the COARSE taxonomy (hair, makeup, nails, barber, skincare) —
what a provider broadly does. The fine-grained taxonomy (texture and
technique tags like "fade" or "locs") is a separate, later concept —
see app/specialties.py once that exists — deliberately not the same
thing as this module, which was itself named "specialties" for this
coarse list before this rename.

ProviderProfile.categories and Booking.category are both stored as a
plain string / string array (see their models) — this allowlist is
enforced at the Pydantic layer via `Category` below, not as a DB
constraint, which is the whole point: changing the list is a code
change, not a migration.
"""
from typing import Annotated

from pydantic import AfterValidator

CATEGORIES: frozenset[str] = frozenset({"hair", "makeup", "nails", "barber", "skincare"})


def _validate_category(value: str) -> str:
    if value not in CATEGORIES:
        raise ValueError(f"'{value}' is not a known category; must be one of {sorted(CATEGORIES)}")
    return value


Category = Annotated[str, AfterValidator(_validate_category)]
