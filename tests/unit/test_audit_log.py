"""
Pure logic, no real DB — record_audit_log only ever calls db.add(), so a
plain object with an add() method (no real session/connection needed)
is enough to confirm it builds the right AuditLog shape and never
commits on its own (matching this codebase's "helper stages, caller
commits" convention — see CLAUDE.md).
"""
import uuid
from unittest.mock import MagicMock

from app.audit_log import record_audit_log
from app.models.audit_log import AuditAction, AuditLog, AuditTargetType


def test_record_audit_log_stages_one_row_with_the_given_fields():
    db = MagicMock()
    admin_id = uuid.uuid4()
    target_id = uuid.uuid4()

    record_audit_log(
        db, admin_id, AuditAction.user_status_changed, AuditTargetType.user, target_id, {"is_active": False}
    )

    db.add.assert_called_once()
    staged = db.add.call_args[0][0]
    assert isinstance(staged, AuditLog)
    assert staged.admin_id == admin_id
    assert staged.action == AuditAction.user_status_changed
    assert staged.target_type == AuditTargetType.user
    assert staged.target_id == target_id
    assert staged.details == {"is_active": False}


def test_record_audit_log_never_commits():
    db = MagicMock()
    record_audit_log(
        db, uuid.uuid4(), AuditAction.sessions_revoked, AuditTargetType.platform, None, {"revoked_count": 3}
    )
    db.commit.assert_not_called()
