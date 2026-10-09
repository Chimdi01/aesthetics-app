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

from app.config import settings
from app.database import get_db
from app.email import send_email
from app.email_tokens import issue_email_token
from app.models.email_token import EmailTokenPurpose
from app.models.user import User, UserRole
from app.rate_limit import limiter
from app.schemas.user import UserCreate, UserPublic, UserSummary
from app.security import get_current_user, hash_password

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
    # Explicit flush before staging the EmailToken: User and EmailToken
    # aren't linked by an ORM relationship() (just a raw FK column), so
    # SQLAlchemy's flush-ordering doesn't know to insert the user row
    # before the token row that references it — without this, both
    # being new objects in the SAME commit hits a real
    # ForeignKeyViolationError (caught the hard way, via a failing
    # regression test, not reasoned about in advance). flush() sends the
    # INSERT and assigns user.id without ending the transaction, so this
    # stays one atomic commit from the caller's point of view.
    await db.flush()
    raw_token = issue_email_token(db, user.id, EmailTokenPurpose.verify_email)
    await db.commit()
    await db.refresh(user)
    logger.info("User created: %s (role=%s)", user.id, user.role.value)

    try:
        await send_email(
            user.email,
            "Verify your email",
            f"Click to verify your email: {settings.frontend_base_url}/verify-email?token={raw_token}",
        )
    except Exception:
        # Account creation succeeds regardless of whether the email
        # actually went out — deliverability flakiness shouldn't fail
        # signup itself. POST /v1/auth/resend-verification is the
        # fallback if this is the branch that ran.
        logger.exception("Failed to send verification email to new user %s", user.id)

    return user


@router.get("/{user_id}", response_model=UserPublic | UserSummary)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Was fully public/unauthenticated, returning email + is_active to
    anyone who had or guessed a UUID — nothing in the app actually
    depended on that. Now requires auth, and strangers get UserSummary
    (no email, no is_active) while you see your own full UserPublic, as
    does an admin."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id or current_user.role == UserRole.admin:
        return UserPublic.model_validate(user)
    return UserSummary.model_validate(user)
