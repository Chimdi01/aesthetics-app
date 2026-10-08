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

from sqlalchemy import Boolean, String, Enum, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


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

    provider_profile: Mapped["ProviderProfile | None"] = relationship(
        back_populates="user", uselist=False
    )
