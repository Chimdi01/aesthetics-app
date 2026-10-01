"""
The actual HTTP endpoints. Notice the pattern in every function:
  1. Take validated input (FastAPI already ran it through UserCreate)
  2. Do the database work via the injected `db` session
  3. Return data shaped by UserPublic (FastAPI converts it automatically)

`Depends(get_db)` is FastAPI's dependency injection: for every request,
it runs get_db(), hands the route function the session, and closes it
afterward — you never manage that lifecycle by hand.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.rate_limit import limiter
from app.schemas.user import UserCreate, UserPublic
from app.security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/", response_model=UserPublic, status_code=201)
# Tighter than the 200/minute global default — a signup endpoint with no
# throttle is an easy way to mass-create accounts (spam, fraud, scraping
# the "email already registered" signal to enumerate real users).
@limiter.limit("10/hour")
async def create_user(request: Request, payload: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        logger.info("Signup rejected, email already registered: %s", payload.email)
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    logger.info("User created: %s (role=%s)", user.id, user.role.value)
    return user


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
