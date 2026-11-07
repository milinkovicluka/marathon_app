from datetime import date, timedelta

import pytest

from core.models import Activity


def make_run(**overrides):
    fields = dict(
        date=date(2026, 11, 1),
        type="run",
        distance_km=10.0,
        duration=timedelta(minutes=55),
    )
    fields.update(overrides)
    return Activity(**fields)


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
        make_run(distance_km=-1.0)


def test_activity_rejects_negative_duration():
    with pytest.raises(ValueError, match="duration cannot be negative"):
        make_run(duration=timedelta(minutes=-5))


def test_rejects_run_with_zero_duration():
    with pytest.raises(ValueError):
        make_run(duration=timedelta(0))


def test_rejects_bike_with_zero_duration():
    with pytest.raises(ValueError):
        make_run(type="bike", duration=timedelta(0))


def test_rest_allows_zero_duration_and_distance():
    activity = make_run(
        type="rest",
        distance_km=0,
        duration=timedelta(0),
    )

    assert activity.pace is None


def test_activity_rejects_unknown_type():
    with pytest.raises(ValueError, match="unknown activity type"):
        make_run(type="swim")


def test_activity_rejects_nan_distance():
    with pytest.raises(ValueError, match="distance_km must be finite"):
        make_run(distance_km=float("nan"))


def test_activity_rejects_infinite_distance():
    with pytest.raises(ValueError, match="distance_km must be finite"):
        make_run(distance_km=float("inf"))


def test_pace_per_km():
    assert make_run().pace == timedelta(minutes=5, seconds=30)


def test_pace_is_none_without_distance():
    assert make_run(type="gym", distance_km=0).pace is None


def test_segment_pace_and_from_pace():
    from core.models import Segment

    segment = Segment.from_pace(2, timedelta(minutes=4))
    assert segment.duration == timedelta(minutes=8)
    assert segment.pace == timedelta(minutes=4)


@pytest.mark.parametrize(
    ("distance_km", "duration"),
    [(0, timedelta(minutes=4)), (-1, timedelta(minutes=4)), (1, timedelta(0))],
)
def test_segment_rejects_empty_or_negative_values(distance_km, duration):
    from core.models import Segment

    with pytest.raises(ValueError):
        Segment(distance_km=distance_km, duration=duration)


def test_segments_must_fit_inside_activity_distance():
    from core.models import Segment

    with pytest.raises(ValueError, match="more than"):
        Activity(
            date=date(2026, 11, 5),
            type="run",
            distance_km=2.5,
            duration=timedelta(minutes=15),
            segments=(Segment.from_pace(2, timedelta(minutes=4)),) * 2,
        )


def test_gym_and_rest_cannot_have_segments():
    from core.models import Segment

    with pytest.raises(ValueError, match="can't have segments"):
        Activity(
            date=date(2026, 11, 5),
            type="gym",
            distance_km=0,
            duration=timedelta(minutes=60),
            segments=(Segment.from_pace(1, timedelta(minutes=4)),),
        )


def test_sport_covers_other_activities_without_distance():
    activity = Activity(
        date=date(2026, 11, 3),
        type="sport",
        distance_km=0,
        duration=timedelta(minutes=90),
        notes="pingpong",
    )
    assert activity.pace is None
