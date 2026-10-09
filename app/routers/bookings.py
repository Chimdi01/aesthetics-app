"""
Route registration ORDER matters here: FastAPI matches routes in the
order they're registered, and `/{booking_id}` (typed as uuid.UUID) is
still just a plain string segment at the routing-pattern level — the UUID
conversion happens AFTER a route already matched, not during matching.
So a request to GET /bookings/as-customer would match `/{booking_id}`
first if that route were registered above it, fail UUID conversion on
"as-customer", and return 422 — never reaching the real as-customer
handler below. Static-path routes (/as-customer, /as-provider) are
registered before the parameterized /{booking_id} routes to avoid that.
(app/routers/providers.py's /search vs /{profile_id} is the same pattern.)

Reviews and messaging used to live in this file too — they've moved to
app/routers/reviews.py and app/routers/messages.py respectively, once
this file started covering three distinct concerns (booking lifecycle,
reviews, messaging) in one place. The shared booking-party-authorization
helper they (and this file) depend on now lives in app/booking_access.py,
a plain module rather than living inside whichever router happened to
need it first.
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.booking_access import authorize_booking_party, get_owning_provider_profile
from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.provider_profile import ProviderProfile
from app.models.user import User
from app.notifications import notify_booking_status_changed
from app.schemas.booking import BookingCreate, BookingPublic, BookingStatusUpdate
from app.security import get_current_provider, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=BookingPublic, status_code=201)
async def create_booking(
    payload: BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider_profile = await db.get(ProviderProfile, payload.provider_profile_id)
    if not provider_profile:
        raise HTTPException(status_code=404, detail="Provider profile not found")

    if not provider_profile.is_active:
        # Deliberately 404, not 400/403: a deactivated provider should
        # look the same as one that doesn't exist to a customer trying to
        # book them — no need to reveal "this profile exists but is
        # moderated" to someone who isn't an admin.
        raise HTTPException(status_code=404, detail="Provider profile not found")

    if provider_profile.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't book your own provider profile")

    if payload.category not in provider_profile.categories:
        raise HTTPException(
            status_code=400, detail=f"This provider does not offer '{payload.category.value}'"
        )

    if payload.scheduled_at <= datetime.now(UTC):
        raise HTTPException(status_code=400, detail="scheduled_at must be in the future")

    booking = Booking(
        customer_id=current_user.id,
        provider_profile_id=provider_profile.id,
        category=payload.category,
        visit_type=payload.visit_type,
        address=payload.address,
        scheduled_at=payload.scheduled_at,
        price=payload.price,
        transport_fee=payload.transport_fee,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    logger.info(
        "Booking created: %s (customer=%s, provider_profile=%s, category=%s, visit_type=%s)",
        booking.id, booking.customer_id, booking.provider_profile_id, booking.category.value, booking.visit_type.value,
    )
    return booking


@router.get("/as-customer", response_model=list[BookingPublic])
async def list_my_bookings_as_customer(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Booking).where(Booking.customer_id == current_user.id).order_by(Booking.scheduled_at)
    )
    return result.scalars().all()


@router.get("/as-provider", response_model=list[BookingPublic])
async def list_my_bookings_as_provider(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_provider)
):
    result = await db.execute(select(ProviderProfile).where(ProviderProfile.user_id == current_user.id))
    provider_profile = result.scalar_one_or_none()
    if not provider_profile:
        raise HTTPException(status_code=404, detail="You don't have a provider profile yet")

    bookings = await db.execute(
        select(Booking).where(Booking.provider_profile_id == provider_profile.id).order_by(Booking.scheduled_at)
    )
    return bookings.scalars().all()


@router.get("/{booking_id}", response_model=BookingPublic)
async def get_booking(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    await authorize_booking_party(db, booking, current_user)

    return booking


@router.patch("/{booking_id}/status", response_model=BookingPublic)
async def update_booking_status(
    booking_id: uuid.UUID,
    payload: BookingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    is_customer, is_provider = await authorize_booking_party(db, booking, current_user)

    if booking.status in (BookingStatus.completed, BookingStatus.cancelled):
        raise HTTPException(
            status_code=400, detail=f"Booking is already {booking.status.value}, no further changes allowed"
        )

    new_status = payload.status
    if new_status == BookingStatus.confirmed:
        if not is_provider:
            raise HTTPException(status_code=403, detail="Only the provider can confirm a booking")
        if booking.status != BookingStatus.requested:
            raise HTTPException(status_code=400, detail="Only a requested booking can be confirmed")
    elif new_status == BookingStatus.completed:
        if not is_provider:
            raise HTTPException(status_code=403, detail="Only the provider can mark a booking completed")
        if booking.status != BookingStatus.confirmed:
            raise HTTPException(status_code=400, detail="Only a confirmed booking can be completed")
    elif new_status == BookingStatus.cancelled:
        pass  # either the customer or the provider can cancel a requested/confirmed booking
    else:
        raise HTTPException(status_code=400, detail="Invalid status transition")

    previous_status = booking.status
    booking.status = new_status
    await db.commit()
    await db.refresh(booking)
    logger.info(
        "Booking %s status changed: %s -> %s (by user=%s)",
        booking.id, previous_status.value, new_status.value, current_user.id,
    )

    # Notify the OTHER party — whoever didn't make this change.
    try:
        if is_customer:
            provider_profile = await get_owning_provider_profile(db, booking)
            recipient = await db.get(User, provider_profile.user_id)
        else:
            recipient = await db.get(User, booking.customer_id)
        if recipient is not None:
            await notify_booking_status_changed(db, recipient, new_status.value)
    except Exception:
        logger.exception("Failed to send booking-status-changed notification for booking %s", booking.id)

    return booking
