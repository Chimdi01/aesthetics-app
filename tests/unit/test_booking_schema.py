"""
Pure Pydantic validation on BookingCreate — no DB, no HTTP.
"""
import pytest
from pydantic import ValidationError

from app.schemas.booking import BookingCreate

BASE = {
    "provider_profile_id": "00000000-0000-0000-0000-000000000000",
    "category": "hair",
    "visit_type": "shop_visit",
    "scheduled_at": "2027-01-01T10:00:00Z",
}


def test_booking_create_allows_zero_price():
    booking = BookingCreate(**BASE, price=0)
    assert booking.price == 0


def test_booking_create_rejects_negative_price():
    with pytest.raises(ValidationError):
        BookingCreate(**BASE, price=-1)


def test_booking_create_rejects_negative_transport_fee():
    with pytest.raises(ValidationError):
        BookingCreate(**BASE, transport_fee=-0.01)


def test_booking_create_allows_missing_price_and_fee():
    booking = BookingCreate(**BASE)
    assert booking.price is None
    assert booking.transport_fee is None


def test_house_call_without_address_is_rejected():
    with pytest.raises(ValidationError):
        BookingCreate(**{**BASE, "visit_type": "house_call"})


def test_house_call_with_address_is_valid():
    booking = BookingCreate(**{**BASE, "visit_type": "house_call", "address": "123 Main St"})
    assert booking.address == "123 Main St"
