import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate, QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from ui.date_edit import SegmentedDateEdit


@pytest.fixture
def form():
    app = QApplication.instance() or QApplication([])
    container = QWidget()
    layout = QVBoxLayout(container)
    before = QLineEdit(container)
    date_edit = SegmentedDateEdit(QDate(2026, 11, 5), container)
    date_edit.setDisplayFormat("ddd d MMM")
    date_edit.setMaximumDate(QDate(2026, 11, 7))
    after = QLineEdit(container)
    for widget in (before, date_edit, after):
        layout.addWidget(widget)
    container.show()
    app.processEvents()
    yield app, before, date_edit, after
    container.close()


def _selected(app, date_edit):
    app.processEvents()
    return date_edit.lineEdit().selectedText()


def test_tab_into_field_selects_whole_weekday(form):
    app, before, date_edit, _after = form
    before.setFocus()
    QTest.keyClick(before, Qt.Key.Key_Tab)
    assert app.focusWidget() is date_edit
    assert _selected(app, date_edit) == "Thu"


def test_up_and_down_change_selected_part_and_keep_it_selected(form):
    app, _before, date_edit, _after = form
    date_edit.setFocus()
    date_edit.select_section(1)
    QTest.keyClick(date_edit, Qt.Key.Key_Down)
    assert date_edit.date() == QDate(2026, 11, 4)
    assert _selected(app, date_edit) == "4"


def test_enter_and_tab_move_weekday_then_day_then_month_then_next_field(form):
    app, _before, date_edit, after = form
    date_edit.setFocus()
    date_edit.select_section(0)
    QTest.keyClick(date_edit, Qt.Key.Key_Return)
    assert _selected(app, date_edit) == "5"
    QTest.keyClick(date_edit, Qt.Key.Key_Tab)
    assert _selected(app, date_edit) == "Nov"
    QTest.keyClick(date_edit, Qt.Key.Key_Return)
    app.processEvents()
    assert app.focusWidget() is after


def test_left_right_stay_inside_field_and_backtab_goes_back(form):
    app, before, date_edit, _after = form
    date_edit.setFocus()
    date_edit.select_section(0)
    QTest.keyClick(date_edit, Qt.Key.Key_Left)
    assert _selected(app, date_edit) == "Thu"
    QTest.keyClick(date_edit, Qt.Key.Key_Right)
    QTest.keyClick(date_edit, Qt.Key.Key_Right)
    QTest.keyClick(date_edit, Qt.Key.Key_Right)
    assert _selected(app, date_edit) == "Nov"
    QTest.keyClick(date_edit, Qt.Key.Key_Backtab)
    assert _selected(app, date_edit) == "5"
    QTest.keyClick(date_edit, Qt.Key.Key_Backtab)
    QTest.keyClick(date_edit, Qt.Key.Key_Backtab)
    app.processEvents()
    assert app.focusWidget() is before


def test_click_selects_whole_part_under_mouse(form):
    app, _before, date_edit, _after = form
    line_edit = date_edit.lineEdit()
    x = (
        line_edit.textMargins().left()
        + line_edit.fontMetrics().horizontalAdvance("Thu ")
        + 3
    )
    QTest.mouseClick(
        line_edit, Qt.MouseButton.LeftButton, pos=QPoint(x, line_edit.height() // 2)
    )
    assert _selected(app, date_edit) == "5"


def test_typing_day_number_replaces_it_and_tab_moves_to_month(form):
    app, _before, date_edit, _after = form
    date_edit.setDate(QDate(2026, 10, 5))
    date_edit.setFocus()
    date_edit.select_section(1)
    QTest.keyClicks(date_edit, "1")
    assert date_edit.date() == QDate(2026, 10, 1)
    assert date_edit.currentSectionIndex() == 1
    QTest.keyClick(date_edit, Qt.Key.Key_Tab)
    assert _selected(app, date_edit) == "Oct"


def test_typing_unambiguous_day_jumps_to_month_by_itself(form):
    app, _before, date_edit, _after = form
    date_edit.setFocus()
    date_edit.select_section(1)
    QTest.keyClicks(date_edit, "4")
    assert date_edit.date() == QDate(2026, 11, 4)
    assert _selected(app, date_edit) == "Nov"
