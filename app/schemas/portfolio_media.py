import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.portfolio_media import MediaType


class PortfolioMediaPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_profile_id: uuid.UUID
    media_type: MediaType
    url: str
    caption: str | None
    created_at: datetime
