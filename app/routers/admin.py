"""
Admin-only review of identity-verification submissions. Deliberately a
separate router from app/routers/verification.py (self-service: act on
your own row) rather than one file branching on role — the authorization
model is fundamentally different (anyone's row vs. only your own), and
this is also where future admin-facing features (e.g. reporting/flagging)
would land, not inside a user-facing router.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.identity_verification import IdentityVerification, VerificationStatus
from app.models.user import User
from app.schemas.identity_verification import VerificationAdminPublic, VerificationReviewUpdate
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

    content = read_verification_document(verification.file_path)
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

    if verification.status != VerificationStatus.pending:
        raise HTTPException(status_code=400, detail=f"Verification is already {verification.status.value}")

    verification.status = payload.status
    verification.rejection_reason = payload.rejection_reason if payload.status == VerificationStatus.rejected else None
    verification.reviewed_by = current_admin.id
    verification.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(verification)
    logger.info(
        "Verification %s reviewed: user=%s, status=%s, reviewed_by=%s",
        verification.id, verification.user_id, payload.status.value, current_admin.id,
    )
    return verification
