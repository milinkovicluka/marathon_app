from collections.abc import Iterable
from datetime import timedelta

from core.models import Segment


def format_pace(pace: timedelta | None) -> str:
    if pace is None:
        return "n/a"
    seconds = round(pace.total_seconds())
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes}:{seconds:02d}/km"


def format_duration(duration: timedelta) -> str:
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def format_segments(segments: Iterable[Segment]) -> str:
    """Format segments like "2 km @ 4:00 · 1 km @ 3:50" (pace per km)."""
    return " · ".join(
        f"{segment.distance_km:g} km @ {format_pace(segment.pace).removesuffix('/km')}"
        for segment in segments
    )
