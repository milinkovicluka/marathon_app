from datetime import date, timedelta

from core.models import Activity


def _runs(activities: list[Activity]) -> list[Activity]:
    return [activity for activity in activities if activity.type == "run"]


def _runs_in_week(activities: list[Activity], monday: date) -> list[Activity]:
    sunday = monday + timedelta(days=6)
    return [
        activity
        for activity in _runs(activities)
        if monday <= activity.date <= sunday
    ]


def _week_mondays(start: date, end: date) -> list[date]:
    if start > end:
        return []
    first_monday = start - timedelta(days=start.weekday())
    last_monday = end - timedelta(days=end.weekday())
    return [
        first_monday + timedelta(weeks=week_offset)
        for week_offset in range((last_monday - first_monday).days // 7 + 1)
    ]


def km_in_week(activities: list[Activity], day: date) -> float:
    monday = day - timedelta(days=day.weekday())
    return sum(
        (activity.distance_km for activity in _runs_in_week(activities, monday)),
        start=0.0,
    )


def weekly_km_series(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    return [
        (
            monday,
            sum(
                (activity.distance_km for activity in _runs_in_week(activities, monday)),
                start=0.0,
            ),
        )
        for monday in _week_mondays(start, end)
    ]


def daily_km_series(
    activities: list[Activity],
    start: date,
    end: date,
) -> list[tuple[date, float]]:
    runs = _runs(activities)
    days = (
        start + timedelta(days=day_offset)
        for day_offset in range(max(0, (end - start).days + 1))
    )
    return [
        (
            day,
            sum(
                (activity.distance_km for activity in runs if activity.date == day),
                start=0.0,
            ),
        )
        for day in days
    ]


def linear_trend(values: list[float]) -> list[float]:
    if len(values) < 2:
        return []

    x_mean = (len(values) - 1) / 2
    y_mean = sum(values) / len(values)
    slope = sum(
        (x - x_mean) * (value - y_mean)
        for x, value in enumerate(values)
    ) / sum((x - x_mean) ** 2 for x in range(len(values)))
    intercept = y_mean - slope * x_mean
    return [intercept + slope * x for x in range(len(values))]


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
