"""
Review creation is a booking sub-resource (POST /bookings/{booking_id}/review
— a customer reacting to one specific completed booking) while listing is
a provider-profile sub-resource (GET /providers/{profile_id}/reviews —
public, browsing a provider). Grouped into one file by DOMAIN CONCEPT
(reviews) rather than by URL prefix — splitting one cohesive concern
across two files just to match prefixes would be worse than one file
whose routes happen to carry two different path prefixes. No
router-level `prefix=` for that reason; each route spells out its full
path instead.

Split out of app/routers/bookings.py once that file started covering
booking lifecycle, reviews, AND messaging all in one place.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.booking import Booking, BookingStatus
from app.models.provider_profile import ProviderProfile
from app.models.review import Review
from app.models.user import User
from app.schemas.review import ReviewCreate, ReviewPublic
from app.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["reviews"])


@router.post("/bookings/{booking_id}/review", response_model=ReviewPublic, status_code=201)
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
        logger.warning("User %s denied review access to booking %s (not the customer)", current_user.id, booking.id)
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
    logger.info("Review created: %s (booking=%s, rating=%d)", review.id, booking.id, review.rating)
    return review


@router.get("/providers/{profile_id}/reviews", response_model=list[ReviewPublic])
async def list_provider_reviews(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    # Bounded default + hard cap: an unbounded SELECT here would let a
    # provider with a large review history turn every page load into an
    # ever-growing query — cap it rather than trusting callers to paginate.
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    profile = await db.get(ProviderProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found")

    result = await db.execute(
        select(Review)
        .where(Review.provider_profile_id == profile_id)
        .order_by(Review.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
