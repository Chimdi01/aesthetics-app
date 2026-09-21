import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)

    @field_validator("comment")
    @classmethod
    def reject_embedded_null_bytes(cls, value: str | None) -> str | None:
        # Postgres text/varchar columns reject "\x00" at the driver level,
        # which would otherwise surface as an unhandled 500 instead of a
        # clean 422 — catch it here so bad input fails validation, not the DB write.
        if value is not None and "\x00" in value:
            raise ValueError("comment must not contain null bytes")
        return value


class ReviewPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    customer_id: uuid.UUID
    provider_profile_id: uuid.UUID
    rating: int
    comment: str | None
    created_at: datetime
