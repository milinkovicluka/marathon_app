from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from core.countdown import time_until_race, format_countdown

PRAGUE = ZoneInfo("Europe/Prague")

def test_exactly_one_day_before():
    now = datetime(2027, 5, 1, 8, 0, tzinfo=PRAGUE)
    assert time_until_race(now) == timedelta(days=1)

def test_across_dst_change():
    # 28 Mar 2027 clocks jump forward, so one real hour disappears
    now = datetime(2027, 3, 1, 8, 0, tzinfo=PRAGUE)
    assert time_until_race(now) == timedelta(days=62, hours=-1)

def test_format_days_and_hours():
    assert format_countdown(timedelta(days=185, hours=12, minutes=30)) == "185d 12h"

def test_format_after_start():
    assert format_countdown(timedelta(seconds=-1)) == "🏁"