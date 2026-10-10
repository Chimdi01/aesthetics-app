"""
An append-only record of every admin action taken against someone
else's data — the gap flagged in CLAUDE.md: before this, "who
deactivated this account, when, why" only lived in the generic
request/application logs (fine for live debugging, not a durable or
easily queryable record for an actual incident review).

Deliberately scoped to ADMIN actions only (app/routers/admin.py) — a
user managing their own account (disabling their own 2FA, updating
their own phone number) isn't what this is for; this is specifically
"an admin did something to someone else's data or to the platform."

No API ever updates or deletes a row here (nothing in this codebase
calls db.delete() on an AuditLog, and there's no PATCH/DELETE endpoint
for it) — append-only at the application level. An admin with direct
database access could still tamper with it; that's the same trust
boundary already accepted everywhere else in this app (e.g. admin
accounts themselves only exist via a direct DB update — see
CLAUDE.md), not a new gap introduced here.

target_id is nullable: a platform-wide action (revoke-all-sessions)
has no single target row to point at.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AuditAction(str, enum.Enum):
    verification_reviewed = "verification_reviewed"
    report_reviewed = "report_reviewed"
    user_status_changed = "user_status_changed"
    provider_status_changed = "provider_status_changed"
    sessions_revoked = "sessions_revoked"


class AuditTargetType(str, enum.Enum):
    user = "user"
    provider_profile = "provider_profile"
    identity_verification = "identity_verification"
    report = "report"
    # No single row — see the module docstring on target_id.
    platform = "platform"


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # The admin-facing listing's two real query shapes: "everything
        # this admin has done" and "everything that's happened to this
        # target", both newest-first.
        Index("ix_audit_logs_admin_id_created_at", "admin_id", "created_at"),
        Index("ix_audit_logs_target_type_target_id_created_at", "target_type", "target_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction, name="auditaction"), nullable=False)
    target_type: Mapped[AuditTargetType] = mapped_column(
        Enum(AuditTargetType, name="audittargettype"), nullable=False
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Action-specific structured detail (e.g. {"is_active": false},
    # {"status": "approved"}, {"revoked_count": 42}) — a JSONB column
    # rather than a fixed set of nullable typed columns, since each
    # action's "what changed" shape is genuinely different and none of
    # them need to be queried ON individually (only read back for
    # display, and filtered by action/target/admin above instead).
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
