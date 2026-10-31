import sys

from PySide6.QtWidgets import QApplication

from core.paths import DATABASE_PATH
from core.storage import Storage
from ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    storage = Storage(DATABASE_PATH)
    window = MainWindow(storage)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
