import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.identity_verification import DocumentType, VerificationStatus


class VerificationPublic(BaseModel):
    """What the submitting user sees about their own submission —
    deliberately no file_path, reviewed_by, or anything about other
    users' submissions."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_type: DocumentType
    status: VerificationStatus
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime


class VerificationAdminPublic(BaseModel):
    """What an admin sees while reviewing — includes whose submission
    this is and who (if anyone) already reviewed it, still never the
    file_path (the document is fetched through its own streaming
    endpoint, not exposed as a path string)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    document_type: DocumentType
    status: VerificationStatus
    rejection_reason: str | None
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class VerificationReviewUpdate(BaseModel):
    status: VerificationStatus
    rejection_reason: str | None = Field(default=None, max_length=1000)

    # A single model_validator, not two field_validators — a
    # field_validator on rejection_reason wouldn't even run when the
    # field is omitted (Pydantic v2 skips validators for fields left at
    # their default unless validate_default=True), which is exactly the
    # "no reason given" case this needs to catch. mode="after" always
    # runs regardless of which fields were actually supplied.
    @model_validator(mode="after")
    def validate_status_and_reason(self):
        # An admin reviews and decides — "pending" isn't a decision, it's
        # the state before one. Resubmission (not an admin action) is
        # what puts a row back into pending; see app/routers/verification.py.
        if self.status == VerificationStatus.pending:
            raise ValueError("status must be 'approved' or 'rejected'")
        if self.status == VerificationStatus.rejected and not self.rejection_reason:
            raise ValueError("rejection_reason is required when rejecting")
        return self
