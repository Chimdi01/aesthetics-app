import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.provider_profile import AddressType, ServiceCategory


class ProviderProfileCreate(BaseModel):
    business_name: str
    bio: str | None = None
    years_experience: int | None = None
    # min_length=1: a provider must declare at least one thing they do —
    # an empty list would make them unfindable/unbookable.
    categories: list[ServiceCategory] = Field(min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    address_type: AddressType | None = None

    @model_validator(mode="after")
    def require_complete_location(self):
        has_coords = (self.latitude is not None, self.longitude is not None)
        if any(has_coords) and not all(has_coords):
            raise ValueError("latitude and longitude must be provided together")
        if all(has_coords) and self.address_type is None:
            raise ValueError("address_type is required when a location is provided")
        return self


class ProviderProfilePublic(BaseModel):
    # Deliberately no latitude/longitude: a home provider's exact
    # coordinates are effectively their home address. Search exposes only
    # a rounded distance instead.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    business_name: str
    bio: str | None
    years_experience: int | None
    categories: list[ServiceCategory]
    address_type: AddressType | None
    created_at: datetime


class ProviderSearchResult(BaseModel):
    id: uuid.UUID
    business_name: str
    bio: str | None
    categories: list[ServiceCategory]
    address_type: AddressType | None
    distance_km: float
    average_rating: float | None
    review_count: int
