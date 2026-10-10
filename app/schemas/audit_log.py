import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.audit_log import AuditAction, AuditTargetType


class AuditLogPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    admin_id: uuid.UUID
    action: AuditAction
    target_type: AuditTargetType
    target_id: uuid.UUID | None
    details: dict
    created_at: datetime
