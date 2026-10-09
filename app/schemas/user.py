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

from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    # min_length=8, no complexity rules (no "must contain a symbol" etc.)
    # — current NIST guidance (SP 800-63B) is that length matters far
    # more than enforced complexity, and complexity rules mostly just
    # push people toward predictable substitutions. No max_length either:
    # bcrypt's 72-byte input limit is already handled in app/security.py
    # (see the passlib/bcrypt pinning gotcha in CLAUDE.md), so a long
    # password doesn't need rejecting here, just hashing correctly.
    password: str = Field(min_length=8)  # plain text in the request; we hash it before saving
    full_name: str
    role: UserRole = UserRole.customer

    @field_validator("email")
    @classmethod
    def normalize_email_case(cls, value: str) -> str:
        # Without this, "User@x.com" and "user@x.com" register as two
        # different accounts (the DB unique constraint is case-sensitive)
        # and a user who typed capitals at signup gets a false "incorrect
        # password" if they type it lowercase at login — login normalizes
        # the same way (see app/routers/auth.py) so the two stay matched.
        return value.lower()

    @field_validator("role")
    @classmethod
    def reject_admin_signup(cls, value: UserRole) -> UserRole:
        # POST /v1/users/ is public and unauthenticated — without this,
        # anyone could self-register with role="admin" and get a fully
        # privileged account instantly. Admin accounts are provisioned
        # out-of-band (a direct DB update by the operator, see CLAUDE.md),
        # never through this endpoint.
        if value == UserRole.admin:
            raise ValueError("admin accounts cannot be created via signup")
        return value


class UserPublic(BaseModel):
    # Tells Pydantic it's fine to read this straight from a SQLAlchemy
    # object's attributes (user.id, user.email, ...), not just a dict.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserSummary(BaseModel):
    """What GET /users/{id} returns when the caller is looking at
    someone ELSE (see app/routers/users.py) — no email, no is_active.
    Email is PII a stranger has no reason to see; is_active would leak
    a moderation action taken against someone to anyone who asks. The
    caller sees their own full UserPublic, and so does an admin."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    role: UserRole
    created_at: datetime


class UserStatusUpdate(BaseModel):
    """Admin-only (see app/routers/admin.py) — never part of UserCreate;
    an account always starts active."""

    is_active: bool
