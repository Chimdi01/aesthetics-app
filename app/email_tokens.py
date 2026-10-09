"""
Lifecycle for the single-use tokens behind email verification and
password reset (see app/models/email_token.py for why they share one
table). Same convention as app/refresh_tokens.py: functions here only
mutate the given AsyncSession — the calling router commits once.
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_token import EmailToken, EmailTokenPurpose
from app.secret_tokens import generate_raw_token, hash_token


def _expiry_for(purpose: EmailTokenPurpose) -> timedelta:
    # A function, not a module-level dict built at import time: reading
    # settings.* lazily here (rather than baking the configured values in
    # at import) means a test that monkeypatches settings still takes
    # effect, and it keeps this file from caring about import order
    # relative to app/config.py.
    if purpose is EmailTokenPurpose.verify_email:
        return timedelta(hours=settings.email_verification_token_expire_hours)
    return timedelta(minutes=settings.password_reset_token_expire_minutes)


def issue_email_token(db: AsyncSession, user_id: uuid.UUID, purpose: EmailTokenPurpose) -> str:
    """Stages a new EmailToken row on `db` and returns the RAW token —
    the value that goes into the email link; only its hash is stored."""
    raw_token = generate_raw_token()
    db.add(
        EmailToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + _expiry_for(purpose),
        )
    )
    return raw_token


async def get_valid_email_token(db: AsyncSession, raw_token: str, purpose: EmailTokenPurpose) -> EmailToken | None:
    """Looks up raw_token and returns the row only if it matches the
    expected purpose and is neither used nor expired. Checking `purpose`
    here (not just the hash) means a password-reset token can never be
    replayed against the verify-email endpoint or vice versa, even
    though both are looked up the same way."""
    result = await db.execute(
        select(EmailToken).where(EmailToken.token_hash == hash_token(raw_token), EmailToken.purpose == purpose)
    )
    stored = result.scalar_one_or_none()
    if stored is None or stored.used_at is not None or stored.expires_at < datetime.now(UTC):
        return None
    return stored


async def invalidate_pending_tokens(db: AsyncSession, user_id: uuid.UUID, purpose: EmailTokenPurpose) -> None:
    """Marks every still-valid, not-yet-used token of this purpose for
    this user as used. Called right before issuing a fresh one (resend
    verification, a repeated forgot-password request) so only the
    latest link a user was sent can ever actually work — an older email
    sitting in an inbox (or a shared mailbox, or a scraped-and-leaked
    message) silently stops being valid instead of staying live in
    parallel with the new one."""
    await db.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user_id, EmailToken.purpose == purpose, EmailToken.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )
