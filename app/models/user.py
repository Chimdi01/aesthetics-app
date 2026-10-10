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

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, func
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
    # Tracked, not yet ENFORCED anywhere (login, bookings, etc. all work
    # regardless of this value) — whether/where to gate on it is a
    # product decision flagged separately (see CLAUDE.md), not assumed
    # here. server_default="false": a brand-new account hasn't verified
    # anything yet; see app/routers/users.py for where this gets set to
    # true (POST /v1/auth/verify-email) and app/routers/auth.py's
    # resend-verification for re-sending the link.
    email_verified: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    # Per-ACCOUNT login lockout (app/login_lockout.py) — a second,
    # independent layer on top of app/rate_limit.py's per-IP limit on
    # POST /auth/login. The per-IP limit alone doesn't stop a slow,
    # distributed brute force spread across many IPs against this ONE
    # account; this does, by tracking consecutive failures on the
    # account itself regardless of which IP they came from.
    failed_login_attempts: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    login_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Optional, added via PATCH /v1/users/me/phone-number — not
    # collected at signup, not verified (same "tracked, not enforced"
    # posture as email_verified above). app/notifications.py only sends
    # an SMS when this is set; a user who never adds one just gets email
    # notifications. No uniqueness constraint — unlike email, nothing in
    # this app treats a phone number as an account identifier.
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 2FA (app/totp.py). totp_secret_encrypted is set as soon as
    # enrollment starts (POST /v1/users/me/2fa/enroll) but
    # totp_enabled stays False until the user proves they actually
    # copied the secret into their authenticator app (POST
    # /v1/users/me/2fa/confirm) — login only branches into the 2FA
    # challenge once totp_enabled is True, so a half-finished
    # enrollment never locks anyone out. Encrypted, not hashed — see
    # app/totp_encryption.py's docstring for why (the app needs the
    # real value back to compute a code, unlike a password).
    totp_secret_encrypted: Mapped[str | None] = mapped_column(String(255), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Same circular-import-avoidance forward reference as the "User"
    # string in app/models/provider_profile.py — see that file's comment
    # and the TYPE_CHECKING import above.
    provider_profile: Mapped["ProviderProfile | None"] = relationship(back_populates="user", uselist=False)
