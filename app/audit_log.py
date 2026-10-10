"""
Writes app/models/audit_log.py rows. One function, intentionally — every
admin action in app/routers/admin.py calls this the same way, so the
shape of an audit entry can't drift between call sites.

Same convention as every other DB-mutating helper in this codebase
(app/refresh_tokens.py, app/email_tokens.py): only stages the row
(`db.add`) — never calls db.commit() itself. The calling router commits
once, alongside whatever else that request already changed, so the
audit entry and the actual change land in the same transaction (either
both happen or neither does, never one without the other).
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog, AuditTargetType


def record_audit_log(
    db: AsyncSession,
    admin_id: uuid.UUID,
    action: AuditAction,
    target_type: AuditTargetType,
    target_id: uuid.UUID | None,
    details: dict,
) -> None:
    db.add(
        AuditLog(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
        )
    )
