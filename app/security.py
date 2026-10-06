"""
Everything related to "who is this request from" lives here: password
hashing (shared by user creation and login), JWT creation/verification,
and the `get_current_user`/`get_current_provider`/`get_current_provider_profile`
dependency chain that protected routes use to pull the authenticated
user (and, where relevant, their own ProviderProfile row) out of the
request.

Logging rule for this whole file: never log a password, a raw JWT, or an
Authorization header value — only ever a user id (and only once it's
already been validated as a real UUID from a decoded token, never the
raw token string itself).
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.provider_profile import ProviderProfile
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# tokenUrl points the auto-generated docs at the login endpoint, so
# /docs's "Authorize" button knows where to send credentials.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    # "sub" (subject) is the standard JWT claim for "who this token is about".
    to_encode = {"sub": str(user_id), "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def get_current_user(
    token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if user_id is None:
            logger.warning("Rejected token with no 'sub' claim")
            raise credentials_error
    except jwt.PyJWTError as exc:
        # str(exc) is a short, fixed message from PyJWT (e.g. "Signature
        # has expired") — never the token itself.
        logger.warning("Rejected invalid/expired token: %s", exc)
        raise credentials_error

    user = await db.get(User, uuid.UUID(user_id))
    if user is None:
        logger.warning("Token valid but no matching user: %s", user_id)
        raise credentials_error
    logger.debug("Authenticated user %s", user.id)
    return user


async def get_current_provider(current_user: User = Depends(get_current_user)) -> User:
    """A dependency built on top of another dependency: reuses
    get_current_user's work, then adds a role check on top. Any route
    that needs 'must be logged in AND be a provider' just depends on
    this instead of re-checking the role itself."""
    if current_user.role != UserRole.provider:
        logger.warning("User %s (role=%s) attempted a provider-only action", current_user.id, current_user.role.value)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Providers only")
    return current_user


async def get_current_provider_profile(
    current_user: User = Depends(get_current_provider), db: AsyncSession = Depends(get_db)
) -> ProviderProfile:
    """Another link in the same dependency chain: resolves the
    authenticated provider's own ProviderProfile row. Every '/me/...'
    provider-owned endpoint (availability, portfolio) depends on this
    directly instead of each re-querying 'my profile' by hand."""
    result = await db.execute(select(ProviderProfile).where(ProviderProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="You don't have a provider profile yet")
    return profile
