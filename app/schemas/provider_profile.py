import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.provider_profile import ServiceCategory


class ProviderProfileCreate(BaseModel):
    business_name: str
    bio: str | None = None
    years_experience: int | None = None
    # min_length=1: a provider must declare at least one thing they do —
    # an empty list would make them unfindable/unbookable.
    categories: list[ServiceCategory] = Field(min_length=1)


class ProviderProfilePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    business_name: str
    bio: str | None
    years_experience: int | None
    categories: list[ServiceCategory]
    created_at: datetime
