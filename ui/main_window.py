from datetime import date, timedelta

from PySide6.QtCore import QDate, QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from core.countdown import format_countdown, time_until_race
from core.formatting import format_duration, format_pace
from core.models import ACTIVITY_TYPES, Activity
from core.stats import km_in_week
from core.storage import Storage


class MainWindow(QMainWindow):
    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self.storage = storage
        self._editing_id: int | None = None
        self._activities_by_id: dict[int, Activity] = {}
        self.setWindowTitle("Marathon App")

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)

        self.countdown_label = QLabel(self)
        self.countdown_label.setStyleSheet("font-size: 28px; font-weight: bold;")
        layout.addWidget(self.countdown_label)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(60_000)
        self.countdown_timer.timeout.connect(self._refresh_all)
        self.countdown_timer.start()

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
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self._cancel_edit)
        self.cancel_button.hide()
        form_buttons = QHBoxLayout()
        form_buttons.addWidget(self.save_button)
        form_buttons.addWidget(self.cancel_button)
        form_layout.addRow(form_buttons)
        layout.addLayout(form_layout)

        self.week_label = QLabel(self)
        layout.addWidget(self.week_label)

        self.activity_table = QTableWidget(0, 6, self)
        self.activity_table.setHorizontalHeaderLabels(
            ["Date", "Type", "Distance", "Duration", "Pace", "Notes"]
        )
        self.activity_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.activity_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.activity_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.activity_table.cellDoubleClicked.connect(self._edit_row)
        layout.addWidget(self.activity_table)

        self.delete_button = QPushButton("Delete", self)
        self.delete_button.clicked.connect(self._delete_selected)
        layout.addWidget(self.delete_button)

        self.setCentralWidget(central_widget)
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._refresh_countdown()
        self._reload()

    def _refresh_countdown(self) -> None:
        self.countdown_label.setText(
            f"🏃 {format_countdown(time_until_race())} to go"
        )

    def _reload(self) -> None:
        activities = self.storage.list_activities()
        self._activities_by_id = {
            activity.id: activity
            for activity in activities
            if activity.id is not None
        }

        self.activity_table.setRowCount(len(activities))
        for row, activity in enumerate(activities):
            items = [
                QTableWidgetItem(activity.date.isoformat()),
                QTableWidgetItem(activity.type),
                QTableWidgetItem(f"{activity.distance_km:.1f} km"),
                QTableWidgetItem(format_duration(activity.duration)),
                QTableWidgetItem(format_pace(activity.pace)),
                QTableWidgetItem(activity.notes),
            ]
            if activity.id is not None:
                items[0].setData(Qt.ItemDataRole.UserRole, activity.id)
            for column, item in enumerate(items):
                self.activity_table.setItem(row, column, item)

        week_km = km_in_week(activities, date.today())
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
                id=self._editing_id,
            )
        except ValueError as error:
            QMessageBox.warning(self, "Can't save", str(error))
            return

        if self._editing_id is None:
            self.storage.add(activity)
        else:
            self.storage.update(activity)
        self._reset_form()
        self._reload()

    def _edit_row(self, row: int) -> None:
        first_item = self.activity_table.item(row, 0)
        if first_item is None:
            return
        activity_id = first_item.data(Qt.ItemDataRole.UserRole)
        if activity_id not in self._activities_by_id:
            return
        activity = self._activities_by_id[activity_id]

        self._editing_id = activity.id
        self.date_edit.setDate(QDate(activity.date.year, activity.date.month, activity.date.day))
        self.type_combo.setCurrentText(activity.type)
        self.distance_spin.setValue(activity.distance_km)
        self.duration_edit.setTime(
            QTime(0, 0).addSecs(int(activity.duration.total_seconds()))
        )
        self.notes_edit.setText(activity.notes)
        self.save_button.setText("Update")
        self.cancel_button.show()

    def _cancel_edit(self) -> None:
        self._reset_form()

    def _reset_form(self) -> None:
        self._editing_id = None
        self.date_edit.setDate(QDate.currentDate())
        self.type_combo.setCurrentIndex(0)
        self.distance_spin.setValue(0)
        self.duration_edit.setTime(QTime(0, 0))
        self.notes_edit.clear()
        self.save_button.setText("Save")
        self.cancel_button.hide()

    def _delete_selected(self) -> None:
        row = self.activity_table.currentRow()
        if row < 0:
            return
        first_item = self.activity_table.item(row, 0)
        if first_item is None:
            return
        activity_id = first_item.data(Qt.ItemDataRole.UserRole)
        if activity_id is None:
            return

        answer = QMessageBox.question(
            self,
            "Delete activity",
            "Delete this activity?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.storage.delete(activity_id)
        if self._editing_id == activity_id:
            self._reset_form()
        self._reload()
