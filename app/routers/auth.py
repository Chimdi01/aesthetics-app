"""
OAuth2PasswordRequestForm expects standard form fields (username, password)
rather than JSON — that's part of the OAuth2 "password" flow spec, and it's
what makes /docs's "Authorize" button work out of the box. We treat the
`username` field as the user's email.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.security import create_access_token, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        # Email is logged (it's the username being attempted, not a
        # secret), the password never is, successful or not.
        logger.warning("Failed login attempt for %s", form_data.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user.id)
    logger.info("User %s logged in", user.id)
    return {"access_token": access_token, "token_type": "bearer"}
