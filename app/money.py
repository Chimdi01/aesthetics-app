"""
Money handling: every amount is an integer in minor units plus an ISO
4217 currency code — never a float, never an amount without its
currency. See CLAUDE.md's Money convention.

CURRENCIES is an allowlist in code, not the full ISO 4217 standard —
just the launch markets' currencies (see CLAUDE.md's market list) —
same "allowlist in code, not a DB enum" pattern as app/specialties.py.
Each value is the number of minor units per major unit: 2 for a
cents/kobo/pence-style currency, 0 for XOF, which has no subdivision
used in practice.
"""
from typing import Annotated

from pydantic import AfterValidator

CURRENCIES: dict[str, int] = {
    "GBP": 2,
    "EUR": 2,
    "NGN": 2,
    "XOF": 0,
}


def _validate_currency(value: str) -> str:
    if value not in CURRENCIES:
        raise ValueError(f"'{value}' is not a supported currency; must be one of {sorted(CURRENCIES)}")
    return value


Currency = Annotated[str, AfterValidator(_validate_currency)]
