"""
Shared booking-authorization logic used by every booking sub-resource
router (app/routers/bookings.py, app/routers/messages.py) — a plain
module, not a router itself, same pattern as app/security.py and
app/storage.py: routers depend on these, they don't depend on each
other, so a router can be read in isolation without chasing imports into
a sibling router file.
"""
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.provider_profile import ProviderProfile
from app.models.user import User

logger = logging.getLogger(__name__)


async def get_owning_provider_profile(db: AsyncSession, booking: Booking) -> ProviderProfile:
    result = await db.execute(select(ProviderProfile).where(ProviderProfile.id == booking.provider_profile_id))
    return result.scalar_one()


async def authorize_booking_party(db: AsyncSession, booking: Booking, current_user: User) -> tuple[bool, bool]:
    """Returns (is_customer, is_provider) for this booking; raises 403 if
    current_user is neither. Centralizes a check needed by every booking
    sub-resource (status updates, messages)."""
    provider_profile = await get_owning_provider_profile(db, booking)
    is_customer = booking.customer_id == current_user.id
    is_provider = provider_profile.user_id == current_user.id
    if not is_customer and not is_provider:
        logger.warning("User %s denied access to booking %s (not a party to it)", current_user.id, booking.id)
        raise HTTPException(status_code=403, detail="Not your booking")
    return is_customer, is_provider
