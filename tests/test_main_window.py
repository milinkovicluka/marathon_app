import os
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate, QSize
from PySide6.QtWidgets import QApplication, QToolButton

from core.countdown import RACE_START_TIME
from core.models import Activity
from core.storage import Storage
from ui.main_window import MainWindow
from ui.theme import build_stylesheet


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    application.setStyleSheet(build_stylesheet())
    return application


@pytest.fixture
def window(app, tmp_path):
    main_window = MainWindow(Storage(tmp_path / "test.db"))
    main_window.resize(1120, 840)
    main_window.show()
    app.processEvents()
    yield main_window
    main_window.close()


def _fixed_today(monkeypatch, year=2026, month=11, day=1):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(year, month, day)

    monkeypatch.setattr("ui.main_window.date", FakeDate)
    return FakeDate.today()


def test_form_date_max_moves_forward_at_midnight(window, monkeypatch):
    today = _fixed_today(monkeypatch)
    window._last_reload_date = today - timedelta(days=1)
    window.date_edit.setMaximumDate(QDate(2026, 10, 31))

    window._on_timer()

    assert window.date_edit.maximumDate().toString("yyyy-MM-dd") == "2026-11-01"


def test_progress_controls_have_only_requested_periods_and_metrics(window):
    assert [
        window.period_buttons[period].text()
        for period in ("7 Days", "4 Weeks", "6 Months", "1 Year")
    ] == ["7 Days", "4 Weeks", "6 Months", "1 Year"]
    assert [
        window.chart_metric.itemText(index)
        for index in range(window.chart_metric.count())
    ] == ["Activities", "Kilometers", "Time"]
    assert window.chart_activity_filter.currentText() == "Run"
    assert window.chart_metric.currentText() == "Activities"
    assert window.period_buttons["7 Days"].isChecked()
    race_day = RACE_START_TIME.date()
    assert window.countdown_title.text() == (
        f"PRAGUE MARATHON · {race_day.day} {race_day:%b %Y}".upper()
    )
    for button in (window.period_back_button, window.period_forward_button):
        assert button.text() == ""
        assert not button.icon().isNull()
        icon_image = button.icon().pixmap(QSize(18, 18)).toImage()
        assert any(
            icon_image.pixelColor(x, y).name() == "#ffffff"
            for x in range(icon_image.width())
            for y in range(icon_image.height())
        )


def test_current_period_stops_at_today_and_cannot_go_forward(
    window,
    monkeypatch,
):
    today = _fixed_today(monkeypatch)
    window._refresh_chart([])

    assert window.period_range_label.text() == "26 Oct–1 Nov 2026"
    assert not window.period_forward_button.isEnabled()
    assert window.period_back_button.isEnabled()

    window.period_back_button.click()

    assert window.period_range_label.text() == "19–25 Oct 2026"
    assert window.period_forward_button.isEnabled()
    assert window._progress_period_offset == -1

    window.period_forward_button.click()

    assert window.period_range_label.text() == "26 Oct–1 Nov 2026"
    assert not window.period_forward_button.isEnabled()
    assert window._progress_period_offset == 0
    assert today == date(2026, 11, 1)


def test_period_button_resets_navigation_to_current_period(
    window,
    monkeypatch,
):
    _fixed_today(monkeypatch)
    window.period_back_button.click()
    window.period_buttons["4 Weeks"].click()

    assert window._progress_period == "4 Weeks"
    assert window._progress_period_offset == 0
    assert window.period_range_label.text() == "5 Oct–1 Nov 2026"
    assert not window.period_forward_button.isEnabled()
    assert len(window.chart_axes.lines[0].get_ydata()) == 3
    assert list(window.chart_axes.lines[1].get_ydata()) == [0, 0]


def test_metric_and_activity_filter_update_graph_values(
    window,
    monkeypatch,
):
    _fixed_today(monkeypatch)
    window.storage.add(
        Activity(
            date=date(2026, 10, 26),
            type="run",
            distance_km=5,
            duration=timedelta(minutes=25),
        )
    )
    window.storage.add(
        Activity(
            date=date(2026, 10, 28),
            type="bike",
            distance_km=12,
            duration=timedelta(minutes=30),
        )
    )
    window._reload()
    window.chart_activity_filter.setCurrentText("Run")

    assert list(window.chart_axes.lines[0].get_ydata()) == [1, 0, 0, 0, 0, 0]
    assert list(window.chart_axes.lines[1].get_ydata()) == [0, 0]

    window.chart_metric.setCurrentText("Kilometers")
    assert list(window.chart_axes.lines[0].get_ydata()) == [5, 0, 0, 0, 0, 0]
    assert list(window.chart_axes.lines[1].get_ydata()) == [0, 0]
    assert window.chart_axes.get_ylabel() == "Kilometers"

    window.chart_metric.setCurrentText("Time")
    assert list(window.chart_axes.lines[0].get_ydata()) == pytest.approx(
        [25 / 60, 0, 0, 0, 0, 0]
    )
    assert window.chart_axes.get_ylabel() == "Hours"

    window.chart_activity_filter.setCurrentText("Bike")
    assert list(window.chart_axes.lines[0].get_ydata()) == pytest.approx(
        [0, 0, 0.5, 0, 0, 0]
    )


def test_four_weeks_aggregates_activities_by_week(window, monkeypatch):
    _fixed_today(monkeypatch)
    for day, distance in ((5, 3), (12, 4), (26, 5)):
        window.storage.add(
            Activity(
                date=date(2026, 10, day),
                type="run",
                distance_km=distance,
                duration=timedelta(minutes=30),
            )
        )
    window._reload()
    window.period_buttons["4 Weeks"].click()
    window.chart_metric.setCurrentText("Kilometers")

    assert list(window.chart_axes.lines[0].get_ydata()) == [3, 4, 0]
    assert list(window.chart_axes.lines[1].get_ydata()) == [0, 5]
    assert window.chart_axes.lines[1].get_linestyle() == "--"
    assert [tick.get_text() for tick in window.chart_axes.get_xticklabels()] == [
        "5 Oct",
        "12 Oct",
        "19 Oct",
        "26 Oct",
    ]


def test_month_periods_use_monthly_points(window, monkeypatch):
    _fixed_today(monkeypatch)
    window.period_buttons["6 Months"].click()

    assert window.period_range_label.text() == "1 Jun–1 Nov 2026"
    assert len(window.chart_axes.lines[0].get_ydata()) == 5
    assert len(window.chart_axes.lines[1].get_ydata()) == 2
    assert len(window.chart_axes.get_xticklabels()) == 6
    assert [tick.get_text() for tick in window.chart_axes.get_xticklabels()] == [
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
    ]

    window.period_buttons["1 Year"].click()
    assert window.period_range_label.text() == "1 Dec 2025–1 Nov 2026"
    assert len(window.chart_axes.lines[0].get_ydata()) == 11
    assert len(window.chart_axes.lines[1].get_ydata()) == 2
    assert len(window.chart_axes.get_xticklabels()) == 12


def test_current_month_uses_dashed_segment_and_hollow_endpoint(
    window,
    monkeypatch,
):
    _fixed_today(monkeypatch)
    window.storage.add(
        Activity(
            date=date(2026, 10, 15),
            type="run",
            distance_km=215,
            duration=timedelta(hours=15),
        )
    )
    window.storage.add(
        Activity(
            date=date(2026, 11, 1),
            type="run",
            distance_km=15,
            duration=timedelta(hours=1),
        )
    )
    window._reload()
    window.period_buttons["6 Months"].click()
    window.chart_metric.setCurrentText("Kilometers")

    solid_line, partial_segment, partial_endpoint = window.chart_axes.lines

    assert list(solid_line.get_ydata()) == [0, 0, 0, 0, 215]
    assert list(partial_segment.get_ydata()) == [215, 15]
    assert partial_segment.get_linestyle() == "--"
    assert list(partial_endpoint.get_ydata()) == [15]
    assert partial_endpoint.get_markerfacecolor() == "none"


def test_calendar_dims_dates_outside_shown_month_and_highlights_weekends(window):
    calendar = window.date_edit.calendarWidget()
    calendar.setCurrentPage(2026, 11)

    previous_month = calendar.date_color(QDate(2026, 10, 31))
    current_weekday = calendar.date_color(QDate(2026, 11, 2))
    current_weekend = calendar.date_color(QDate(2026, 11, 1))
    following_month = calendar.date_color(QDate(2026, 12, 1))

    assert previous_month.name() == "#8a90a2"
    assert following_month.name() == "#8a90a2"
    assert current_weekday.name() == "#e6e8ef"
    assert current_weekend.name() == "#00e5ff"


def test_calendar_month_navigation_arrows_are_white(window):
    calendar = window.date_edit.calendarWidget()
    checked_buttons = 0
    for name in (
        "qt_calendar_prevmonth",
        "qt_calendar_nextmonth",
        "qt_calendar_prevyear",
        "qt_calendar_nextyear",
    ):
        button = calendar.findChild(QToolButton, name)
        if button is None:
            continue
        checked_buttons += 1
        assert not button.icon().isNull()
        image = button.icon().pixmap(QSize(18, 18)).toImage()
        assert any(
            image.pixelColor(x, y).name() == "#ffffff"
            for x in range(image.width())
            for y in range(image.height())
        )
    assert checked_buttons >= 2


def test_calendar_does_not_show_week_numbers(window):
    calendar = window.date_edit.calendarWidget()

    assert (
        calendar.verticalHeaderFormat()
        == calendar.VerticalHeaderFormat.NoVerticalHeader
    )


def test_tab_from_date_goes_to_type_even_with_macos_focus_rules(window, app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    focus_flags = window.type_combo.focusPolicy().value
    assert focus_flags & Qt.FocusPolicy.StrongFocus.value == Qt.FocusPolicy.StrongFocus.value

    window.date_edit.setFocus()
    window.date_edit.select_section(2)
    QTest.keyClick(window.date_edit, Qt.Key.Key_Tab)
    app.processEvents()
    assert app.focusWidget() is window.type_combo


def _fill_interval_run(window):
    from PySide6.QtCore import QTime

    window.type_combo.setCurrentText("run")
    window.distance_spin.setValue(9.6)
    window.duration_edit.setTime(QTime(0, 46, 0))
    for km, minutes, seconds in ((2, 4, 0), (1, 3, 50)):
        window.segment_distance_spin.setValue(km)
        window.segment_pace_edit.setTime(QTime(0, minutes, seconds))
        window._add_segment()


def test_segments_are_added_saved_shown_and_loaded_for_edit(window):
    _fill_interval_run(window)
    assert window.segment_list.count() == 2
    assert window.segment_list.item(0).text() == "2 km @ 4:00"

    window._on_save()

    [saved] = window.storage.list_activities()
    assert [segment.distance_km for segment in saved.segments] == [2, 1]
    assert window.activity_table.horizontalHeaderItem(5).text() == "Segments"
    assert window.activity_table.item(0, 5).text() == "2 km @ 4:00 · 1 km @ 3:50"
    assert window.segment_list.count() == 0

    window._edit_row(0)
    assert window.segment_list.count() == 2
    window.segment_list.setCurrentRow(0)
    window._remove_segment()
    window._on_save()
    assert [
        segment.distance_km for segment in window.storage.list_activities()[0].segments
    ] == [1]


def test_segments_editor_is_hidden_and_ignored_for_gym(window):
    _fill_interval_run(window)
    window.type_combo.setCurrentText("gym")
    assert window.segment_editor.isHidden()

    window._on_save()

    [saved] = window.storage.list_activities()
    assert saved.type == "gym"
    assert saved.segments == ()


def test_empty_segment_is_rejected_with_a_message(window, monkeypatch):
    warnings = []
    monkeypatch.setattr(
        "ui.main_window.QMessageBox.warning",
        lambda *args: warnings.append(args[2]),
    )
    window._add_segment()
    assert warnings and window.segment_list.count() == 0


def test_sport_is_offered_in_form_and_chart_filter(window):
    form_types = [window.type_combo.itemText(i) for i in range(window.type_combo.count())]
    assert form_types == ["run", "bike", "gym", "sport", "rest"]
    filter_types = [
        window.chart_activity_filter.itemData(i) or window.chart_activity_filter.itemText(i)
        for i in range(window.chart_activity_filter.count())
    ]
    assert "sport" in filter_types
