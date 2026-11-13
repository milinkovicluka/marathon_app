import sys

from PySide6.QtWidgets import QApplication

from core.paths import DATABASE_PATH, STRAVA_SETTINGS_PATH
from core.storage import Storage
from core.watch_import import DEFAULT_VOLUMES
from ui.main_window import MainWindow
from ui.theme import build_stylesheet


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())
    storage = Storage(DATABASE_PATH)
    window = MainWindow(
        storage,
        # Strava needs a paid subscription for its API; only offered once
        # strava.json exists.
        STRAVA_SETTINGS_PATH if STRAVA_SETTINGS_PATH.exists() else None,
        watch_volumes=DEFAULT_VOLUMES,
    )
    window.show()
    window.start_watch_import()
    window.start_strava_auto_sync()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
