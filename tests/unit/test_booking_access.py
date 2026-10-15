"""
app/booking_access.py's authorize_booking_party, without a database:
the one DB lookup it makes (the owning provider profile) is patched out.
"""
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.booking_access import authorize_booking_party
from app.errors import AppError, ErrorCode
from app.models.booking import Booking
from app.models.provider_profile import ProviderProfile
from app.models.user import User, UserRole

CUSTOMER_ID = uuid.uuid4()
PROVIDER_USER_ID = uuid.uuid4()


def _booking() -> Booking:
    return Booking(id=uuid.uuid4(), customer_id=CUSTOMER_ID, provider_profile_id=uuid.uuid4())


def _patch_owner():
    profile = ProviderProfile(id=uuid.uuid4(), user_id=PROVIDER_USER_ID)
    return patch("app.booking_access.get_owning_provider_profile", AsyncMock(return_value=profile))


async def test_stranger_gets_forbidden_app_error():
    stranger = User(id=uuid.uuid4(), role=UserRole.customer)
    with _patch_owner(), pytest.raises(AppError) as exc_info:
        await authorize_booking_party(db=None, booking=_booking(), current_user=stranger)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 403
    assert exc_info.value.error_code == ErrorCode.forbidden
    assert exc_info.value.detail == "Not your booking"


async def test_customer_and_provider_are_identified():
    customer = User(id=CUSTOMER_ID, role=UserRole.customer)
    provider = User(id=PROVIDER_USER_ID, role=UserRole.provider)
    with _patch_owner():
        assert await authorize_booking_party(None, _booking(), customer) == (True, False)  # type: ignore[arg-type]
        assert await authorize_booking_party(None, _booking(), provider) == (False, True)  # type: ignore[arg-type]
