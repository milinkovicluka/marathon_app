from datetime import timedelta

from core.formatting import format_duration, format_pace


def test_format_pace():
    assert format_pace(timedelta(minutes=5, seconds=30)) == "5:30/km"


def test_format_pace_rounds_up_to_next_minute():
    assert format_pace(timedelta(minutes=5, seconds=59.7)) == "6:00/km"


def test_format_pace_none():
    assert format_pace(None) == "n/a"


def test_format_duration():
    assert format_duration(timedelta(hours=1, minutes=5, seconds=3)) == "1:05:03"


def test_format_duration_under_an_hour():
    assert format_duration(timedelta(minutes=55)) == "0:55:00"
