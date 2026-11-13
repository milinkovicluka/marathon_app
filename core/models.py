import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, get_args

ActivityType = Literal["run", "bike", "gym", "sport", "rest"]
ACTIVITY_TYPES = get_args(ActivityType)


SEGMENT_TYPES = ("run", "bike")


@dataclass(frozen=True)
class Segment:
    """One part of a workout, e.g. a 2 km interval at 4:00/km."""

    distance_km: float
    duration: timedelta

    def __post_init__(self) -> None:
        if not math.isfinite(self.distance_km) or self.distance_km <= 0:
            raise ValueError("segment distance must be greater than zero")
        if self.duration <= timedelta(0):
            raise ValueError("segment duration must be greater than zero")

    @classmethod
    def from_pace(cls, distance_km: float, pace: timedelta) -> "Segment":
        return cls(distance_km=distance_km, duration=pace * distance_km)

    @property
    def pace(self) -> timedelta:
        return self.duration / self.distance_km


@dataclass
class Activity:
    date: date
    type: ActivityType
    distance_km: float
    duration: timedelta
    notes: str = ""
    id: int | None = None
    segments: tuple[Segment, ...] = field(default_factory=tuple)
    # Where an imported activity came from, e.g. "fit:2026-11-07T06:56:44+00:00";
    # used to skip a file that was already imported.
    source_id: str | None = None

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
        self.segments = tuple(self.segments)
        if self.segments and self.type not in SEGMENT_TYPES:
            raise ValueError(f"{self.type} can't have segments")
        segment_km = sum(segment.distance_km for segment in self.segments)
        # Half of the 0.01 km the form shows, so rounding never blocks a save.
        if segment_km > self.distance_km + 0.005:
            raise ValueError(
                f"segments add up to {segment_km:g} km, "
                f"more than the {self.distance_km:g} km distance"
            )

    @property
    def pace(self) -> timedelta | None:
        if self.distance_km == 0:
            return None
        return self.duration / self.distance_km
