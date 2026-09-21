import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.provider_profile import ProviderProfile
from app.models.review import Review
from app.models.user import User
from app.schemas.provider_profile import ProviderProfileCreate, ProviderProfilePublic
from app.schemas.review import ReviewPublic
from app.security import get_current_provider

router = APIRouter(prefix="/providers", tags=["providers"])


@router.post("/", response_model=ProviderProfilePublic, status_code=201)
async def create_provider_profile(
    payload: ProviderProfileCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_provider),
):
    existing = await db.execute(
        select(ProviderProfile).where(ProviderProfile.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Provider profile already exists for this user")

    profile = ProviderProfile(
        user_id=current_user.id,
        business_name=payload.business_name,
        bio=payload.bio,
        years_experience=payload.years_experience,
        categories=payload.categories,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/{profile_id}", response_model=ProviderProfilePublic)
async def get_provider_profile(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    profile = await db.get(ProviderProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found")
    return profile


@router.get("/{profile_id}/reviews", response_model=list[ReviewPublic])
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
