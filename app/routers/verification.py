"""
Self-service identity verification: submit a document, check your own
status, view your own previously-submitted document. Admin review
(listing submissions, viewing anyone's document, approving/rejecting)
lives in app/routers/admin.py instead — different authorization model
(act on your own row vs. act on anyone's), kept as separate routers
rather than one file branching on role.
"""
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.identity_verification import DocumentType, IdentityVerification, VerificationStatus
from app.models.user import User
from app.schemas.identity_verification import VerificationPublic
from app.security import get_current_user
from app.verification_storage import (
    content_type_for_path,
    delete_verification_document,
    read_verification_document,
    save_verification_document,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/verification", tags=["verification"])


async def _get_own_verification(db: AsyncSession, current_user: User) -> IdentityVerification | None:
    result = await db.execute(select(IdentityVerification).where(IdentityVerification.user_id == current_user.id))
    return result.scalar_one_or_none()


@router.post("/me", response_model=VerificationPublic, status_code=201)
async def submit_verification(
    document_type: DocumentType = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = await _get_own_verification(db, current_user)
    if existing and existing.status == VerificationStatus.approved:
        raise HTTPException(status_code=409, detail="You're already verified")

    relative_path = await save_verification_document(file, current_user.id)

    if existing:
        # Resubmission (after rejection, or fixing a pending one) replaces
        # the row in place rather than creating a new one — see
        # app/models/identity_verification.py for why.
        delete_verification_document(existing.file_path)
        existing.document_type = document_type
        existing.file_path = relative_path
        existing.status = VerificationStatus.pending
        existing.rejection_reason = None
        existing.reviewed_by = None
        existing.reviewed_at = None
        verification = existing
    else:
        verification = IdentityVerification(
            user_id=current_user.id,
            document_type=document_type,
            file_path=relative_path,
        )
        db.add(verification)

    await db.commit()
    await db.refresh(verification)
    logger.info("Identity verification submitted: user=%s, document_type=%s", current_user.id, document_type.value)
    return verification


@router.get("/me", response_model=VerificationPublic)
async def get_my_verification(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    verification = await _get_own_verification(db, current_user)
    if not verification:
        raise HTTPException(status_code=404, detail="No verification submitted yet")
    return verification


@router.get("/me/document")
async def get_my_verification_document(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    verification = await _get_own_verification(db, current_user)
    if not verification:
        raise HTTPException(status_code=404, detail="No verification submitted yet")

    content = read_verification_document(verification.file_path)
    # The opposite of /media's Cache-Control: this is a government ID
    # photo — no shared or browser cache should ever retain a copy.
    return Response(
        content=content,
        media_type=content_type_for_path(verification.file_path),
        headers={"Cache-Control": "no-store"},
    )
