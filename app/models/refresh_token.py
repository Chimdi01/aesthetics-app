"""
Backs JWT refresh tokens (app/refresh_tokens.py). Deliberately NOT a JWT
itself — see app/secret_tokens.py's docstring for why — just an opaque
random value whose SHA-256 hash is the only thing ever stored here.

revoked_at (nullable) rather than a separate boolean + a delete: keeping
a revoked row (instead of deleting it) means a replayed, already-used
token can be told apart from a token that never existed at all — both
matter for rotation (see app/refresh_tokens.py) and for debugging a
"why did my session get logged out" question later.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        # "every active token for this user" (logout-all, and the
        # is_active-deactivation path) and "find this token" (token_hash
        # alone, already unique-indexed) are the two query shapes this
        # table ever sees.
        Index("ix_refresh_tokens_user_id_revoked_at", "user_id", "revoked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # sha256 hex digest is always exactly 64 characters.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
