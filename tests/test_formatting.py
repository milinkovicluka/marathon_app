from datetime import timedelta

from core.formatting import format_pace


def test_format_pace():
    assert format_pace(timedelta(minutes=5, seconds=30)) == "5:30/km"


def test_format_pace_rounds_up_to_next_minute():
    assert format_pace(timedelta(minutes=5, seconds=59.7)) == "6:00/km"


def test_format_pace_none():
    assert format_pace(None) == "n/a"
