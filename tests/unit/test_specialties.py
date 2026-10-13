"""
Pure logic on app/specialties.py — no DB, no HTTP.
"""
import pytest
from pydantic import BaseModel, ValidationError

from app.specialties import SPECIALTIES, SPECIALTY_CATEGORIES, Specialty


class _Model(BaseModel):
    specialty: Specialty


def test_known_specialty_is_accepted():
    assert _Model(specialty="fade").specialty == "fade"


def test_unknown_specialty_is_rejected():
    with pytest.raises(ValidationError):
        _Model(specialty="not-a-real-specialty")


@pytest.mark.parametrize(
    "slug,expected_categories",
    [
        ("coily", {"hair", "barber"}),  # texture: shared between hair and barber
        ("fade", {"barber"}),
        ("locs", {"hair"}),
        ("gel", {"nails"}),
        ("bridal", {"makeup"}),
        ("facial", {"skincare"}),
    ],
)
def test_specialty_maps_to_the_right_categories(slug, expected_categories):
    assert SPECIALTY_CATEGORIES[slug] == frozenset(expected_categories)


def test_specialties_set_matches_the_mapping_keys():
    # SPECIALTIES is derived from SPECIALTY_CATEGORIES — guards against
    # the two ever being edited out of sync.
    assert frozenset(SPECIALTY_CATEGORIES) == SPECIALTIES
