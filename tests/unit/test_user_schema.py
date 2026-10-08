"""
Pure Pydantic validation on UserCreate — no DB, no HTTP. The admin-signup
rejection is a real security boundary (see app/schemas/user.py), not just
input hygiene, so it gets its own direct test rather than only being
covered indirectly through a regression test.
"""
import pytest
from pydantic import ValidationError

from app.schemas.user import UserCreate


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
