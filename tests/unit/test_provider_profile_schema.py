"""
Pure Pydantic validation for the location fields on ProviderProfileCreate —
no DB, no HTTP. The PostGIS side (distance/radius queries) needs a real
database and is covered in tests/regression/test_provider_search.py.
"""
import pytest
from pydantic import ValidationError

from app.models.provider_profile import AddressType
from app.schemas.provider_profile import ProviderProfileCreate

BASE = {"business_name": "Jane's Studio", "categories": ["hair"]}


def test_profile_without_location_is_valid():
    profile = ProviderProfileCreate(**BASE)
    assert profile.latitude is None and profile.longitude is None


def test_profile_with_full_location_is_valid():
    profile = ProviderProfileCreate(**BASE, latitude=51.5, longitude=-0.12, address_type="shop")
    assert profile.address_type == AddressType.shop


def test_latitude_without_longitude_is_rejected():
    with pytest.raises(ValidationError):
        ProviderProfileCreate(**BASE, latitude=51.5, address_type="shop")


def test_longitude_without_latitude_is_rejected():
    with pytest.raises(ValidationError):
        ProviderProfileCreate(**BASE, longitude=-0.12, address_type="shop")


def test_location_without_address_type_is_rejected():
    with pytest.raises(ValidationError):
        ProviderProfileCreate(**BASE, latitude=51.5, longitude=-0.12)


@pytest.mark.parametrize("lat,lon", [(90.1, 0), (-90.1, 0), (0, 180.1), (0, -180.1)])
def test_out_of_range_coordinates_are_rejected(lat, lon):
    with pytest.raises(ValidationError):
        ProviderProfileCreate(**BASE, latitude=lat, longitude=lon, address_type="home")


@pytest.mark.parametrize("lat,lon", [(90, 180), (-90, -180), (0, 0)])
def test_boundary_coordinates_are_accepted(lat, lon):
    ProviderProfileCreate(**BASE, latitude=lat, longitude=lon, address_type="home")
