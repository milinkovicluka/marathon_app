from datetime import date

from ui.main_window import (
    _daily_tick_interval,
    _format_day,
    _weekly_label_step,
)


def test_format_day_without_weekday():
    assert _format_day(date(2026, 11, 1)) == "1 Nov"


def test_format_day_with_weekday():
    assert _format_day(date(2026, 10, 31), with_weekday=True) == "Sat 31 Oct"


def test_weekly_labels_stay_dense_up_to_16_weeks():
    assert _weekly_label_step(12) == 1
    assert _weekly_label_step(16) == 1


def test_weekly_labels_thin_after_16_weeks():
    assert _weekly_label_step(17) == 2
    assert _weekly_label_step(32) == 2
    assert _weekly_label_step(33) == 4


def test_daily_labels_thin_as_the_range_grows():
    assert _daily_tick_interval(8) == 1
    assert _daily_tick_interval(11) == 2
    assert _daily_tick_interval(25) == 4
