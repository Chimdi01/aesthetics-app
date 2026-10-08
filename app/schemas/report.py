import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.report import ReportReason, ReportStatus


class ReportCreate(BaseModel):
    reason: ReportReason
    details: str | None = Field(default=None, max_length=2000)

    @field_validator("details")
    @classmethod
    def reject_embedded_null_bytes(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("details must not contain null bytes")
        return value


class ReportPublic(BaseModel):
    """What the reporting user sees about their own report."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reported_user_id: uuid.UUID
    reason: ReportReason
    details: str | None
    status: ReportStatus
    created_at: datetime


class ReportAdminPublic(BaseModel):
    """What an admin sees while triaging — includes who filed it and who
    (if anyone) already resolved it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reporter_id: uuid.UUID
    reported_user_id: uuid.UUID
    reason: ReportReason
    details: str | None
    status: ReportStatus
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime


class ReportReviewUpdate(BaseModel):
    status: ReportStatus

    @field_validator("status")
    @classmethod
    def reject_setting_back_to_pending(cls, value: ReportStatus) -> ReportStatus:
        # status has no default (it's a required field), so unlike
        # VerificationReviewUpdate's rejection_reason check, a plain
        # field_validator is fine here — there's no "skipped because the
        # field was left at its default" risk (see CLAUDE.md).
        if value == ReportStatus.pending:
            raise ValueError("status must be 'resolved' or 'dismissed'")
        return value
