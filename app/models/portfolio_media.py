"""
A single photo or video in a provider's portfolio. `file_path` is a path
relative to settings.media_root, never a client-facing URL — the router
builds the servable URL from it. Keeping that detail out of the model
(and out of every other layer except app/storage.py, which owns writing
and deleting the actual bytes) is what lets the storage backend change
later (e.g. to S3) without touching the model, schema, or router.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MediaType(str, enum.Enum):
    photo = "photo"
    video = "video"


class PortfolioMedia(Base):
    __tablename__ = "portfolio_media"
    __table_args__ = (
        # GET /providers/{id}/portfolio filters on provider_profile_id and
        # sorts by created_at — one composite index for both.
        Index("ix_portfolio_media_provider_profile_id_created_at", "provider_profile_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provider_profiles.id"), nullable=False
    )
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType, name="mediatype"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
