import uuid
from collections import defaultdict
from datetime import time

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.provider_availability import DayOfWeek

# No hard cap on ranges per day (a busy provider might reasonably split
# a day into 3+ blocks); the overlap check below is what keeps the
# schedule sane, not a count limit.
_MAX_SCHEDULE_ENTRIES = 50


class DayAvailability(BaseModel):
    day_of_week: DayOfWeek
    start_time: time
    end_time: time

    @model_validator(mode="after")
    def end_after_start(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class ProviderAvailabilityUpdate(BaseModel):
    # A full replacement of the weekly schedule, not per-day patches —
    # "set my working hours" is naturally one coherent action, and this
    # avoids ever reconciling a partial update against existing rows.
    # Split shifts are allowed: multiple entries with the same
    # day_of_week are fine as long as their time ranges don't overlap.
    schedule: list[DayAvailability] = Field(max_length=_MAX_SCHEDULE_ENTRIES)

    @model_validator(mode="after")
    def no_overlapping_ranges_within_a_day(self):
        by_day: dict[DayOfWeek, list[tuple[time, time]]] = defaultdict(list)
        for entry in self.schedule:
            by_day[entry.day_of_week].append((entry.start_time, entry.end_time))

        for day, ranges in by_day.items():
            ranges.sort()
            for (_, prev_end), (next_start, _) in zip(ranges, ranges[1:]):
                if next_start < prev_end:
                    raise ValueError(f"overlapping time ranges for {day.value}")
        return self


class ProviderAvailabilityPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_profile_id: uuid.UUID
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
