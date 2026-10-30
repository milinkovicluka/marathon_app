from datetime import date, timedelta

from core.models import Activity


def _runs(activities: list[Activity]) -> list[Activity]:
    return [activity for activity in activities if activity.type == "run"]


def km_in_week(activities: list[Activity], day: date) -> float:
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    return sum(
        (
            activity.distance_km
            for activity in _runs(activities)
            if monday <= activity.date <= sunday
        ),
        start=0.0,
    )


def longest_run(activities: list[Activity]) -> Activity | None:
    return max(_runs(activities), key=lambda activity: activity.distance_km, default=None)


def average_pace(activities: list[Activity]) -> timedelta | None:
    runs_with_distance = [run for run in _runs(activities) if run.distance_km > 0]
    total_distance = sum(run.distance_km for run in runs_with_distance)
    if total_distance == 0:
        return None

    total_duration = sum(
        (run.duration for run in runs_with_distance),
        start=timedelta(),
    )
    return total_duration / total_distance
