"""
The fine-grained specialties taxonomy: texture and technique tags,
each mapping to the (coarse) category or categories it belongs to —
see app/categories.py for that coarser level, and CLAUDE.md's
Categories/Specialties conventions. An allowlist in code, not a
Postgres enum, same "a taxonomy is configuration" reasoning as
everywhere else in this codebase — adding a specialty is a dict entry
here, not a migration.

Values describe hair texture and technique only — never race,
ethnicity, or a proxy for either (see CLAUDE.md's "Product decisions
already made"). Checked against this starter taxonomy: the texture
terms (straight/wavy/curly/coily) are the explicitly sanctioned
discovery axis itself, not a proxy for anything; every other slug
names a technique or service, not a person.

No labels are served anywhere from this module or its API — see
GET /v1/specialties/ in app/routers/specialties.py. The client
localises slug -> display label itself (English now, French later,
same posture as every other human-facing string — see CLAUDE.md's
Locale convention); serving English label text from here would be
exactly the kind of un-templated, server-chosen human-facing string
that convention exists to avoid.
"""
from typing import Annotated

from pydantic import AfterValidator

# slug -> the category/categories it belongs to. Texture is shared
# between hair and barber; every other slug belongs to exactly one
# category.
SPECIALTY_CATEGORIES: dict[str, frozenset[str]] = {
    "straight": frozenset({"hair", "barber"}),
    "wavy": frozenset({"hair", "barber"}),
    "curly": frozenset({"hair", "barber"}),
    "coily": frozenset({"hair", "barber"}),
    "locs": frozenset({"hair"}),
    "braids": frozenset({"hair"}),
    "twists": frozenset({"hair"}),
    "natural_hair": frozenset({"hair"}),
    "silk_press": frozenset({"hair"}),
    "relaxer": frozenset({"hair"}),
    "colour": frozenset({"hair"}),
    "extensions": frozenset({"hair"}),
    "fade": frozenset({"barber"}),
    "taper": frozenset({"barber"}),
    "line_up": frozenset({"barber"}),
    "razor_shave": frozenset({"barber"}),
    "beard_grooming": frozenset({"barber"}),
    "gel": frozenset({"nails"}),
    "acrylic": frozenset({"nails"}),
    "builder_gel": frozenset({"nails"}),
    "nail_art": frozenset({"nails"}),
    "pedicure": frozenset({"nails"}),
    "bridal": frozenset({"makeup"}),
    "special_occasion": frozenset({"makeup"}),
    "editorial": frozenset({"makeup"}),
    "everyday": frozenset({"makeup"}),
    "facial": frozenset({"skincare"}),
}

SPECIALTIES: frozenset[str] = frozenset(SPECIALTY_CATEGORIES)


def _validate_specialty(value: str) -> str:
    if value not in SPECIALTIES:
        raise ValueError(f"'{value}' is not a known specialty; must be one of {sorted(SPECIALTIES)}")
    return value


Specialty = Annotated[str, AfterValidator(_validate_specialty)]
