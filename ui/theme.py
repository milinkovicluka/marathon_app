import atexit
import tempfile
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QCalendarWidget, QToolButton

BACKGROUND = "#12141C"
SURFACE = "#1B1F2B"
SURFACE_RAISED = "#252A38"
TEXT = "#E6E8EF"
MUTED_TEXT = "#8A90A2"
BORDER = "#303647"
GRID = "#2E3445"
ACCENT = "#00E5FF"
ACCENT_HOVER = "#33EEFF"
ACCENT_PRESSED = "#00B8CC"
BLUE = "#2979FF"
BLUE_HOVER = "#5595FF"
BLUE_PRESSED = "#1E5FCC"
TREND = "#FF4ECD"
DANGER = "#FF5370"
BAR_GLOSS = "#7DF5FF"
PLOT_BACKGROUND = SURFACE


def _create_arrow_icon() -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".svg",
        prefix="marathon-arrow-",
        encoding="utf-8",
        delete=False,
    ) as icon_file:
        icon_file.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 8">'
            f'<path fill="{ACCENT}" d="M1 1l5 5 5-5z"/></svg>'
        )
        return Path(icon_file.name)


def _create_check_icon() -> Path:
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".svg",
        prefix="marathon-check-",
        encoding="utf-8",
        delete=False,
    ) as icon_file:
        icon_file.write(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
            f'<path d="M3 8l3.2 3.2L13 4.5" fill="none" stroke="{ACCENT}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
            f"</svg>"
        )
        return Path(icon_file.name)


class ThemedCalendarWidget(QCalendarWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setVerticalHeaderFormat(
            QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
        )

    def date_color(self, day: QDate) -> QColor:
        if day.year() != self.yearShown() or day.month() != self.monthShown():
            return QColor(MUTED_TEXT)
        if day.dayOfWeek() in (6, 7):
            return QColor(ACCENT)
        return QColor(TEXT)

    def paintCell(self, painter: QPainter, rect: QRect, day: QDate) -> None:
        painter.save()
        selected = day == self.selectedDate()
        painter.fillRect(rect, QColor(BLUE if selected else SURFACE))

        if day == QDate.currentDate():
            painter.setPen(QPen(QColor(ACCENT), 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(3, 3, -3, -3))

        text_color = QColor(TEXT) if selected else self.date_color(day)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(day.day()))
        painter.restore()


def navigation_arrow_icon(direction: int) -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(
        QPen(
            QColor("#FFFFFF"),
            2,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
        )
    )
    center = 9
    if direction < 0:
        points = (QPoint(11, 4), QPoint(6, center), QPoint(11, 14))
    else:
        points = (QPoint(7, 4), QPoint(12, center), QPoint(7, 14))
    for start, end in zip(points, points[1:]):
        painter.drawLine(start, end)
    painter.end()
    return QIcon(pixmap)


def style_calendar(calendar: ThemedCalendarWidget) -> None:
    calendar.setStyleSheet(
        f"""
        QCalendarWidget {{
            background-color: {SURFACE};
            color: {TEXT};
        }}
        QCalendarWidget QToolButton {{
            color: #FFFFFF;
            background-color: {SURFACE};
        }}
        QCalendarWidget QMenu {{
            color: {TEXT};
            background-color: {SURFACE_RAISED};
        }}
        """
    )
    for button_name, direction in (
        ("qt_calendar_prevmonth", -1),
        ("qt_calendar_nextmonth", 1),
        ("qt_calendar_prevyear", -1),
        ("qt_calendar_nextyear", 1),
    ):
        button = calendar.findChild(QToolButton, button_name)
        if button is not None:
            button.setText("")
            button.setIcon(navigation_arrow_icon(direction))
            button.setIconSize(QSize(14, 14))


_ARROW_ICON_PATH = _create_arrow_icon()
_CHECK_ICON_PATH = _create_check_icon()
atexit.register(_ARROW_ICON_PATH.unlink, missing_ok=True)
atexit.register(_CHECK_ICON_PATH.unlink, missing_ok=True)


def build_stylesheet() -> str:
    return f"""
        QMainWindow, QWidget {{
            background-color: {BACKGROUND};
            color: {TEXT};
            font-size: 13px;
        }}
        QLabel {{
            background: transparent;
        }}
        QTabWidget::pane {{
            background-color: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 12px;
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: {BACKGROUND};
            color: {MUTED_TEXT};
            border: 1px solid {BORDER};
            border-bottom: none;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            padding: 10px 22px;
            margin-right: 5px;
        }}
        QTabBar::tab:selected {{
            background-color: {SURFACE};
            color: {ACCENT};
            border-bottom: 2px solid {ACCENT};
        }}
        QTabBar::tab:hover:!selected {{
            color: {TEXT};
            background-color: {SURFACE_RAISED};
        }}
        QLineEdit, QDateEdit, QTimeEdit, QDoubleSpinBox, QComboBox {{
            background-color: {SURFACE_RAISED};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 8px;
            min-height: 34px;
            padding: 0 10px;
            selection-background-color: {BLUE};
        }}
        QLineEdit:focus, QDateEdit:focus, QTimeEdit:focus,
        QDoubleSpinBox:focus, QComboBox:focus {{
            border: 1px solid {ACCENT};
        }}
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
        QTimeEdit::up-button, QTimeEdit::down-button {{
            subcontrol-origin: border;
            width: 0;
            height: 0;
            border: none;
        }}
        QComboBox::drop-down, QDateEdit::drop-down {{
            width: 30px;
            border: none;
            border-left: 1px solid {BORDER};
            subcontrol-origin: padding;
            subcontrol-position: top right;
        }}
        QComboBox::down-arrow, QDateEdit::down-arrow {{
            image: url("{_ARROW_ICON_PATH.as_posix()}");
            width: 12px;
            height: 8px;
            border: none;
        }}
        QComboBox QAbstractItemView {{
            background-color: {SURFACE_RAISED};
            color: {TEXT};
            border: 1px solid {BORDER};
            selection-background-color: {BLUE};
            outline: none;
        }}
        QPushButton {{
            min-height: 36px;
            border: 1px solid {BORDER};
            border-radius: 18px;
            padding: 0 20px;
            background-color: {SURFACE_RAISED};
            color: {TEXT};
            font-weight: 600;
        }}
        QPushButton:hover {{
            background-color: {SURFACE};
            border-color: {ACCENT};
            color: {ACCENT};
        }}
        QPushButton:pressed {{
            background-color: {BORDER};
        }}
        QPushButton:checked {{
            background-color: {SURFACE};
            border-color: {ACCENT};
            color: {ACCENT};
        }}
        QPushButton:disabled {{
            color: {MUTED_TEXT};
            border-color: {BORDER};
            background-color: {SURFACE};
        }}
        QPushButton[primary="true"] {{
            min-height: 40px;
            border: none;
            border-radius: 20px;
            color: {BACKGROUND};
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {ACCENT}, stop:1 {BLUE});
        }}
        QPushButton[primary="true"]:hover {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {ACCENT_HOVER}, stop:1 {BLUE_HOVER});
        }}
        QPushButton[primary="true"]:pressed {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {ACCENT_PRESSED},
                                        stop:1 {BLUE_PRESSED});
        }}
        QPushButton[danger="true"] {{
            color: {DANGER};
            border-color: {DANGER};
        }}
        QPushButton[danger="true"]:hover {{
            color: {BACKGROUND};
            background-color: {DANGER};
            border-color: {DANGER};
        }}
        QPushButton[danger="true"]:disabled {{
            color: {MUTED_TEXT};
            border-color: {BORDER};
            background-color: {SURFACE};
        }}
        QCheckBox {{
            spacing: 8px;
            color: {TEXT};
            background: transparent;
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {BORDER};
            border-radius: 5px;
            background-color: {SURFACE_RAISED};
        }}
        QCheckBox::indicator:checked {{
            border-color: {ACCENT};
            background-color: {SURFACE_RAISED};
            image: url("{_CHECK_ICON_PATH.as_posix()}");
        }}
        QTableWidget {{
            background-color: {SURFACE};
            alternate-background-color: {SURFACE_RAISED};
            color: {TEXT};
            gridline-color: {GRID};
            border: 1px solid {BORDER};
            border-radius: 8px;
            selection-background-color: {BLUE};
        }}
        QHeaderView::section {{
            background-color: {SURFACE_RAISED};
            color: {ACCENT};
            border: none;
            border-bottom: 1px solid {BORDER};
            padding: 8px;
            font-weight: 600;
        }}
        QScrollBar:vertical {{
            background-color: {BACKGROUND};
            width: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {BORDER};
            border-radius: 5px;
            min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {MUTED_TEXT};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QToolTip {{
            background-color: {SURFACE_RAISED};
            color: {TEXT};
            border: 1px solid {BORDER};
            padding: 5px;
        }}
        QWidget#segmentEditor {{
            background: transparent;
        }}
        QListWidget#segmentList {{
            background: transparent;
            border: none;
            outline: none;
        }}
        QListWidget#segmentList::item {{
            background-color: {SURFACE_RAISED};
            color: {TEXT};
            border: 1px solid {BORDER};
            border-radius: 12px;
            padding: 3px 12px;
        }}
        QListWidget#segmentList::item:selected {{
            border-color: {ACCENT};
            color: {ACCENT};
        }}
        QFrame#DashboardCard {{
            background-color: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 16px;
        }}
        QLabel#countdownTitle, QLabel#cardCaption {{
            color: {MUTED_TEXT};
            font-size: 11px;
            font-weight: 600;
        }}
        QLabel#countdownValue, QLabel#weekValue {{
            color: {ACCENT};
            font-size: 28px;
            font-weight: 700;
        }}
        QLabel#weekDetails {{
            color: {MUTED_TEXT};
            font-size: 12px;
        }}
        QLabel#countdownSuffix {{
            color: {MUTED_TEXT};
            font-size: 15px;
        }}
    """
