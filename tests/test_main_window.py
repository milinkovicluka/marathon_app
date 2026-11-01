import os
from datetime import date, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

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


def test_form_date_max_moves_forward_at_midnight(window, monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 11, 1)

    window._last_reload_date = date(2026, 10, 31)
    window.date_edit.setMaximumDate(QDate(2026, 10, 31))
    monkeypatch.setattr("ui.main_window.date", FakeDate)

    window._on_timer()

    assert window.date_edit.maximumDate().toString("yyyy-MM-dd") == "2026-11-01"


def test_weekly_labels_reset_rotation_after_daily(window, app):
    window.tabs.setCurrentIndex(1)
    window.chart_granularity.setCurrentText("By day")
    app.processEvents()
    window.chart_granularity.setCurrentText("By week")
    app.processEvents()

    assert all(
        label.get_rotation() == 0
        for label in window.chart_axes.get_xticklabels()
    )


def test_daily_axis_stays_inside_selected_range(window, app):
    window.tabs.setCurrentIndex(1)
    window.chart_granularity.setCurrentText("By day")
    window.chart_from_edit.setDate(QDate(2026, 10, 27))
    window.chart_to_edit.setDate(QDate(2026, 10, 29))
    app.processEvents()

    labels = {
        label.get_text()
        for label in window.chart_axes.get_xticklabels()
        if label.get_text()
    }

    assert "26 Oct" not in labels
    assert "30 Oct" not in labels


def test_weekly_chart_only_counts_selected_dates(window, app):
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
            type="run",
            distance_km=7,
            duration=timedelta(minutes=35),
        )
    )
    window._reload()
    window.tabs.setCurrentIndex(1)
    window.chart_granularity.setCurrentText("By week")
    window.chart_from_edit.setDate(QDate(2026, 10, 28))
    window.chart_to_edit.setDate(QDate(2026, 10, 29))
    app.processEvents()

    assert window.chart_axes.get_title() == (
        "Weekly distance · 28 Oct – 29 Oct · 7 km"
    )
    assert window.chart_axes.patches[0].get_height() == 7
