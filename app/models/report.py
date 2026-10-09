"""
Manual reporting/flagging — a user reports ANOTHER USER (not specifically
a provider's business profile) for a safety concern, inappropriate
behavior, fraud, spam, or something else; an admin reviews the report
queue and decides whether to act (see app/routers/admin.py).

Targets a User, not a ProviderProfile, deliberately: the roadmap's safety
narrative is two-way (customers visit providers' homes/shops now;
providers may travel to customers' homes in V2), so misbehavior can come
from either side, and a customer has no "profile" to report the way a
provider does — the actual reportable thing is always the person. A
report against a provider just uses their User.id (already exposed as
ProviderProfilePublic.user_id) rather than their ProviderProfile.id.

Resolving a report (status -> resolved/dismissed) and any resulting
deactivation are deliberately separate admin actions, not coupled — a
report can be dismissed as unfounded with no deactivation, or an account/
profile deactivated without every open report against it being
individually resolved first. Two independent deactivation levers exist
once a report leads to action: User.is_active (cuts off the account
entirely, either role) and ProviderProfile.is_active (hides just the
business listing from search/booking, provider only) — see each model's
own docstring.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ReportReason(str, enum.Enum):
    safety_concern = "safety_concern"
    inappropriate_behavior = "inappropriate_behavior"
    fraud_or_scam = "fraud_or_scam"
    spam = "spam"
    other = "other"


class ReportStatus(str, enum.Enum):
    pending = "pending"
    resolved = "resolved"
    dismissed = "dismissed"


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        # Matches the actual admin-queue query: filter by status (usually
        # "pending"), oldest first.
        Index("ix_reports_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reported_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reason: Mapped[ReportReason] = mapped_column(Enum(ReportReason, name="reportreason"), nullable=False)
    details: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus, name="reportstatus"), default=ReportStatus.pending, nullable=False
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
