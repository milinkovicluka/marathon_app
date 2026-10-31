import atexit
import tempfile
from pathlib import Path

BACKGROUND = "#12141C"
SURFACE = "#1A1D29"
SURFACE_RAISED = "#202432"
TEXT = "#E6E8EF"
MUTED_TEXT = "#9AA3B5"
BORDER = "#303647"
GRID = "#353B4C"
ACCENT = "#00E5FF"
ACCENT_HOVER = "#33EEFF"
ACCENT_PRESSED = "#00B8CC"
BLUE = "#2979FF"
BLUE_HOVER = "#5595FF"
BLUE_PRESSED = "#1E5FCC"
TREND = "#FFB74D"
BAR_GLOSS = "#7DF5FF"
PLOT_BACKGROUND = "#171A24"


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


_ARROW_ICON_PATH = _create_arrow_icon()
atexit.register(_ARROW_ICON_PATH.unlink, missing_ok=True)


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
        QComboBox::drop-down, QDateEdit::drop-down, QTimeEdit::drop-down {{
            width: 30px;
            border: none;
            border-left: 1px solid {BORDER};
            subcontrol-origin: padding;
            subcontrol-position: top right;
        }}
        QComboBox::down-arrow, QDateEdit::down-arrow, QTimeEdit::down-arrow {{
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
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
            width: 18px;
            border: none;
            background-color: {SURFACE};
        }}
        QDoubleSpinBox::up-arrow {{
            image: none;
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-bottom: 5px solid {ACCENT};
        }}
        QDoubleSpinBox::down-arrow {{
            image: none;
            width: 0;
            height: 0;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 5px solid {ACCENT};
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
        QPushButton:disabled {{
            color: {MUTED_TEXT};
            border-color: {BORDER};
            background-color: {SURFACE};
        }}
        QPushButton[primary="true"] {{
            border: none;
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
            background-color: {ACCENT};
        }}
        QTableWidget {{
            background-color: {SURFACE};
            alternate-background-color: {SURFACE_RAISED};
            color: {TEXT};
            gridline-color: {BORDER};
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
        QLabel#countdownSuffix {{
            color: {MUTED_TEXT};
            font-size: 15px;
        }}
    """
