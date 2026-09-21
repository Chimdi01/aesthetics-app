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
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.provider_profile import ProviderProfile
from app.models.review import Review
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingPublic, BookingStatusUpdate
from app.schemas.review import ReviewCreate, ReviewPublic
from app.security import get_current_provider, get_current_user

router = APIRouter(prefix="/bookings", tags=["bookings"])


async def _get_owning_provider_profile(db: AsyncSession, booking: Booking) -> ProviderProfile:
    result = await db.execute(select(ProviderProfile).where(ProviderProfile.id == booking.provider_profile_id))
    return result.scalar_one()


@router.post("/", response_model=BookingPublic, status_code=201)
async def create_booking(
    payload: BookingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    provider_profile = await db.get(ProviderProfile, payload.provider_profile_id)
    if not provider_profile:
        raise HTTPException(status_code=404, detail="Provider profile not found")

    if payload.category not in provider_profile.categories:
        raise HTTPException(
            status_code=400, detail=f"This provider does not offer '{payload.category.value}'"
        )

    if payload.scheduled_at <= datetime.now(timezone.utc):
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

    provider_profile = await _get_owning_provider_profile(db, booking)
    is_customer = booking.customer_id == current_user.id
    is_provider = provider_profile.user_id == current_user.id
    if not is_customer and not is_provider:
        raise HTTPException(status_code=403, detail="Not your booking")

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

    provider_profile = await _get_owning_provider_profile(db, booking)
    is_customer = booking.customer_id == current_user.id
    is_provider = provider_profile.user_id == current_user.id
    if not is_customer and not is_provider:
        raise HTTPException(status_code=403, detail="Not your booking")

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

    booking.status = new_status
    await db.commit()
    await db.refresh(booking)
    return booking


@router.post("/{booking_id}/review", response_model=ReviewPublic, status_code=201)
async def create_review(
    booking_id: uuid.UUID,
    payload: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the customer on this booking can leave a review")

    if booking.status != BookingStatus.completed:
        raise HTTPException(status_code=400, detail="Only a completed booking can be reviewed")

    existing = await db.execute(select(Review).where(Review.booking_id == booking_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="This booking has already been reviewed")

    review = Review(
        booking_id=booking.id,
        customer_id=current_user.id,
        provider_profile_id=booking.provider_profile_id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return review
