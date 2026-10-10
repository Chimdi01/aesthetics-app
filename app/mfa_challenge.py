"""
Lifecycle for the login-handshake token behind 2FA (see
app/models/mfa_challenge.py for what it's for). Same convention as
app/refresh_tokens.py/app/email_tokens.py: functions here only mutate
the given AsyncSession — the calling router commits once.
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.mfa_challenge import MfaChallenge
from app.secret_tokens import generate_raw_token, hash_token


def issue_mfa_challenge(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Stages a new MfaChallenge row on `db` and returns the RAW token —
    handed back in login()'s response; only its hash is ever stored."""
    raw_token = generate_raw_token()
    db.add(
        MfaChallenge(
            user_id=user_id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.mfa_challenge_expire_minutes),
        )
    )
    return raw_token


async def get_valid_mfa_challenge(db: AsyncSession, raw_token: str) -> MfaChallenge | None:
    """Looks up raw_token and returns the row only if it's neither used
    nor expired — mirrors app/refresh_tokens.py's get_valid_refresh_token.
    A single lookup covering all three "invalid" cases (doesn't exist,
    already used, expired) so a guessed/stolen token string can't be
    used to probe which one applies."""
    result = await db.execute(select(MfaChallenge).where(MfaChallenge.token_hash == hash_token(raw_token)))
    challenge = result.scalar_one_or_none()
    if challenge is None or challenge.used_at is not None or challenge.expires_at < datetime.now(UTC):
        return None
    return challenge
