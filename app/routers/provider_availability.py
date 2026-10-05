"""
PUT /me/availability uses a different HTTP method (PUT) than
GET /{profile_id}/availability below, so — unlike app/routers/bookings.py's
/as-customer vs /{booking_id} (both GET, a real collision risk) — these
two don't actually collide regardless of registration order. Kept with
the static path first anyway, for readability consistency with the rest
of this codebase's routers.

Split out of app/routers/providers.py once that file started covering
profile CRUD, search, availability, AND portfolio all in one place.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.provider_availability import DayOfWeek, ProviderAvailability
from app.models.provider_profile import ProviderProfile
from app.schemas.provider_availability import ProviderAvailabilityPublic, ProviderAvailabilityUpdate
from app.security import get_current_provider_profile

logger = logging.getLogger(__name__)

# Enum declaration order (monday..sunday) doubles as sort order for
# schedule responses — customers/providers read a week Monday-first.
_DAY_ORDER = {day: index for index, day in enumerate(DayOfWeek)}

router = APIRouter(prefix="/providers", tags=["providers"])


@router.put("/me/availability", response_model=list[ProviderAvailabilityPublic])
async def set_provider_availability(
    payload: ProviderAvailabilityUpdate,
    db: AsyncSession = Depends(get_db),
    profile: ProviderProfile = Depends(get_current_provider_profile),
):
    # Full replace: clear the existing week, then insert the new one.
    # Simpler and less error-prone than diffing against existing rows for
    # a "set my working hours" action that's naturally one coherent write.
    await db.execute(delete(ProviderAvailability).where(ProviderAvailability.provider_profile_id == profile.id))

    rows = [
        ProviderAvailability(
            provider_profile_id=profile.id,
            day_of_week=entry.day_of_week,
            start_time=entry.start_time,
            end_time=entry.end_time,
        )
        for entry in payload.schedule
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)

    logger.info("Availability updated for provider %s: %d shift(s)", profile.id, len(rows))
    return sorted(rows, key=lambda r: (_DAY_ORDER[r.day_of_week], r.start_time))


@router.get("/{profile_id}/availability", response_model=list[ProviderAvailabilityPublic])
async def get_provider_availability(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    profile = await db.get(ProviderProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found")

    # Naturally bounded (at most a handful of shifts per day, 7 days) — no
    # pagination needed the way the reviews/portfolio listings have it.
    result = await db.execute(
        select(ProviderAvailability).where(ProviderAvailability.provider_profile_id == profile_id)
    )
    rows = result.scalars().all()
    return sorted(rows, key=lambda r: (_DAY_ORDER[r.day_of_week], r.start_time))
