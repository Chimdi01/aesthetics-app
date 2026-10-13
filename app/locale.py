"""
Locale handling: every user has a `preferred_language`. See CLAUDE.md's
Locale convention and app/notification_templates.py for where this
actually gets used (rendering human-facing notification copy).

LANGUAGES is an allowlist in code, not a Postgres enum — same pattern
as app/specialties.py and app/money.py — so adding a language is a
data change (add template entries in app/notification_templates.py,
add the code here), not a schema migration.
"""
from typing import Annotated

from pydantic import AfterValidator

LANGUAGES: frozenset[str] = frozenset({"en", "fr"})
DEFAULT_LANGUAGE = "en"


def _validate_language(value: str) -> str:
    if value not in LANGUAGES:
        raise ValueError(f"'{value}' is not a supported language; must be one of {sorted(LANGUAGES)}")
    return value


Language = Annotated[str, AfterValidator(_validate_language)]
