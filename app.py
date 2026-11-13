import sys

from PySide6.QtWidgets import QApplication

from core.paths import DATABASE_PATH, STRAVA_SETTINGS_PATH
from core.storage import Storage
from ui.main_window import MainWindow
from ui.theme import build_stylesheet


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())
    storage = Storage(DATABASE_PATH)
    window = MainWindow(storage, STRAVA_SETTINGS_PATH)
    window.show()
    window.start_strava_auto_sync()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
