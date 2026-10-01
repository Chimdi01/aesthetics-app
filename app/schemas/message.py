import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        # Postgres rejects "\x00" in text columns at the driver level,
        # which would otherwise surface as an unhandled 500 instead of a
        # clean 422 (same reasoning as ReviewCreate.comment).
        if "\x00" in value:
            raise ValueError("body must not contain null bytes")
        if not value.strip():
            raise ValueError("body must not be blank")
        return value


class MessagePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    created_at: datetime
