from datetime import date

from ui.main_window import _format_date_range, _format_day, _progress_period_bounds


def test_format_day():
    assert _format_day(date(2026, 11, 1)) == "1 Nov"


def test_format_date_range():
    assert _format_date_range(date(2026, 10, 26), date(2026, 11, 1)) == (
        "26 Oct–1 Nov 2026"
    )
    assert _format_date_range(date(2026, 10, 5), date(2026, 11, 1)) == (
        "5 Oct–1 Nov 2026"
    )
    assert _format_date_range(date(2025, 12, 1), date(2026, 11, 1)) == (
        "1 Dec 2025–1 Nov 2026"
    )


def test_seven_day_period_moves_back_in_full_weeks():
    today = date(2026, 11, 1)

    assert _progress_period_bounds("7 Days", 0, today) == (
        date(2026, 10, 26),
        date(2026, 11, 1),
    )
    assert _progress_period_bounds("7 Days", -1, today) == (
        date(2026, 10, 19),
        date(2026, 10, 25),
    )


def test_four_week_period_moves_back_in_full_four_week_blocks():
    today = date(2026, 11, 1)

    assert _progress_period_bounds("4 Weeks", 0, today) == (
        date(2026, 10, 5),
        date(2026, 11, 1),
    )
    assert _progress_period_bounds("4 Weeks", -1, today) == (
        date(2026, 9, 7),
        date(2026, 10, 4),
    )


def test_month_periods_are_calendar_aligned():
    today = date(2026, 11, 1)

    assert _progress_period_bounds("6 Months", 0, today) == (
        date(2026, 6, 1),
        date(2026, 11, 30),
    )
    assert _progress_period_bounds("6 Months", -1, today) == (
        date(2025, 12, 1),
        date(2026, 5, 31),
    )
    assert _progress_period_bounds("1 Year", 0, today) == (
        date(2025, 12, 1),
        date(2026, 11, 30),
    )


def test_unknown_period_is_rejected():
    try:
        _progress_period_bounds("2 Years", 0, date(2026, 11, 1))
    except ValueError as error:
        assert str(error) == "Unknown progress period: 2 Years"
    else:
        raise AssertionError("unknown progress period should be rejected")
