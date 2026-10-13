"""
Time handling: every instant is timezone-aware and stored in UTC
(`DateTime(timezone=True)`) — naive datetimes are rejected at the API
boundary instead of silently being assumed to mean some particular
timezone. See CLAUDE.md's Time convention.

For a client-supplied instant (e.g. Booking.scheduled_at), just use
Pydantic's own `pydantic.AwareDatetime` type directly — it already
rejects a naive value with a clean 422, no custom validator needed.
This module only adds what Pydantic doesn't already provide: IANA
timezone validation for ProviderProfile.timezone.
"""
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator

# Computed once at import time, not on every validation call —
# zoneinfo.available_timezones() walks the tzdata source each time it's
# called, which would otherwise mean re-scanning it on every single
# provider-profile request.
_IANA_TIMEZONES = frozenset(available_timezones())


def _validate_iana_timezone(value: str) -> str:
    if value not in _IANA_TIMEZONES:
        raise ValueError(f"'{value}' is not a known IANA timezone (e.g. 'Europe/London', 'Africa/Lagos')")
    return value


# A provider's own IANA timezone — see ProviderProfile.timezone. Weekly
# availability is stored as wall-clock time and is only meaningful once
# paired with this.
ProviderTimezone = Annotated[str, AfterValidator(_validate_iana_timezone)]
