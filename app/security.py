"""
Everything related to "who is this request from" lives here: password
hashing (shared by user creation and login), JWT creation/verification,
and the `get_current_user`/`get_current_admin`/`get_current_provider_profile`
dependency chain that protected routes use to pull the authenticated
user (and, where relevant, their own ProviderProfile row) out of the
request. "Provider" means "has a ProviderProfile row", not a role
value — see get_current_provider_profile and CLAUDE.md's Roles
convention; `role` is a signup-time default only, never an access gate
except for `admin`, which stays exclusive.

Logging rule for this whole file: never log a password, a raw JWT, or an
Authorization header value — only ever a user id (and only once it's
already been validated as a real UUID from a decoded token, never the
raw token string itself).
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import get_db
from app.errors import AppError, ErrorCode
from app.models.provider_profile import ProviderProfile
from app.models.user import User, UserRole
from app.request_context import current_user_id_var

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl points the auto-generated docs at the login endpoint, so
# /docs's "Authorize" button knows where to send credentials.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


async def hash_password(password: str) -> str:
    # bcrypt is deliberately slow (~300ms measured on this machine) and
    # CPU-bound — calling it directly from an async def route doesn't
    # background it, it blocks uvicorn's single event loop for that
    # whole duration, stalling every other concurrent request on that
    # worker. Same fix already applied to app/storage.py's Pillow calls
    # (see CHANGELOG) — run_in_threadpool offloads it instead.
    return await run_in_threadpool(pwd_context.hash, password)


async def verify_password(plain_password: str, hashed_password: str) -> bool:
    return await run_in_threadpool(pwd_context.verify, plain_password, hashed_password)


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    # "sub" (subject) is the standard JWT claim for "who this token is about".
    to_encode = {"sub": str(user_id), "exp": expire}
    # Always the CURRENT key — jwt_previous_secret_keys are accepted for
    # verification (decode_access_token below) but never used to sign a
    # new token; that's what makes them "previous".
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _verification_keys() -> list[str]:
    previous = [key.strip() for key in settings.jwt_previous_secret_keys.split(",") if key.strip()]
    return [settings.jwt_secret_key, *previous]


def decode_access_token(token: str) -> dict:
    """Tries the current signing key first, then each key in
    jwt_previous_secret_keys (app/config.py) in order, succeeding on the
    first that verifies — see that setting's docstring for the rotation
    this supports. Raises the last key's PyJWTError if every key fails;
    the caller only ever turns any failure into the same generic 401
    regardless of which key(s) it was tried against, so which specific
    error comes back here doesn't matter."""
    last_error: jwt.PyJWTError | None = None
    for key in _verification_keys():
        try:
            return jwt.decode(token, key, algorithms=[settings.jwt_algorithm])
        except jwt.PyJWTError as exc:
            last_error = exc
    assert last_error is not None  # _verification_keys() always yields at least jwt_secret_key
    raise last_error


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    credentials_error = AppError(
        status_code=status.HTTP_401_UNAUTHORIZED,
        error_code=ErrorCode.unauthenticated,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            logger.warning("Rejected token with no 'sub' claim")
            raise credentials_error
    except jwt.PyJWTError as exc:
        # str(exc) is a short, fixed message from PyJWT (e.g. "Signature
        # has expired") — never the token itself.
        logger.warning("Rejected invalid/expired token: %s", exc)
        # from None: credentials_error is a deliberately generic,
        # client-facing 401 — chaining PyJWT's internal exception onto it
        # risks that detail surfacing somewhere it shouldn't (a debugger,
        # a future exception handler) for no benefit, since the specific
        # reason is already in the warning above.
        raise credentials_error from None

    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        logger.warning("Token valid but no matching user: %s", user_id)
        raise credentials_error
    # Set as soon as we know who this is, even though the two checks
    # below can still reject the request — a deactivated-account 403
    # should still show the right user_id in its log line, not "-".
    current_user_id_var.set(str(user.id))
    if not user.is_active:
        # Checked here, not just at login: a token issued before the
        # account was deactivated must stop working immediately, not
        # keep granting access until it expires on its own.
        logger.warning("Rejected request from deactivated account: %s", user.id)
        raise AppError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=ErrorCode.account_deactivated,
            detail="This account has been deactivated",
        )
    logger.debug("Authenticated user %s", user.id)
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """Unlike provider-ness, admin IS a role check — admin stays an
    exclusive, non-additive account type (see CLAUDE.md). There is no
    API path that grants the admin role (see UserCreate.reject_admin_signup)
    — admin accounts only exist via a direct DB update by the operator,
    which makes this check meaningful rather than a gate anyone could
    self-pass."""
    if current_user.role != UserRole.admin:
        logger.warning("User %s (role=%s) attempted an admin-only action", current_user.id, current_user.role.value)
        raise AppError(status_code=status.HTTP_403_FORBIDDEN, error_code=ErrorCode.forbidden, detail="Admins only")
    return current_user


async def get_current_provider_profile(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> ProviderProfile:
    """The ONE 'prove you're a provider' dependency — 'provider' means
    'has a ProviderProfile row', not role == provider; role is a
    signup-time default only, never an access gate (see CLAUDE.md).
    Every provider-only route depends on this directly (it needs the
    profile anyway, so there's no separate 'just check the role' step
    to layer underneath — that used to be get_current_provider, now
    removed: it had no caller left that didn't also need the profile
    itself, and querying twice to get it would be redundant).

    Deliberately does NOT check profile.is_active. A deactivated profile
    is hidden from search and can't take new bookings (see
    app/routers/providers.py, app/routers/bookings.py), but the owner can
    still manage it — add portfolio items, fix availability, etc. — while
    it's under review. Blocking self-management too would be a stricter
    policy (closer to what User.is_active does for the whole account);
    this was confirmed as the intended split, not an oversight, during a
    gap-analysis pass (see CLAUDE.md)."""
    result = await db.execute(select(ProviderProfile).where(ProviderProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise AppError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=ErrorCode.provider_profile_required,
            detail="You don't have a provider profile yet",
        )
    return profile
