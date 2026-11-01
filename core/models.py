import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, get_args

ActivityType = Literal["run", "bike", "gym", "rest"]
ACTIVITY_TYPES = get_args(ActivityType)


@dataclass
class Activity:
    date: date
    type: ActivityType
    distance_km: float
    duration: timedelta
    notes: str = ""
    id: int | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(self.distance_km):
            raise ValueError("distance_km must be finite")
        if self.distance_km < 0:
            raise ValueError("distance_km cannot be negative")
        if self.duration < timedelta(0):
            raise ValueError("duration cannot be negative")
        if self.type in ("run", "bike") and self.duration == timedelta(0):
            raise ValueError(f"{self.type} duration must be greater than zero")
        if self.type not in ACTIVITY_TYPES:
            raise ValueError(f"unknown activity type: {self.type}")

    @property
    def pace(self) -> timedelta | None:
        if self.distance_km == 0:
            return None
        return self.duration / self.distance_km
