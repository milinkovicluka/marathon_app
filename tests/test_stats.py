from datetime import date, timedelta

import pytest

from core.models import Activity, ActivityType
from core.stats import (
    average_pace,
    daily_km_series,
    km_in_week,
    linear_trend,
    longest_run,
    weekly_km_series,
)


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


def test_weekly_series_covers_whole_weeks_in_range():
    series = weekly_km_series(
        WEEK,
        start=date(2026, 10, 28),
        end=date(2026, 11, 4),
    )
    assert series == [(date(2026, 10, 26), 12), (date(2026, 11, 2), 36)]


def test_weekly_series_includes_empty_weeks():
    series = weekly_km_series(
        [],
        start=date(2026, 10, 19),
        end=date(2026, 11, 4),
    )
    assert [km for _, km in series] == [0, 0, 0]


def test_daily_series_includes_every_day_in_range():
    series = daily_km_series(
        WEEK,
        start=date(2026, 11, 1),
        end=date(2026, 11, 4),
    )
    assert series == [
        (date(2026, 11, 1), 12),
        (date(2026, 11, 2), 8),
        (date(2026, 11, 3), 0),
        (date(2026, 11, 4), 10),
    ]


def test_daily_series_sums_runs_on_same_day():
    runs = [
        act(date(2026, 11, 2), 5, 30),
        act(date(2026, 11, 2), 3, 20),
    ]
    assert daily_km_series(
        runs,
        date(2026, 11, 2),
        date(2026, 11, 2),
    ) == [(date(2026, 11, 2), 8)]


def test_daily_series_ignores_bike():
    assert daily_km_series(
        WEEK,
        date(2026, 11, 5),
        date(2026, 11, 5),
    ) == [(date(2026, 11, 5), 0)]


def test_linear_trend_on_straight_line():
    assert linear_trend([10, 20, 30]) == pytest.approx([10, 20, 30])


def test_linear_trend_fits_noisy_data():
    assert linear_trend([10, 30, 20]) == pytest.approx([15, 20, 25])


def test_linear_trend_needs_two_points():
    assert linear_trend([10]) == []


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
