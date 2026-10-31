from datetime import date, timedelta

from PySide6.QtCore import QDate, QTime, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from core.countdown import format_countdown, time_until_race
from core.models import ACTIVITY_TYPES, Activity
from core.stats import km_in_week
from core.storage import Storage


class MainWindow(QMainWindow):
    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self.storage = storage
        self.setWindowTitle("Marathon App")

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)

        self.countdown_label = QLabel(self)
        self.countdown_label.setStyleSheet("font-size: 28px; font-weight: bold;")
        layout.addWidget(self.countdown_label)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(60_000)
        self.countdown_timer.timeout.connect(self._refresh_countdown)
        self.countdown_timer.start()
        self._refresh_countdown()

        form_layout = QFormLayout()
        self.date_edit = QDateEdit(QDate.currentDate(), self)
        self.date_edit.setCalendarPopup(True)
        form_layout.addRow("Date", self.date_edit)

        self.type_combo = QComboBox(self)
        self.type_combo.addItems(ACTIVITY_TYPES)
        form_layout.addRow("Type", self.type_combo)

        self.distance_spin = QDoubleSpinBox(self)
        self.distance_spin.setRange(0, 100)
        self.distance_spin.setSingleStep(0.1)
        form_layout.addRow("Distance (km)", self.distance_spin)

        self.duration_edit = QTimeEdit(self)
        self.duration_edit.setDisplayFormat("H:mm:ss")
        self.duration_edit.setTime(QTime(0, 0))
        form_layout.addRow("Duration", self.duration_edit)

        self.notes_edit = QLineEdit(self)
        form_layout.addRow("Notes", self.notes_edit)

        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self._on_save)
        form_layout.addRow(self.save_button)
        layout.addLayout(form_layout)

        self.week_label = QLabel(self)
        layout.addWidget(self.week_label)

        self.setCentralWidget(central_widget)
        self._refresh_week_summary()

    def _refresh_countdown(self) -> None:
        self.countdown_label.setText(
            f"🏃 {format_countdown(time_until_race())} to go"
        )

    def _refresh_week_summary(self) -> None:
        week_km = km_in_week(self.storage.list_activities(), date.today())
        self.week_label.setText(f"This week: {week_km:.1f} km")

    def _on_save(self) -> None:
        duration_seconds = QTime(0, 0).secsTo(self.duration_edit.time())
        try:
            activity = Activity(
                date=self.date_edit.date().toPython(),
                type=self.type_combo.currentText(),
                distance_km=self.distance_spin.value(),
                duration=timedelta(seconds=duration_seconds),
                notes=self.notes_edit.text(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Can't save", str(error))
            return

        self.storage.add(activity)
        self.date_edit.setDate(QDate.currentDate())
        self.type_combo.setCurrentIndex(0)
        self.distance_spin.setValue(0)
        self.duration_edit.setTime(QTime(0, 0))
        self.notes_edit.clear()
        self._refresh_week_summary()
