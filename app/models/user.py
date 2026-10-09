"""
The User model is the one table shared by customers AND providers
(hair, makeup, nails, and other beauty/aesthetics services). A 'role'
field distinguishes them rather than having two separate tables — this
keeps auth simple (one login system) while ProviderProfile (added in a
later session) holds the extra fields that only providers need
(specialties, price range, portfolio media).
"""
import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# TYPE_CHECKING-only import: this is how mypy resolves the "ProviderProfile"
# string forward-reference below without creating a real circular import at
# runtime (provider_profile.py imports this module right back for its own
# "User" forward reference — see that file's comment). Ruff's F821 also
# recognizes this pattern, so no noqa is needed either.
if TYPE_CHECKING:
    from app.models.provider_profile import ProviderProfile


class UserRole(str, enum.Enum):
    customer = "customer"
    provider = "provider"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.customer, nullable=False)
    # Admin-only moderation lever (see app/routers/admin.py), distinct
    # from ProviderProfile.is_active: this cuts off the ACCOUNT entirely
    # (login rejected, every request through get_current_user rejected —
    # see app/security.py), for either role, not just a provider's
    # business listing being hidden from search while they can still log
    # in, message, and manage existing bookings.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Same circular-import-avoidance forward reference as the "User"
    # string in app/models/provider_profile.py — see that file's comment
    # and the TYPE_CHECKING import above.
    provider_profile: Mapped["ProviderProfile | None"] = relationship(back_populates="user", uselist=False)
