"""
One identity-verification submission per user — a government ID photo,
manually reviewed by an admin (see the roadmap's "manual review at this
scale" note; no third-party verification vendor is integrated). This is
what makes "a customer visits a stranger's shop/home" safer than the
status quo, and it's the trust data V2's house-call dispatch gates on.

One row per user (unique user_id), not an append-only history: a
resubmission after rejection REPLACES the existing row rather than
creating a new one (see app/routers/verification.py) — simpler than
reconstructing "what's the current status" from a log of attempts, and
nothing here needs the rejected-attempt history kept around.

file_path is a path relative to settings.verification_root — a directory
never mounted as a public route (see app/config.py). Unlike
PortfolioMedia.file_path, there is no public URL built from this; only
the submitting user themselves or an admin can ever retrieve the bytes
(see the authorization checks in app/routers/verification.py and
app/routers/admin.py).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentType(str, enum.Enum):
    passport = "passport"
    drivers_license = "drivers_license"
    national_id = "national_id"
    other = "other"


class VerificationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class IdentityVerification(Base):
    __tablename__ = "identity_verifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False
    )
    document_type: Mapped[DocumentType] = mapped_column(Enum(DocumentType, name="documenttype"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verificationstatus"), default=VerificationStatus.pending, nullable=False
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
