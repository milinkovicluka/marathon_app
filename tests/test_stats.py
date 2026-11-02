from datetime import date, timedelta

import pytest

from core.models import Activity, ActivityType
from core.stats import (
    average_pace,
    km_in_week,
    longest_run,
    progress_series,
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


def test_daily_progress_buckets_activity_count_distance_and_time():
    kwargs = {
        "activities": WEEK,
        "start": date(2026, 11, 1),
        "end": date(2026, 11, 4),
        "period": "7 Days",
    }

    assert progress_series(**kwargs, metric="Activities") == [
        (date(2026, 11, 1), 1),
        (date(2026, 11, 2), 1),
        (date(2026, 11, 3), 0),
        (date(2026, 11, 4), 1),
    ]
    assert progress_series(**kwargs, metric="Kilometers") == [
        (date(2026, 11, 1), 12),
        (date(2026, 11, 2), 8),
        (date(2026, 11, 3), 0),
        (date(2026, 11, 4), 10),
    ]
    assert [value for _, value in progress_series(**kwargs, metric="Time")] == (
        pytest.approx([70 / 60, 44 / 60, 0, 52 / 60])
    )


def test_weekly_progress_includes_empty_weeks_and_filters_activity_type():
    runs_with_a_gap = [
        act(date(2026, 10, 26), 12, 70),
        act(date(2026, 11, 9), 9, 50),
    ]
    series = progress_series(
        runs_with_a_gap,
        start=date(2026, 10, 26),
        end=date(2026, 11, 22),
        period="4 Weeks",
        metric="Kilometers",
    )
    assert series == [
        (date(2026, 10, 26), 12),
        (date(2026, 11, 2), 0),
        (date(2026, 11, 9), 9),
        (date(2026, 11, 16), 0),
    ]

    all_activities = progress_series(
        WEEK,
        start=date(2026, 11, 2),
        end=date(2026, 11, 8),
        period="4 Weeks",
        metric="Activities",
        activity_type="all",
    )
    assert all_activities == [(date(2026, 11, 2), 4)]


def test_monthly_progress_respects_selected_range_and_activity_type():
    series = progress_series(
        WEEK,
        start=date(2026, 10, 1),
        end=date(2026, 11, 4),
        period="6 Months",
        metric="Kilometers",
    )
    assert series == [
        (date(2026, 10, 1), 0),
        (date(2026, 11, 1), 30),
    ]

    all_activities = progress_series(
        WEEK,
        start=date(2026, 11, 1),
        end=date(2026, 11, 8),
        period="1 Year",
        metric="Activities",
        activity_type="all",
    )
    assert all_activities == [(date(2026, 11, 1), 5)]


def test_progress_series_empty_range():
    assert progress_series(
        WEEK,
        start=date(2026, 11, 4),
        end=date(2026, 11, 1),
        period="7 Days",
        metric="Kilometers",
    ) == []


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
