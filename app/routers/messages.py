"""
Message endpoints for a booking's back-and-forth — scoped to a Booking,
not a general DM system (see app/models/message.py). Split out of
app/routers/bookings.py once that file started covering booking
lifecycle, reviews, AND messaging all in one place; shares the
booking-party authorization check with bookings.py via
app/booking_access.py (a plain module, not a router — see its
docstring), rather than importing from one router module into another.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.booking_access import authorize_booking_party
from app.database import get_db
from app.models.booking import Booking
from app.models.message import Message
from app.models.user import User
from app.schemas.message import MessageCreate, MessagePublic
from app.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/{booking_id}/messages", response_model=MessagePublic, status_code=201)
async def send_message(
    booking_id: uuid.UUID,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    await authorize_booking_party(db, booking, current_user)

    message = Message(booking_id=booking.id, sender_id=current_user.id, body=payload.body)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    # DEBUG, and metadata only — message content is user-generated
    # conversation text and never belongs in logs at any level, even DEBUG.
    logger.debug("Message sent: %s (booking=%s, sender=%s)", message.id, booking.id, current_user.id)
    return message


@router.get("/{booking_id}/messages", response_model=list[MessagePublic])
async def list_messages(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    await authorize_booking_party(db, booking, current_user)

    # Oldest-first (natural conversation order). offset/limit pagination
    # is consistent with the rest of the codebase (reviews, portfolio) —
    # a cursor-based ("messages before X") approach would suit a
    # high-volume chat better, but isn't warranted at this message volume.
    result = await db.execute(
        select(Message)
        .where(Message.booking_id == booking_id)
        .order_by(Message.created_at, Message.id)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()
