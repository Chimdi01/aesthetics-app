"""
Admin-only actions: reviewing identity-verification submissions, and
reviewing/acting on reports filed against users (either role — see
app/models/report.py). Deliberately a separate router from the
user-facing ones (app/routers/verification.py, app/routers/reports.py —
self-service, act on your own row) rather than one file branching on
role — the authorization model is fundamentally different (anyone's row
vs. only your own).
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.identity_verification import IdentityVerification, VerificationStatus
from app.models.provider_profile import ProviderProfile
from app.models.report import Report, ReportStatus
from app.models.user import User
from app.schemas.identity_verification import (
    VerificationAdminPublic,
    VerificationReviewUpdate,
)
from app.schemas.provider_profile import ProviderProfilePublic, ProviderStatusUpdate
from app.schemas.report import ReportAdminPublic, ReportReviewUpdate
from app.schemas.user import UserPublic, UserStatusUpdate
from app.security import get_current_admin
from app.verification_storage import content_type_for_path, read_verification_document

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/verifications", response_model=list[VerificationAdminPublic])
async def list_verifications(
    status_filter: VerificationStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(IdentityVerification).order_by(IdentityVerification.created_at).limit(limit).offset(offset)
    if status_filter is not None:
        stmt = stmt.where(IdentityVerification.status == status_filter)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/verifications/{verification_id}/document")
async def get_verification_document(
    verification_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    verification = await db.get(IdentityVerification, verification_id)
    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")

    content = await read_verification_document(verification.file_path)
    return Response(
        content=content,
        media_type=content_type_for_path(verification.file_path),
        headers={"Cache-Control": "no-store"},
    )


@router.patch("/verifications/{verification_id}", response_model=VerificationAdminPublic)
async def review_verification(
    verification_id: uuid.UUID,
    payload: VerificationReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    verification = await db.get(IdentityVerification, verification_id)
    if not verification:
        raise HTTPException(status_code=404, detail="Verification not found")

    if verification.user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="You can't review your own verification submission")

    if verification.status != VerificationStatus.pending:
        raise HTTPException(status_code=400, detail=f"Verification is already {verification.status.value}")

    verification.status = payload.status
    verification.rejection_reason = payload.rejection_reason if payload.status == VerificationStatus.rejected else None
    verification.reviewed_by = current_admin.id
    verification.reviewed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(verification)
    logger.info(
        "Verification %s reviewed: user=%s, status=%s, reviewed_by=%s",
        verification.id, verification.user_id, payload.status.value, current_admin.id,
    )
    return verification


@router.get("/reports", response_model=list[ReportAdminPublic])
async def list_reports(
    status_filter: ReportStatus | None = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    stmt = select(Report).order_by(Report.created_at).limit(limit).offset(offset)
    if status_filter is not None:
        stmt = stmt.where(Report.status == status_filter)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/reports/{report_id}", response_model=ReportAdminPublic)
async def review_report(
    report_id: uuid.UUID,
    payload: ReportReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if report.reported_user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="You can't review a report filed against yourself")

    if report.status != ReportStatus.pending:
        raise HTTPException(status_code=400, detail=f"Report is already {report.status.value}")

    report.status = payload.status
    report.resolved_by = current_admin.id
    report.resolved_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(report)
    logger.info(
        "Report %s reviewed: reported_user=%s, status=%s, resolved_by=%s",
        report.id, report.reported_user_id, payload.status.value, current_admin.id,
    )
    return report


@router.patch("/users/{user_id}/status", response_model=UserPublic)
async def set_user_active_status(
    user_id: uuid.UUID,
    payload: UserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """Cuts off the ACCOUNT entirely (login rejected; get_current_user
    rejects any existing token too — see app/security.py), for either
    role. Independent of, and a harsher lever than,
    PATCH /providers/{profile_id}/status below, which only hides a
    provider's business listing while leaving their account usable.

    Deactivating a provider's account cascades to deactivating their
    ProviderProfile too (one write, here) — an account-level suspension
    should never leave a bookable profile behind. Reactivating does NOT
    cascade back the other way: resuming account access and trusting the
    business profile again are different decisions, and the safer
    default is requiring the profile to be explicitly re-enabled."""
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="You can't deactivate your own account")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = payload.is_active
    if not payload.is_active:
        result = await db.execute(select(ProviderProfile).where(ProviderProfile.user_id == user_id))
        provider_profile = result.scalar_one_or_none()
        if provider_profile is not None:
            provider_profile.is_active = False

    await db.commit()
    await db.refresh(user)
    logger.info("User %s active status set to %s by admin=%s", user_id, payload.is_active, current_admin.id)
    return user


@router.patch("/providers/{profile_id}/status", response_model=ProviderProfilePublic)
async def set_provider_active_status(
    profile_id: uuid.UUID,
    payload: ProviderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    """Deactivating excludes the profile from search (app/routers/providers.py)
    and blocks new bookings against it (app/routers/bookings.py) — it
    does NOT hide existing bookings/reviews/portfolio, which still
    reference this row and would break if it disappeared entirely.
    Deliberately independent of report review above: deactivating a
    profile doesn't require (or imply) resolving every report against it,
    and resolving a report doesn't require (or imply) deactivating."""
    profile = await db.get(ProviderProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Provider profile not found")

    profile.is_active = payload.is_active
    await db.commit()
    await db.refresh(profile)
    logger.info(
        "Provider profile %s active status set to %s by admin=%s",
        profile_id, payload.is_active, current_admin.id,
    )
    return profile
