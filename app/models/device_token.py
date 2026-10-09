"""
Backs mobile/web push notifications (app/push.py, app/notifications.py)
— registered by a client (a mobile app, once one exists; see CLAUDE.md)
via PATCH... POST /v1/users/me/device-tokens after the OS/FCM SDK hands
it a token. One row per device/app-install, not per user — a user can
have several (phone + tablet, or having reinstalled), so this is a
many-rows-per-user table, unlike NotificationPreference's 1:1.

`token` is globally unique, not scoped to a user: a real device token
identifies one specific app installation, and the same physical device
reassigning it to a different User (a logout/login as someone else on
a shared or reinstalled app) is a real scenario — see
app/routers/users.py's register_device_token, which upserts on this
column (reassigning user_id if the token already exists) rather than
allowing duplicates.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DevicePlatform(str, enum.Enum):
    ios = "ios"
    android = "android"
    web = "web"


class DeviceToken(Base):
    __tablename__ = "device_tokens"
    __table_args__ = (
        # "every device for this user" (sending a push, listing in a
        # future device-management screen) is the only query shape
        # besides the unique lookup by token itself.
        Index("ix_device_tokens_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    # 500 comfortably covers real FCM (~150-200 chars) and APNs (64 hex
    # chars) tokens with headroom, without being an unbounded column.
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    platform: Mapped[DevicePlatform] = mapped_column(Enum(DevicePlatform, name="deviceplatform"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
