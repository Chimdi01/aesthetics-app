"""
Separate from app/schemas/user.py — describes the DeviceToken resource,
same reasoning as every other schemas/ split in this codebase.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.device_token import DevicePlatform


class DeviceTokenRegister(BaseModel):
    token: str
    platform: DevicePlatform


class DeviceTokenPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: DevicePlatform
    created_at: datetime
    # Deliberately NOT including the raw token value in any response —
    # it's a bearer-ish credential for pushing to that one device
    # (same spirit as never echoing back a password or refresh token
    # in a GET), and nothing ever needs to read it back out of the API.
