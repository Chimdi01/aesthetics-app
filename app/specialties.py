"""
The specialties allowlist — a plain Python collection, not a Postgres
enum, so the taxonomy can grow (e.g. splitting "hair" into specific
textures/techniques later) without an ALTER TYPE migration against a
live column. See CLAUDE.md's Specialties convention.

ProviderProfile.categories and Booking.category are both stored as a
plain string / string array (see their models) — this allowlist is
enforced at the Pydantic layer via `Specialty` below, not as a DB
constraint, which is the whole point: changing the list is a code
change, not a migration.
"""
from typing import Annotated

from pydantic import AfterValidator

SPECIALTIES: frozenset[str] = frozenset({"hair", "makeup", "nails", "barber", "skincare"})


def _validate_specialty(value: str) -> str:
    if value not in SPECIALTIES:
        raise ValueError(f"'{value}' is not a known specialty; must be one of {sorted(SPECIALTIES)}")
    return value


Specialty = Annotated[str, AfterValidator(_validate_specialty)]
