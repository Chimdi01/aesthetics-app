"""
One-time recovery codes for 2FA (app/totp.py) — issued 10 at a time when
2FA is confirmed (POST /v1/users/me/2fa/confirm) or explicitly
regenerated (POST /v1/users/me/2fa/backup-codes/regenerate), for the
"I lost my phone" case a TOTP-only scheme has no answer for otherwise.

Hashed the same way as every other DB-backed secret in this codebase
(app/secret_tokens.py's hash_token) — a backup code is a bearer
credential just like a refresh token, so the same "only the hash is
ever stored" rule applies. Unlike refresh/email tokens though, these
are short, human-typable strings (see app/totp.py's generator), not
long URL-safe ones — hashing is what makes that safe to store at all.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TotpBackupCode(Base):
    __tablename__ = "totp_backup_codes"
    __table_args__ = (
        # "every still-unused code for this user" is the only query
        # shape this table sees (checking a login-time code against all
        # of them, and regeneration invalidating the old batch).
        Index("ix_totp_backup_codes_user_id_used_at", "user_id", "used_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # sha256 hex digest is always exactly 64 characters.
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
