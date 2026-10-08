"""
User-facing report submission — reports a USER (customer or provider),
not specifically a ProviderProfile (see app/models/report.py for why).
Admin review (listing, resolving, and the deactivation levers it can
lead to) lives in app/routers/admin.py instead — same split rationale as
verification.py/admin.py: act on your own submission vs. act on anyone's.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.report import Report
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.report import ReportCreate, ReportPublic
from app.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["reports"])


@router.post("/{user_id}/report", response_model=ReportPublic, status_code=201)
# Tighter than the 200/minute global default — otherwise one account can
# file 200 reports a minute against the same target, which is itself a
# harassment vector against whoever gets reported.
@limiter.limit("10/hour")
async def report_user(
    request: Request,
    user_id: uuid.UUID,
    payload: ReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You can't report yourself")

    reported_user = await db.get(User, user_id)
    if not reported_user:
        raise HTTPException(status_code=404, detail="User not found")

    report = Report(
        reporter_id=current_user.id,
        reported_user_id=user_id,
        reason=payload.reason,
        details=payload.details,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    logger.info(
        "User reported: report=%s, reported_user=%s, reporter=%s, reason=%s",
        report.id, user_id, current_user.id, payload.reason.value,
    )
    return report
