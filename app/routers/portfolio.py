"""
POST/DELETE under /me use different HTTP methods than
GET /{profile_id}/portfolio below — same note as
app/routers/provider_availability.py: no real collision risk here, kept
static-path-first anyway for readability consistency.

Split out of app/routers/providers.py once that file started covering
profile CRUD, search, availability, AND portfolio all in one place.
"""
import logging
import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portfolio_media import PortfolioMedia
from app.models.provider_profile import ProviderProfile
from app.rate_limit import limiter
from app.schemas.portfolio_media import PortfolioMediaPublic
from app.security import get_current_provider_profile
from app.storage import delete_file, save_upload

logger = logging.getLogger(__name__)

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


@router.post("/me/portfolio", response_model=PortfolioMediaPublic, status_code=201)
# Tighter than the 200/minute global default — each upload costs a
# Pillow decode/recompress plus a disk write up to max_upload_size_bytes;
# the generic default would let one compromised/malicious provider
# account write up to the size cap x 200 times a minute, which is exactly
# the storage-cost exposure the compression/cache-header work earlier
# this session was trying to bound.
@limiter.limit("20/hour")
async def upload_portfolio_media(
    request: Request,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None, max_length=255),
    db: AsyncSession = Depends(get_db),
    profile: ProviderProfile = Depends(get_current_provider_profile),
):
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
    logger.info("Portfolio media uploaded: %s (provider=%s, type=%s)", media.id, profile.id, media_type.value)
    return _portfolio_media_to_public(media)


@router.delete("/me/portfolio/{media_id}", status_code=204)
async def delete_portfolio_media(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    profile: ProviderProfile = Depends(get_current_provider_profile),
):
    media = await db.get(PortfolioMedia, media_id)
    if not media or media.provider_profile_id != profile.id:
        raise HTTPException(status_code=404, detail="Portfolio media not found")

    await db.delete(media)
    await db.commit()
    delete_file(media.file_path)
    logger.info("Portfolio media deleted: %s (provider=%s)", media_id, profile.id)


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
