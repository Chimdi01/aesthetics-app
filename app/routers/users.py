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
from app.models.device_token import DeviceToken
from app.models.email_token import EmailTokenPurpose
from app.models.notification_preference import NotificationPreference
from app.models.user import User, UserRole
from app.rate_limit import limiter
from app.schemas.device_token import DeviceTokenPublic, DeviceTokenRegister
from app.schemas.notification_preference import NotificationPreferencesPublic, NotificationPreferencesUpdate
from app.schemas.user import PhoneNumberUpdate, UserCreate, UserPublic, UserSummary
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
    # Explicit flush before staging the EmailToken/NotificationPreference:
    # neither is linked to User by an ORM relationship() (just a raw FK
    # column), so SQLAlchemy's flush-ordering doesn't know to insert the
    # user row before rows that reference it — without this, new objects
    # sharing one commit hit a real ForeignKeyViolationError (caught the
    # hard way, via a failing regression test, not reasoned about in
    # advance — see CLAUDE.md). flush() sends the INSERT and assigns
    # user.id without ending the transaction, so this stays one atomic
    # commit from the caller's point of view.
    await db.flush()
    raw_token = issue_email_token(db, user.id, EmailTokenPurpose.verify_email)
    # Every account gets one of these — see
    # app/models/notification_preference.py for why it's a separate
    # table rather than columns on User, and app/notifications.py for
    # what reads it.
    db.add(NotificationPreference(user_id=user.id))
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


@router.patch("/me/phone-number", response_model=UserPublic)
async def update_my_phone_number(
    payload: PhoneNumberUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Static path, registered BEFORE GET /{user_id} below — same
    route-ordering gotcha as app/routers/bookings.py's /as-customer:
    /{user_id} is typed uuid.UUID, but FastAPI still matches it as a
    plain string segment first, so "/me/phone-number" would fail UUID
    conversion and 422 if the parameterized route were registered first."""
    current_user.phone_number = payload.phone_number
    await db.commit()
    await db.refresh(current_user)
    logger.info(
        "User %s %s their phone number", current_user.id, "set" if payload.phone_number else "cleared"
    )
    return current_user


@router.get("/me/notification-preferences", response_model=NotificationPreferencesPublic)
async def get_my_notification_preferences(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        # Shouldn't happen for any account created after this feature
        # shipped (create_user always makes one) — but an account from
        # before it existed would otherwise 500 here instead of a clean
        # 404, which is a more honest answer than "the row evaporated".
        raise HTTPException(status_code=404, detail="Notification preferences not found")
    return prefs


@router.patch("/me/notification-preferences", response_model=NotificationPreferencesPublic)
async def update_my_notification_preferences(
    payload: NotificationPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        raise HTTPException(status_code=404, detail="Notification preferences not found")

    # exclude_unset: only fields the caller actually included in the
    # request body get applied — an omitted field means "leave this one
    # alone", not "turn it off" (every field is individually optional,
    # see NotificationPreferencesUpdate's docstring).
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)

    await db.commit()
    await db.refresh(prefs)
    logger.info("User %s updated notification preferences", current_user.id)
    return prefs


@router.post("/me/device-tokens", response_model=DeviceTokenPublic, status_code=201)
async def register_device_token(
    payload: DeviceTokenRegister,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Called by a mobile client after the OS/FCM SDK hands it a device
    token — not usable yet in practice (no mobile app exists, see
    CLAUDE.md), but real, tested backend plumbing for when one does.

    Upserts on the token VALUE, not just per-user: the same physical
    device/app-install reassigning its token to a different account
    (log out, log back in as someone else on a shared device; or the
    app was reinstalled and the OS handed back the same token) is a
    real scenario — the row should move to point at whoever's
    logged in now, not accumulate duplicate rows for the same device.
    """
    result = await db.execute(select(DeviceToken).where(DeviceToken.token == payload.token))
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.user_id = current_user.id
        existing.platform = payload.platform
        device_token = existing
    else:
        device_token = DeviceToken(user_id=current_user.id, token=payload.token, platform=payload.platform)
        db.add(device_token)

    await db.commit()
    await db.refresh(device_token)
    logger.info(
        "Device token registered: %s (user=%s, platform=%s)",
        device_token.id, current_user.id, payload.platform.value,
    )
    return device_token


@router.get("/me/device-tokens", response_model=list[DeviceTokenPublic])
async def list_my_device_tokens(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    result = await db.execute(select(DeviceToken).where(DeviceToken.user_id == current_user.id))
    return result.scalars().all()


@router.delete("/me/device-tokens/{token_id}", status_code=204)
async def unregister_device_token(
    token_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Called on logout/uninstall so a device that no longer has the app
    (or isn't logged in as this user anymore) stops receiving pushes for
    this account."""
    device_token = await db.get(DeviceToken, token_id)
    if device_token is None or device_token.user_id != current_user.id:
        # 404 either way — same "don't reveal whether a resource exists
        # for someone else" reasoning used elsewhere (e.g. a deactivated
        # provider profile returning 404 to a booking attempt), not 403,
        # which would confirm a token with this id exists at all.
        raise HTTPException(status_code=404, detail="Device token not found")

    await db.delete(device_token)
    await db.commit()
    logger.info("Device token unregistered: %s (user=%s)", token_id, current_user.id)


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
