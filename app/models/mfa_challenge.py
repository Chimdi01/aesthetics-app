"""
Carries the two-step login handshake for an account with 2FA enabled —
see app/routers/auth.py's login(). Step one (email+password) succeeds
but, instead of a TokenPair, issues one of these; step two
(POST /v1/auth/login/verify-2fa) trades it plus a TOTP/backup code for
the real tokens. Deliberately NOT a JWT (same reasoning as every other
opaque token in this codebase — see app/secret_tokens.py's docstring):
it has to be revocable/single-use, and it grants NO API access on its
own, unlike an access token — it's only ever accepted by the one
endpoint that completes the login.

Short-lived on purpose (settings.mfa_challenge_expire_minutes, default
5) — it only needs to survive the round trip between "password
accepted" and "now enter your code", not be a standing credential.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MfaChallenge(Base):
    __tablename__ = "mfa_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # sha256 hex digest is always exactly 64 characters.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
