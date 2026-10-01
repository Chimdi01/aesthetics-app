"""
Pure Pydantic validation for ProviderAvailabilityUpdate — no DB, no HTTP.
Split shifts (multiple ranges on the same day) are allowed as long as
they don't overlap; that overlap check is the one piece of real logic
here and can't be expressed as a single-row DB CheckConstraint (see
app/models/provider_availability.py), so it's worth covering directly.
"""
import pytest
from pydantic import ValidationError

from app.schemas.provider_availability import ProviderAvailabilityUpdate


def _entry(day, start, end):
    return {"day_of_week": day, "start_time": start, "end_time": end}


def test_empty_schedule_is_valid():
    ProviderAvailabilityUpdate(schedule=[])


def test_single_range_per_day_is_valid():
    ProviderAvailabilityUpdate(schedule=[_entry("monday", "09:00", "17:00")])


def test_non_overlapping_split_shift_on_same_day_is_valid():
    ProviderAvailabilityUpdate(
        schedule=[
            _entry("monday", "09:00", "12:00"),
            _entry("monday", "14:00", "18:00"),
        ]
    )


def test_touching_ranges_are_not_overlapping():
    # 09:00-12:00 followed immediately by 12:00-15:00 — back-to-back, not overlapping.
    ProviderAvailabilityUpdate(
        schedule=[
            _entry("monday", "09:00", "12:00"),
            _entry("monday", "12:00", "15:00"),
        ]
    )


def test_overlapping_ranges_on_same_day_are_rejected():
    with pytest.raises(ValidationError):
        ProviderAvailabilityUpdate(
            schedule=[
                _entry("monday", "09:00", "13:00"),
                _entry("monday", "12:00", "17:00"),
            ]
        )


def test_overlap_check_is_per_day_not_global():
    # Same time range, but different days — not a conflict.
    ProviderAvailabilityUpdate(
        schedule=[
            _entry("monday", "09:00", "17:00"),
            _entry("tuesday", "09:00", "17:00"),
        ]
    )


def test_end_time_before_start_time_is_rejected():
    with pytest.raises(ValidationError):
        ProviderAvailabilityUpdate(schedule=[_entry("monday", "17:00", "09:00")])


def test_end_time_equal_to_start_time_is_rejected():
    with pytest.raises(ValidationError):
        ProviderAvailabilityUpdate(schedule=[_entry("monday", "09:00", "09:00")])


def test_invalid_day_of_week_is_rejected():
    with pytest.raises(ValidationError):
        ProviderAvailabilityUpdate(schedule=[_entry("someday", "09:00", "17:00")])
