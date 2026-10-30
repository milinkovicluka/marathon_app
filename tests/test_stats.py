from datetime import date, timedelta

from core.models import Activity, ActivityType
from core.stats import average_pace, km_in_week, longest_run


def act(
    day: date,
    km: float,
    minutes: int,
    type: ActivityType = "run",
) -> Activity:
    return Activity(
        date=day,
        type=type,
        distance_km=km,
        duration=timedelta(minutes=minutes),
    )


WEEK = [
    act(date(2026, 11, 1), 12, 70),
    act(date(2026, 11, 2), 8, 44),
    act(date(2026, 11, 4), 10, 52),
    act(date(2026, 11, 8), 18, 105),
    act(date(2026, 11, 5), 40, 90, "bike"),
]


def test_km_in_week_counts_monday_to_sunday_runs_only():
    assert km_in_week(WEEK, date(2026, 11, 4)) == 36


def test_km_in_week_empty():
    assert km_in_week([], date(2026, 11, 4)) == 0


def test_longest_run_ignores_bike():
    assert longest_run(WEEK).distance_km == 18


def test_longest_run_none_when_no_runs():
    assert longest_run([]) is None


def test_average_pace_is_weighted_by_distance():
    runs = [act(date(2026, 11, 2), 10, 50), act(date(2026, 11, 3), 5, 35)]
    assert average_pace(runs) == timedelta(minutes=5, seconds=40)


def test_average_pace_none_without_runs():
    assert average_pace([]) is None


def test_average_pace_ignores_runs_without_distance():
    runs = [act(date(2026, 11, 2), 10, 50), act(date(2026, 11, 3), 0, 30)]
    assert average_pace(runs) == timedelta(minutes=5)
