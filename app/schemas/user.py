"""
Why these are separate from app/models/user.py:
The SQLAlchemy model describes the DATABASE TABLE. These Pydantic schemas
describe the API's INPUT and OUTPUT shapes. They often look similar, but
keeping them separate means:
  - UserCreate can require a plain-text password, while the DB never
    stores one (only hashed_password).
  - UserPublic can OMIT hashed_password entirely, so there's no risk of
    ever accidentally returning it in an API response.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, ConfigDict

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str  # plain text in the request; we hash it before saving
    full_name: str
    role: UserRole = UserRole.customer


class UserPublic(BaseModel):
    # Tells Pydantic it's fine to read this straight from a SQLAlchemy
    # object's attributes (user.id, user.email, ...), not just a dict.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    created_at: datetime
