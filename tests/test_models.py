from datetime import date, timedelta

import pytest

from core.models import Activity


def test_activity_defaults_and_pace():
    activity = Activity(
        date=date(2027, 5, 1),
        type="run",
        distance_km=10.0,
        duration=timedelta(minutes=50),
    )

    assert activity.notes == ""
    assert activity.id is None
    assert activity.pace == timedelta(minutes=5)


def test_activity_without_distance_has_no_pace():
    activity = Activity(
        date=date(2027, 5, 1),
        type="rest",
        distance_km=0.0,
        duration=timedelta(0),
    )

    assert activity.pace is None


def test_activity_rejects_negative_distance():
    with pytest.raises(ValueError, match="distance_km cannot be negative"):
        Activity(
            date=date(2027, 5, 1),
            type="run",
            distance_km=-1.0,
            duration=timedelta(minutes=5),
        )


def test_activity_rejects_negative_duration():
    with pytest.raises(ValueError, match="duration cannot be negative"):
        Activity(
            date=date(2027, 5, 1),
            type="run",
            distance_km=1.0,
            duration=timedelta(minutes=-5),
        )


def test_activity_rejects_unknown_type():
    with pytest.raises(ValueError, match="unknown activity type"):
        Activity(
            date=date(2027, 5, 1),
            type="swim",  # type: ignore[arg-type]
            distance_km=1.0,
            duration=timedelta(minutes=5),
        )

from datetime import date, timedelta
import pytest
from core.models import Activity

def make_run(**overrides):
    fields = dict(date=date(2026, 11, 1), type="run", distance_km=10.0,
                  duration=timedelta(minutes=55))
    fields.update(overrides)
    return Activity(**fields)

def test_pace_per_km():
    assert make_run().pace == timedelta(minutes=5, seconds=30)

def test_pace_is_none_without_distance():
    assert make_run(type="gym", distance_km=0).pace is None

def test_rejects_negative_distance():
    with pytest.raises(ValueError):
        make_run(distance_km=-1)

def test_rejects_unknown_type():
    with pytest.raises(ValueError):
        make_run(type="swim")