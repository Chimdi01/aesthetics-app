"""
Pure Pydantic validation on UserCreate — no DB, no HTTP. The admin-signup
rejection is a real security boundary (see app/schemas/user.py), not just
input hygiene, so it gets its own direct test rather than only being
covered indirectly through a regression test.
"""
import pytest
from pydantic import ValidationError

from app.schemas.user import PhoneNumberUpdate, UserCreate


def test_user_create_defaults_to_customer_role():
    user = UserCreate(email="a@example.com", password="secret123", full_name="A")
    assert user.role.value == "customer"


def test_user_create_accepts_provider_role():
    user = UserCreate(email="a@example.com", password="secret123", full_name="A", role="provider")
    assert user.role.value == "provider"


def test_user_create_rejects_admin_role():
    with pytest.raises(ValidationError):
        UserCreate(email="a@example.com", password="secret123", full_name="A", role="admin")


def test_user_create_normalizes_email_to_lowercase():
    user = UserCreate(email="User@Example.com", password="secret123", full_name="A")
    assert user.email == "user@example.com"


def test_user_create_accepts_password_at_minimum_length():
    user = UserCreate(email="a@example.com", password="12345678", full_name="A")
    assert user.password == "12345678"


def test_user_create_rejects_password_under_minimum_length():
    with pytest.raises(ValidationError):
        UserCreate(email="a@example.com", password="1234567", full_name="A")


# --- PhoneNumberUpdate's E.164 validation ---


def test_phone_number_update_accepts_valid_e164():
    update = PhoneNumberUpdate(phone_number="+14155552671")
    assert update.phone_number == "+14155552671"


def test_phone_number_update_accepts_none_to_clear():
    update = PhoneNumberUpdate(phone_number=None)
    assert update.phone_number is None


@pytest.mark.parametrize(
    "bad_number",
    [
        "4155552671",  # missing leading +
        "+0155552671",  # leading digit after + can't be 0
        "+1 415 555 2671",  # spaces
        "+1-415-555-2671",  # dashes
        "not-a-number",
        "+1",  # too short
    ],
)
def test_phone_number_update_rejects_invalid_formats(bad_number):
    with pytest.raises(ValidationError):
        PhoneNumberUpdate(phone_number=bad_number)
