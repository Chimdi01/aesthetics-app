"""
OAuth2PasswordRequestForm expects standard form fields (username, password)
rather than JSON — that's part of the OAuth2 "password" flow spec, and it's
what makes /docs's "Authorize" button work out of the box. We treat the
`username` field as the user's email.

/refresh, /logout, and /logout-all are deliberately NOT rate-limited with
a tighter override the way /login is — they require possessing a specific
long, high-entropy refresh token (not a guessable password), so credential
stuffing doesn't apply the same way; the global default is enough.

/forgot-password and /verify-email/resend-verification ARE tightly
limited, same reasoning as login/signup (app/routers/users.py) — both
send an email, so an unthrottled endpoint is a way to spam a victim's
inbox (or, for forgot-password, to probe which emails are registered via
timing/response differences if the generic response weren't already
careful about that — see the handler itself).
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.email import send_email
from app.email_tokens import get_valid_email_token, invalidate_pending_tokens, issue_email_token
from app.login_lockout import is_locked_out, record_failed_login, record_successful_login
from app.mfa_challenge import get_valid_mfa_challenge, issue_mfa_challenge
from app.models.email_token import EmailTokenPurpose
from app.models.user import User
from app.rate_limit import limiter
from app.refresh_tokens import (
    get_valid_refresh_token,
    issue_refresh_token,
    revoke_all_refresh_tokens_for_user,
)
from app.schemas.auth import (
    ForgotPasswordRequest,
    MfaChallengeResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenPair,
    Verify2FARequest,
    VerifyEmailRequest,
)
from app.security import create_access_token, get_current_user, hash_password, verify_password
from app.totp import verify_and_consume_backup_code, verify_totp_code
from app.totp_encryption import decrypt_totp_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair | MfaChallengeResponse)
# Tighter than the 200/minute global default — login is the one endpoint
# where that default is nowhere near tight enough: credential stuffing
# means many attempts against the SAME account, often from a rotating
# set of IPs, but 5/minute per IP still meaningfully slows a single-IP
# brute force without affecting a real user who mistypes their password.
@limiter.limit("5/minute")
async def login(
    request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    # form_data.username bypasses UserCreate's normalize_email_case (it's
    # a raw OAuth2 form field, not validated through EmailStr the way
    # signup is) — lower it here too, or a user who signed up with
    # capitals in their email gets a false "incorrect email or password"
    # typing it in lowercase. isprintable() strips control characters
    # (newlines, carriage returns, etc.) for the same reason: nothing
    # containing one could ever match a real EmailStr-validated stored
    # email anyway, but leaving them in would let a crafted "username"
    # forge fake lines in a file-based log via the warning below
    # (CWE-117 — log injection isn't just a theoretical category item,
    # this field was a real path into it until this filter).
    normalized_email = "".join(ch for ch in form_data.username.lower() if ch.isprintable())
    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()

    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is not None and is_locked_out(user):
        # verify_password still runs (its result is discarded) purely so
        # this branch's timing doesn't become a cheap way to distinguish
        # "locked out" from "wrong password" — the HTTP response is
        # deliberately byte-for-byte the SAME generic 401 either way (see
        # app/login_lockout.py's docstring for why: revealing lockout
        # state would itself be an account-enumeration leak). Only this
        # log line tells the two apart.
        verify_password(form_data.password, user.hashed_password)
        logger.warning("Login attempt against locked-out account: %s", normalized_email)
        raise credentials_error

    if not user or not verify_password(form_data.password, user.hashed_password):
        if user is not None:
            record_failed_login(user)
            await db.commit()
        # Email is logged (it's the username being attempted, not a
        # secret), the password never is, successful or not.
        logger.warning("Failed login attempt for %s", normalized_email)
        raise credentials_error

    if not user.is_active:
        # Checked separately from the password check above, with its own
        # message — "your credentials are fine, your account is the
        # problem" is a meaningfully different thing to tell a user than
        # "wrong password". get_current_user (app/security.py) re-checks
        # this on every subsequent request too, so even a token issued
        # before deactivation stops working immediately.
        logger.warning("Login rejected for deactivated account: %s", user.id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

    # Password (and account-active) checks are done — the lockout
    # counter resets here regardless of whether 2FA, below, then also
    # succeeds: lockout exists to stop PASSWORD guessing specifically,
    # and that part just succeeded. A wrong 2FA code afterward is a
    # separate failure mode, rate-limited on its own (see verify_2fa).
    record_successful_login(user)

    if user.totp_enabled:
        mfa_token = issue_mfa_challenge(db, user.id)
        await db.commit()
        logger.info("Password accepted for user %s; awaiting 2FA code", user.id)
        return MfaChallengeResponse(mfa_token=mfa_token)

    access_token = create_access_token(user.id)
    refresh_token = issue_refresh_token(db, user.id)
    await db.commit()
    logger.info("User %s logged in", user.id)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/login/verify-2fa", response_model=TokenPair)
# Same tightness as /login itself — a 6-digit TOTP code is a much
# smaller space than a password, so the code-guessing side of this
# needs at least as much rate-limiting as the password side already
# gets, not less.
@limiter.limit("5/minute")
async def verify_2fa(request: Request, payload: Verify2FARequest, db: AsyncSession = Depends(get_db)):
    challenge = await get_valid_mfa_challenge(db, payload.mfa_token)
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired login challenge")

    user = await db.get(User, challenge.user_id)
    if user is None or not user.is_active or not user.totp_enabled:
        # Mirrors /refresh's own re-check of is_active — an account
        # deactivated (or that's had 2FA disabled) in the few minutes
        # between /login and this call shouldn't be able to complete it.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired login challenge")

    code_valid = False
    if user.totp_secret_encrypted is not None:
        code_valid = verify_totp_code(decrypt_totp_secret(user.totp_secret_encrypted), payload.code)
    if not code_valid:
        # A backup code works here too — accepted as a fallback for "I
        # don't have my device", not a lesser-checked alternative.
        code_valid = await verify_and_consume_backup_code(db, user.id, payload.code)

    if not code_valid:
        logger.warning("Invalid 2FA code for user %s", user.id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid code")

    # Single-use: the challenge is spent the moment a valid code clears
    # it, whether or not the rest of this request somehow fails later.
    challenge.used_at = datetime.now(UTC)
    access_token = create_access_token(user.id)
    refresh_token = issue_refresh_token(db, user.id)
    await db.commit()
    logger.info("User %s completed 2FA login", user.id)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh_access_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    stored = await get_valid_refresh_token(db, payload.refresh_token)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user = await db.get(User, stored.user_id)
    if user is None or not user.is_active:
        # Mirrors get_current_user's own is_active check (app/security.py)
        # — a refresh token issued before deactivation must not be usable
        # to mint a fresh access token after the account is deactivated;
        # otherwise deactivation would only bite once the current access
        # token's own short expiry caught up with it.
        logger.warning("Refresh rejected for deactivated/missing account: %s", stored.user_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been deactivated")

    # Rotate: the presented token is single-use. Revoking it here (not
    # just reading it, which get_valid_refresh_token already did read-only)
    # means a stolen-and-replayed copy of this exact token fails outright
    # the moment the legitimate client has already rotated past it.
    stored.revoked_at = datetime.now(UTC)
    new_access_token = create_access_token(user.id)
    new_refresh_token = issue_refresh_token(db, user.id)
    await db.commit()
    logger.info("Refreshed tokens for user %s", user.id)
    return TokenPair(access_token=new_access_token, refresh_token=new_refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Revokes exactly the one session this refresh token belongs to —
    other devices/sessions for the same user keep working. Always 204,
    even for an unknown/already-revoked token: logout isn't a place to
    leak whether a given token string ever existed."""
    stored = await get_valid_refresh_token(db, payload.refresh_token)
    if stored is not None:
        stored.revoked_at = datetime.now(UTC)
        await db.commit()


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Revokes every refresh token for the current user — 'log out
    everywhere'. Requires a valid ACCESS token (not a refresh token),
    unlike /logout and /refresh: this is a request about the account as a
    whole, not about one specific session's own refresh token."""
    await revoke_all_refresh_tokens_for_user(db, current_user.id)
    await db.commit()
    logger.info("User %s logged out of all sessions", current_user.id)


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """No auth required — this is reached by clicking a link in an
    email, not from an already-authenticated session (signup's own
    returned tokens notwithstanding; the link has to work on its own)."""
    stored = await get_valid_email_token(db, payload.token, EmailTokenPurpose.verify_email)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link")

    user = await db.get(User, stored.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired verification link")

    stored.used_at = datetime.now(UTC)
    user.email_verified = True
    await db.commit()
    logger.info("Email verified for user %s", user.id)


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
# Same reasoning as signup's own limit (app/routers/users.py) — this
# sends an email, so it needs the same abuse-rate ceiling signup does.
@limiter.limit("5/hour")
async def resend_verification(
    request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    if current_user.email_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is already verified")

    # Invalidate any earlier still-pending verification link before
    # issuing a new one — only the one just sent should ever work.
    await invalidate_pending_tokens(db, current_user.id, EmailTokenPurpose.verify_email)
    raw_token = issue_email_token(db, current_user.id, EmailTokenPurpose.verify_email)
    await db.commit()

    await send_email(
        current_user.email,
        "Verify your email",
        f"Click to verify your email: {settings.frontend_base_url}/verify-email?token={raw_token}",
    )
    logger.info("Resent verification email to user %s", current_user.id)


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
# Same reasoning as signup's own limit — this sends an email, and the
# target is attacker-chosen (any email address), not necessarily the
# caller's own account, so it's also a harassment vector without a limit.
@limiter.limit("5/hour")
async def forgot_password(request: Request, payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Always returns the same generic response regardless of whether
    `email` is actually registered — anything that differed (a 404 for
    unknown emails, a faster/slower response) would let this endpoint be
    used to enumerate which emails have accounts, the same class of leak
    already closed for login (see CLAUDE.md's case-normalization fix)."""
    normalized_email = payload.email.lower()
    result = await db.execute(select(User).where(User.email == normalized_email))
    user = result.scalar_one_or_none()

    if user is not None:
        await invalidate_pending_tokens(db, user.id, EmailTokenPurpose.reset_password)
        raw_token = issue_email_token(db, user.id, EmailTokenPurpose.reset_password)
        await db.commit()
        await send_email(
            user.email,
            "Reset your password",
            f"Click to reset your password: {settings.frontend_base_url}/reset-password?token={raw_token}",
        )
        logger.info("Password reset requested for user %s", user.id)
    else:
        logger.info("Password reset requested for unregistered email %s", normalized_email)

    return {"detail": "If that email is registered, a password reset link has been sent"}


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    stored = await get_valid_email_token(db, payload.token, EmailTokenPurpose.reset_password)
    if stored is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")

    user = await db.get(User, stored.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset link")

    stored.used_at = datetime.now(UTC)
    user.hashed_password = hash_password(payload.new_password)
    # A credential change invalidates every existing session, not just
    # whichever one triggered it — if the reset was prompted by a
    # compromised account, leaving old refresh tokens alive would let
    # whoever had them keep minting fresh access tokens right through
    # the "fix".
    await revoke_all_refresh_tokens_for_user(db, user.id)
    await db.commit()
    logger.info("Password reset completed for user %s", user.id)
