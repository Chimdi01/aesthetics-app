"""
Static-path routes under /me (portfolio upload/delete, resolved from the
authenticated user) are registered BEFORE the parameterized /{profile_id}
routes — same route-registration-order reasoning as app/routers/bookings.py:
a dynamic segment like {profile_id} still matches "me" at the string level,
so a literal route at the same depth must come first to avoid ever being
shadowed by it.
"""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portfolio_media import PortfolioMedia
from app.models.provider_profile import ProviderProfile
from app.models.review import Review
from app.models.user import User
from app.schemas.portfolio_media import PortfolioMediaPublic
from app.schemas.provider_profile import ProviderProfileCreate, ProviderProfilePublic
from app.schemas.review import ReviewPublic
from app.security import get_current_provider
from app.storage import delete_file, save_upload

router = APIRouter(prefix="/providers", tags=["providers"])


def _portfolio_media_to_public(media: PortfolioMedia) -> PortfolioMediaPublic:
    return PortfolioMediaPublic(
        id=media.id,
        provider_profile_id=media.provider_profile_id,
        media_type=media.media_type,
        url=f"/media/{media.file_path}",
        caption=media.caption,
        created_at=media.created_at,
    )


async def _get_own_provider_profile(db: AsyncSession, current_user: User) -> ProviderProfile:
    result = await db.execute(select(ProviderProfile).where(ProviderProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="You don't have a provider profile yet")
    return profile


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


@router.post("/me/portfolio", response_model=PortfolioMediaPublic, status_code=201)
async def upload_portfolio_media(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None, max_length=255),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_provider),
):
    profile = await _get_own_provider_profile(db, current_user)

    relative_path, media_type = await save_upload(file, profile.id)

    media = PortfolioMedia(
        provider_profile_id=profile.id,
        media_type=media_type,
        file_path=relative_path,
        caption=caption,
    )
    db.add(media)
    await db.commit()
    await db.refresh(media)
    return _portfolio_media_to_public(media)


@router.delete("/me/portfolio/{media_id}", status_code=204)
async def delete_portfolio_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_provider),
):
    profile = await _get_own_provider_profile(db, current_user)

    media = await db.get(PortfolioMedia, media_id)
    if not media or media.provider_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Portfolio media not found")

    await db.delete(media)
    await db.commit()
    delete_file(media.file_path)


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


@router.get("/{profile_id}/portfolio", response_model=list[PortfolioMediaPublic])
async def list_provider_portfolio(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    profile = await db.get(ProviderProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found")

    result = await db.execute(
        select(PortfolioMedia)
        .where(PortfolioMedia.provider_profile_id == profile_id)
        .order_by(PortfolioMedia.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_portfolio_media_to_public(m) for m in result.scalars().all()]
