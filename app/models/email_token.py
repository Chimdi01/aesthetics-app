"""
Backs both email verification and password reset — one table, not two,
disambiguated by `purpose`. Both features need the exact same shape (a
random opaque value, single-use, expiring, tied to one user — see
app/secret_tokens.py's docstring for why not a JWT), so a separate
near-identical table per feature would just be the same logic twice.

`used_at`, not `revoked_at` (contrast app/models/refresh_token.py): the
semantics here are "consumed exactly once on success", not "invalidated
without being redeemed" — a reset/verify token that's already been used
and one that's been superseded by a newer request (see
app/email_tokens.py's invalidate_pending_tokens) both land in the same
"not usable again" bucket either way, but the field name matches what
actually happens to this kind of token specifically.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmailTokenPurpose(str, enum.Enum):
    verify_email = "verify_email"
    reset_password = "reset_password"


class EmailToken(Base):
    __tablename__ = "email_tokens"
    __table_args__ = (
        # "every still-pending token of this purpose for this user" is
        # the shape invalidate_pending_tokens queries on; token_hash
        # alone (unique) covers the other lookup shape, "find this token".
        Index("ix_email_tokens_user_id_purpose_used_at", "user_id", "purpose", "used_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    purpose: Mapped[EmailTokenPurpose] = mapped_column(
        Enum(EmailTokenPurpose, name="emailtokenpurpose"), nullable=False
    )
    # sha256 hex digest is always exactly 64 characters.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
