"""
Which payment processor handles a given provider, decided by the
PROVIDER'S OWN COUNTRY — not by currency. Currency looks like it would
work today (every launch currency happens to map to exactly one
processor) but that's a coincidence, not a rule: EUR, for instance, is
usable well beyond the one country currently mapped to it here, and
nothing says a future market sharing a currency with an existing one
would also share its processor. Country is the real-world fact that
actually decides this, per CLAUDE.md's Payments convention: Stripe
Connect (Standard, direct charges) for the UK and Europe now, the US
and parts of South America eventually; Flutterwave for Africa. The two
are different liability models — never assumed to behave alike.

COUNTRIES/PROVIDER_BY_COUNTRY are an allowlist in code, same pattern as
app/categories.py / app/money.py / app/time_utils.py's ProviderTimezone
— adding a market is adding a dict entry here, not a schema migration.
Only today's actual, decided launch markets are mapped (Wave 1: GB/NG,
Wave 2: FR/CI/SN — see CLAUDE.md's "What this is"). The US and South
America are real stated intent, not yet a decided market the way those
five are, so they're deliberately NOT in this dict yet — add them
(each with its own currency in app/money.py too) once they're actually
decided, the same discipline already applied to currencies/categories.

PaymentProvider itself, unlike country, is NOT expected to grow often —
adding a third processor is a rare, heavy integration decision, not a
business/market configuration change — so it's a real Postgres ENUM
(same reasoning as VisitType/BookingStatus), not a string allowlist.
"""
import enum
from typing import Annotated

from pydantic import AfterValidator


class PaymentProvider(str, enum.Enum):
    stripe = "stripe"
    flutterwave = "flutterwave"


PROVIDER_BY_COUNTRY: dict[str, PaymentProvider] = {
    "GB": PaymentProvider.stripe,
    "FR": PaymentProvider.stripe,
    "NG": PaymentProvider.flutterwave,
    "CI": PaymentProvider.flutterwave,
    "SN": PaymentProvider.flutterwave,
}


def _validate_country(value: str) -> str:
    if value not in PROVIDER_BY_COUNTRY:
        raise ValueError(f"'{value}' is not a configured market; must be one of {sorted(PROVIDER_BY_COUNTRY)}")
    return value


# A provider's own country — see ProviderProfile.country.
Country = Annotated[str, AfterValidator(_validate_country)]


def provider_for_country(country: str) -> PaymentProvider:
    """Safe to assume membership rather than .get()+raise: every
    caller's `country` already passed the `Country` validator above
    (the same dict), so an unmapped value can't reach here through the
    API. A KeyError here would mean the two fell out of sync, which is
    a bug in this module, not bad input."""
    return PROVIDER_BY_COUNTRY[country]
