"""
Refresh-token lifecycle for JWT auth. Access tokens (app/security.py)
are short-lived, stateless JWTs with no way to revoke one before it
expires; refresh tokens are the deliberate opposite — long-lived,
opaque, DB-backed (see app/secret_tokens.py's docstring for why not a
JWT) — precisely so a single session CAN be revoked (logout, "log out
everywhere", a future password reset forcing re-login everywhere)
without waiting out its own expiry.

Functions here only mutate the given AsyncSession (add/update) — none
of them call db.commit() themselves. The calling router commits once,
matching this codebase's existing convention (see e.g.
app/routers/portfolio.py's upload_portfolio_media) rather than each
helper owning its own transaction boundary.
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.refresh_token import RefreshToken
from app.secret_tokens import generate_raw_token, hash_token


def issue_refresh_token(db: AsyncSession, user_id: uuid.UUID) -> str:
    """Stages a new RefreshToken row on `db` and returns the RAW token to
    hand back to the client — the only place that value ever exists
    outside the client's own storage; everything stored here is its hash."""
    raw_token = generate_raw_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
    )
    return raw_token


async def get_valid_refresh_token(db: AsyncSession, raw_token: str) -> RefreshToken | None:
    """Looks up raw_token and returns the row only if it's neither
    revoked nor expired — the one check both /auth/refresh and
    /auth/logout need before acting on a presented token. Returns None
    (not a distinguishing error) for "doesn't exist", "already revoked",
    and "expired" alike — a caller that needs to tell those apart for
    logging can still inspect the raw lookup itself, but no endpoint
    response should, so a stolen/guessed token string can't be used to
    probe which of those three states it's in."""
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token)))
    stored = result.scalar_one_or_none()
    if stored is None or stored.revoked_at is not None or stored.expires_at < datetime.now(UTC):
        return None
    return stored


async def revoke_all_refresh_tokens_for_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Marks every still-active refresh token for a user revoked in one
    statement — used by 'log out everywhere' now, and will be reused by
    password reset later (a credential change should invalidate every
    existing session, not just whichever one triggered it)."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
