from datetime import date, timedelta
from typing import Literal

from core.models import ACTIVITY_TYPES, Activity, ActivityType

ProgressPeriod = Literal["7 Days", "4 Weeks", "6 Months", "1 Year"]
ProgressMetric = Literal["Activities", "Kilometers", "Time"]


def _runs(activities: list[Activity]) -> list[Activity]:
    return [activity for activity in activities if activity.type == "run"]


def _runs_in_week(activities: list[Activity], monday: date) -> list[Activity]:
    sunday = monday + timedelta(days=6)
    return [
        activity
        for activity in _runs(activities)
        if monday <= activity.date <= sunday
    ]


def km_in_week(activities: list[Activity], day: date) -> float:
    monday = day - timedelta(days=day.weekday())
    return sum(
        (activity.distance_km for activity in _runs_in_week(activities, monday)),
        start=0.0,
    )


def progress_series(
    activities: list[Activity],
    start: date,
    end: date,
    period: ProgressPeriod,
    metric: ProgressMetric,
    activity_type: ActivityType | Literal["all"] = "run",
) -> list[tuple[date, float]]:
    if start > end:
        return []
    if period not in ("7 Days", "4 Weeks", "6 Months", "1 Year"):
        raise ValueError(f"Unknown progress period: {period}")
    if metric not in ("Activities", "Kilometers", "Time"):
        raise ValueError(f"Unknown progress metric: {metric}")
    if activity_type != "all" and activity_type not in ACTIVITY_TYPES:
        raise ValueError(f"Unknown activity type: {activity_type}")

    if period == "7 Days":
        bucket_starts = [
            start + timedelta(days=offset)
            for offset in range((end - start).days + 1)
        ]
        bucket_days = 1
    elif period == "4 Weeks":
        bucket_starts = [
            start + timedelta(weeks=offset)
            for offset in range((end - start).days // 7 + 1)
        ]
        bucket_days = 7
    else:
        first_month = date(start.year, start.month, 1)
        first_month_index = first_month.year * 12 + first_month.month - 1
        last_month_index = end.year * 12 + end.month - 1
        bucket_starts = [
            date(
                (first_month_index + offset) // 12,
                (first_month_index + offset) % 12 + 1,
                1,
            )
            for offset in range(last_month_index - first_month_index + 1)
        ]
        bucket_days = 0

    eligible_activities = [
        activity
        for activity in activities
        if start <= activity.date <= end
        and (activity_type == "all" or activity.type == activity_type)
    ]
    result: list[tuple[date, float]] = []
    for index, bucket_start in enumerate(bucket_starts):
        if bucket_days:
            bucket_end = min(
                bucket_start + timedelta(days=bucket_days - 1),
                end,
            )
        elif index + 1 < len(bucket_starts):
            bucket_end = min(
                bucket_starts[index + 1] - timedelta(days=1),
                end,
            )
        else:
            bucket_end = end

        bucket_activities = [
            activity
            for activity in eligible_activities
            if bucket_start <= activity.date <= bucket_end
        ]
        if metric == "Activities":
            value = float(len(bucket_activities))
        elif metric == "Kilometers":
            value = sum(
                activity.distance_km for activity in bucket_activities
            )
        else:
            value = sum(
                activity.duration.total_seconds()
                for activity in bucket_activities
            ) / 3600
        result.append((bucket_start, value))
    return result


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
