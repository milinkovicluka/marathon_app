from datetime import date, timedelta

from core.models import Activity


def km_in_week(activities: list[Activity], day: date) -> float:
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    return sum(
        activity.distance_km
        for activity in activities
        if activity.type == "run" and monday <= activity.date <= sunday
    )


def longest_run(activities: list[Activity]) -> Activity | None:
    runs = [activity for activity in activities if activity.type == "run"]
    return max(runs, key=lambda activity: activity.distance_km, default=None)


def average_pace(activities: list[Activity]) -> timedelta | None:
    runs = [activity for activity in activities if activity.type == "run"]
    total_distance = sum(activity.distance_km for activity in runs)
    if total_distance == 0:
        return None

    total_duration = sum(
        (activity.duration for activity in runs),
        start=timedelta(),
    )
    return total_duration / total_distance
