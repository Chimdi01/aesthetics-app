"""
GET /search is registered BEFORE GET /{profile_id} — same reasoning as
the route-ordering gotcha documented in app/routers/bookings.py:
"/providers/search" and "/providers/{profile_id}" are both GET requests
at the same path depth, and {profile_id} (typed uuid.UUID) still matches
"search" at the STRING level first if registered earlier — the UUID
conversion only happens after a route has already matched, so a
mis-ordered /{profile_id} would intercept a search request and fail UUID
parsing with a 422 instead of ever reaching the real search handler.

Provider-owned sub-resources used to live in this file too — they've
moved to their own router modules (app/routers/provider_availability.py,
app/routers/portfolio.py, app/routers/reviews.py) once this file started
covering profile CRUD, search, availability, AND portfolio all at once.
This file is just the ProviderProfile resource itself now: create, fetch,
search.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2 import Geography, WKTElement
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.provider_profile import ProviderProfile, ServiceCategory
from app.models.review import Review
from app.models.user import User
from app.schemas.provider_profile import ProviderProfileCreate, ProviderProfilePublic, ProviderSearchResult
from app.security import get_current_provider

logger = logging.getLogger(__name__)

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
        address_type=payload.address_type,
        # WKT is "POINT(longitude latitude)" — x is longitude. Both values
        # are already range-validated floats (see ProviderProfileCreate),
        # never free text, so nothing user-controlled is spliced in as SQL.
        location=(
            WKTElement(f"POINT({payload.longitude} {payload.latitude})", srid=4326)
            if payload.latitude is not None
            else None
        ),
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    logger.info("Provider profile created: %s (user=%s, categories=%s)", profile.id, current_user.id, [c.value for c in profile.categories])
    return profile


@router.get("/search", response_model=list[ProviderSearchResult])
async def search_providers(
    latitude: float = Query(ge=-90, le=90),
    longitude: float = Query(ge=-180, le=180),
    radius_km: float = Query(default=10, gt=0, le=50),
    category: ServiceCategory | None = None,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    origin = cast(func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326), Geography)

    ratings = (
        select(
            Review.provider_profile_id.label("provider_profile_id"),
            func.avg(Review.rating).label("average_rating"),
            func.count(Review.id).label("review_count"),
        )
        .group_by(Review.provider_profile_id)
        .subquery()
    )
    distance_m = func.ST_Distance(ProviderProfile.location, origin).label("distance_m")

    stmt = (
        select(ProviderProfile, distance_m, ratings.c.average_rating, func.coalesce(ratings.c.review_count, 0))
        .outerjoin(ratings, ratings.c.provider_profile_id == ProviderProfile.id)
        .where(
            ProviderProfile.location.is_not(None),
            func.ST_DWithin(ProviderProfile.location, origin, radius_km * 1000),
        )
        # id as a tiebreaker keeps pagination stable when distances tie.
        .order_by(distance_m, ProviderProfile.id)
        .limit(limit)
        .offset(offset)
    )
    if category is not None:
        stmt = stmt.where(ProviderProfile.categories.any(category))

    rows = (await db.execute(stmt)).all()
    # Exact search origin isn't logged above DEBUG — for a home provider
    # (or a customer searching from home) that coordinate is effectively a
    # home address, so it gets the same "don't log it above DEBUG"
    # treatment as any other location data in this codebase.
    logger.debug("Search origin=(%s, %s) radius_km=%s category=%s", latitude, longitude, radius_km, category)
    logger.info("Provider search returned %d result(s) within %skm", len(rows), radius_km)
    return [
        ProviderSearchResult(
            id=profile.id,
            business_name=profile.business_name,
            bio=profile.bio,
            categories=profile.categories,
            address_type=profile.address_type,
            distance_km=round(distance / 1000, 1),
            average_rating=round(float(avg), 2) if avg is not None else None,
            review_count=count,
        )
        for profile, distance, avg, count in rows
    ]


@router.get("/{profile_id}", response_model=ProviderProfilePublic)
async def get_provider_profile(profile_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    profile = await db.get(ProviderProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found")
    return profile
