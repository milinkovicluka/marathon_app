from datetime import date, timedelta
from typing import Literal

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from PySide6.QtCore import QDate, QLocale, QSize, QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QAbstractSpinBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from core.countdown import RACE_START_TIME, format_countdown, time_until_race
from core.formatting import format_duration, format_pace
from core.models import ACTIVITY_TYPES, Activity, ActivityType
from core.stats import (
    ProgressMetric,
    ProgressPeriod,
    average_pace,
    km_in_week,
    longest_run,
    progress_series,
)
from core.storage import Storage
from ui import theme


def _format_day(day: date, *, with_weekday: bool = False) -> str:
    prefix = f"{day:%a} " if with_weekday else ""
    return f"{prefix}{day.day} {day:%b}"


def _format_date_range(start: date, end: date) -> str:
    if start == end:
        return _format_day(start)
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {end:%b %Y}"
    if start.year == end.year:
        return f"{_format_day(start)}–{_format_day(end)} {end:%Y}"
    return f"{_format_day(start)} {start:%Y}–{_format_day(end)} {end:%Y}"


def _shift_month(day: date, months: int) -> date:
    month_index = day.year * 12 + day.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


def _progress_period_bounds(
    period: ProgressPeriod,
    offset: int,
    today: date,
) -> tuple[date, date]:
    if period == "7 Days":
        end = today + timedelta(days=7 * offset)
        return end - timedelta(days=6), end
    if period == "4 Weeks":
        end = today + timedelta(days=28 * offset)
        return end - timedelta(days=27), end
    if period in ("6 Months", "1 Year"):
        month_count = 6 if period == "6 Months" else 12
        current_start = _shift_month(today, -(month_count - 1))
        start = _shift_month(current_start, month_count * offset)
        next_start = _shift_month(start, month_count)
        return start, next_start - timedelta(days=1)
    raise ValueError(f"Unknown progress period: {period}")


class MainWindow(QMainWindow):
    def __init__(self, storage: Storage) -> None:
        super().__init__()
        self.storage = storage
        self._editing_id: int | None = None
        self._activities_by_id: dict[int, Activity] = {}
        self._last_reload_date = date.today()
        self.setWindowTitle("Marathon App")
        self.resize(1120, 840)

        central_widget = QWidget(self)
        layout = QVBoxLayout(central_widget)

        countdown_card = QFrame(self)
        countdown_card.setObjectName("DashboardCard")
        countdown_layout = QHBoxLayout(countdown_card)
        countdown_layout.setContentsMargins(20, 14, 20, 14)
        countdown_text_layout = QVBoxLayout()
        race_day = RACE_START_TIME.date()
        self.countdown_title = QLabel(
            f"PRAGUE MARATHON · {race_day.day} {race_day:%b %Y}".upper()
        )
        self.countdown_title.setObjectName("countdownTitle")
        countdown_text_layout.addWidget(self.countdown_title)
        countdown_value_layout = QHBoxLayout()
        self.countdown_label = QLabel(self)
        self.countdown_label.setObjectName("countdownValue")
        self.countdown_suffix_label = QLabel("to go")
        self.countdown_suffix_label.setObjectName("countdownSuffix")
        countdown_value_layout.addWidget(self.countdown_label)
        countdown_value_layout.addWidget(self.countdown_suffix_label)
        countdown_value_layout.addStretch(1)
        countdown_text_layout.addLayout(countdown_value_layout)
        countdown_layout.addLayout(countdown_text_layout)
        countdown_layout.addStretch(1)
        layout.addWidget(countdown_card)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(60_000)
        self.countdown_timer.timeout.connect(self._on_timer)
        self.countdown_timer.start()

        self.tabs = QTabWidget(self)
        log_tab = QWidget(self.tabs)
        log_layout = QVBoxLayout(log_tab)
        self.tabs.addTab(log_tab, "Log")

        progress_tab = QWidget(self.tabs)
        progress_layout = QVBoxLayout(progress_tab)
        self.tabs.addTab(progress_tab, "Progress")
        chart_controls = QHBoxLayout()
        self.chart_activity_filter = QComboBox(progress_tab)
        self.chart_activity_filter.addItem("All activities", "all")
        for activity_type in ACTIVITY_TYPES:
            self.chart_activity_filter.addItem(
                activity_type.title(),
                activity_type,
            )
        self.chart_activity_filter.setCurrentIndex(
            self.chart_activity_filter.findData("run")
        )
        self.chart_activity_filter.currentIndexChanged.connect(
            self._refresh_progress_chart
        )
        chart_controls.addWidget(self.chart_activity_filter)

        self.chart_metric = QComboBox(progress_tab)
        self.chart_metric.addItems(["Activities", "Kilometers", "Time"])
        self.chart_metric.currentIndexChanged.connect(
            self._refresh_progress_chart
        )
        chart_controls.addWidget(self.chart_metric)
        chart_controls.addStretch(1)

        self._progress_period_offset = 0
        self._progress_period: ProgressPeriod = "7 Days"
        self.period_back_button = QPushButton(progress_tab)
        self.period_back_button.setIcon(theme.navigation_arrow_icon(-1))
        self.period_back_button.setIconSize(QSize(18, 18))
        self.period_back_button.setFixedSize(38, 36)
        self.period_back_button.setAccessibleName("Previous period")
        self.period_back_button.clicked.connect(self._on_period_back)
        chart_controls.addWidget(self.period_back_button)

        self.period_range_label = QLabel(progress_tab)
        self.period_range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.period_range_label.setMinimumWidth(150)
        chart_controls.addWidget(self.period_range_label)

        self.period_forward_button = QPushButton(progress_tab)
        self.period_forward_button.setIcon(theme.navigation_arrow_icon(1))
        self.period_forward_button.setIconSize(QSize(18, 18))
        self.period_forward_button.setFixedSize(38, 36)
        self.period_forward_button.setAccessibleName("Next period")
        self.period_forward_button.clicked.connect(self._on_period_forward)
        chart_controls.addWidget(self.period_forward_button)

        chart_controls.addSpacing(12)
        self.period_button_group = QButtonGroup(progress_tab)
        self.period_button_group.setExclusive(True)
        self.period_buttons: dict[str, QPushButton] = {}
        period_options: tuple[ProgressPeriod, ...] = (
            "7 Days",
            "4 Weeks",
            "6 Months",
            "1 Year",
        )
        for period in period_options:
            button = QPushButton(period, progress_tab)
            button.setCheckable(True)
            button.setChecked(period == self._progress_period)
            button.clicked.connect(
                lambda _checked=False, selected=period: self._set_progress_period(
                    selected
                )
            )
            self.period_button_group.addButton(button)
            self.period_buttons[period] = button
            chart_controls.addWidget(button)

        progress_layout.addLayout(chart_controls)

        cards_layout = QHBoxLayout()
        form_card = QFrame(log_tab)
        form_card.setObjectName("DashboardCard")
        form_card_layout = QVBoxLayout(form_card)
        form_card_layout.setContentsMargins(18, 16, 18, 18)
        form_title = QLabel("LOG ACTIVITY", form_card)
        form_title.setObjectName("cardCaption")
        form_card_layout.addWidget(form_title)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.date_edit = QDateEdit(QDate.currentDate(), self)
        self.date_edit.setDisplayFormat("ddd d MMM")
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setCalendarWidget(theme.ThemedCalendarWidget())
        theme.style_calendar(self.date_edit.calendarWidget())
        form_layout.addRow("Date", self.date_edit)

        self.type_combo = QComboBox(self)
        self.type_combo.addItems(ACTIVITY_TYPES)
        form_layout.addRow("Type", self.type_combo)

        self.distance_spin = QDoubleSpinBox(self)
        self.distance_spin.setRange(0, 100)
        self.distance_spin.setSingleStep(0.1)
        self.distance_spin.setLocale(QLocale.c())
        self.distance_spin.setMinimumSize(120, 40)
        self.distance_spin.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        form_layout.addRow("Distance (km)", self.distance_spin)

        self.duration_edit = QTimeEdit(self)
        self.duration_edit.setDisplayFormat("H:mm:ss")
        self.duration_edit.setTime(QTime(0, 0))
        self.duration_edit.setMinimumSize(140, 40)
        self.duration_edit.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        form_layout.addRow("Duration", self.duration_edit)

        self.notes_edit = QLineEdit(self)
        form_layout.addRow("Notes", self.notes_edit)

        self.save_button = QPushButton("Save", self)
        self.save_button.setProperty("primary", True)
        self.save_button.setFixedSize(180, 40)
        self.save_button.clicked.connect(self._on_save)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.clicked.connect(self._cancel_edit)
        self.cancel_button.hide()
        form_buttons = QHBoxLayout()
        form_buttons.addWidget(self.save_button)
        form_buttons.addWidget(self.cancel_button)
        form_buttons.addStretch(1)
        form_layout.addRow("", form_buttons)
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        form_card_layout.addLayout(form_layout)
        cards_layout.addWidget(form_card, 3)

        summary_card = QFrame(log_tab)
        summary_card.setObjectName("DashboardCard")
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(22, 18, 22, 18)
        summary_title = QLabel("THIS WEEK", summary_card)
        summary_title.setObjectName("cardCaption")
        summary_layout.addWidget(summary_title)
        self.week_label = QLabel(summary_card)
        self.week_label.setObjectName("weekValue")
        summary_layout.addWidget(self.week_label)
        self.week_details_label = QLabel(summary_card)
        self.week_details_label.setObjectName("weekDetails")
        self.week_details_label.setWordWrap(True)
        summary_layout.addWidget(self.week_details_label)
        summary_layout.addStretch(1)
        cards_layout.addWidget(summary_card, 2)
        log_layout.addLayout(cards_layout)

        self.activity_table = QTableWidget(0, 6, self)
        self.activity_table.setHorizontalHeaderLabels(
            ["Date", "Type", "Distance", "Duration", "Pace", "Notes"]
        )
        self.activity_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.activity_table.verticalHeader().setVisible(False)
        self.activity_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.activity_table.setAlternatingRowColors(True)
        self.activity_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        table_header = self.activity_table.horizontalHeader()
        table_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for column in (2, 3, 4):
            header_item = self.activity_table.horizontalHeaderItem(column)
            if header_item is not None:
                header_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter
                )
        self.activity_table.cellDoubleClicked.connect(self._edit_row)
        log_layout.addWidget(self.activity_table)

        self.delete_button = QPushButton("Delete", self)
        self.delete_button.setProperty("danger", True)
        self.delete_button.setMinimumWidth(120)
        self.delete_button.clicked.connect(self._delete_selected)
        self.activity_table.itemSelectionChanged.connect(
            self._update_delete_button
        )
        self.delete_button.setEnabled(False)
        delete_row = QHBoxLayout()
        delete_row.addStretch(1)
        delete_row.addWidget(self.delete_button)
        log_layout.addLayout(delete_row)

        self.chart_figure = Figure(facecolor=theme.PLOT_BACKGROUND)
        self.chart_axes = self.chart_figure.add_subplot(
            111,
            facecolor=theme.PLOT_BACKGROUND,
        )
        self.chart_canvas = FigureCanvasQTAgg(self.chart_figure)
        progress_layout.addWidget(self.chart_canvas)

        layout.addWidget(self.tabs)
        self.setCentralWidget(central_widget)
        self._refresh_countdown()
        self._reload()

    def _on_timer(self) -> None:
        self._refresh_countdown()
        today = date.today()
        if today != self._last_reload_date:
            today_qdate = QDate(today.year, today.month, today.day)
            self.date_edit.setMaximumDate(today_qdate)
            self._reload()
            return
        self._refresh_week_label(list(self._activities_by_id.values()))

    def _refresh_countdown(self) -> None:
        remaining = time_until_race()
        self.countdown_label.setText(f"🏃 {format_countdown(remaining)}")
        self.countdown_suffix_label.setText(
            "to go" if remaining > timedelta(0) else ""
        )

    def _reload(self) -> None:
        self._last_reload_date = date.today()
        activities = self.storage.list_activities()
        self._activities_by_id = {
            activity.id: activity
            for activity in activities
            if activity.id is not None
        }

        self.activity_table.setCurrentCell(-1, -1)
        self.activity_table.clearSelection()
        self.activity_table.setRowCount(len(activities))
        for row, activity in enumerate(activities):
            items = [
                QTableWidgetItem(
                    _format_day(activity.date, with_weekday=True)
                ),
                QTableWidgetItem(activity.type),
                QTableWidgetItem(f"{activity.distance_km:.1f} km"),
                QTableWidgetItem(format_duration(activity.duration)),
                QTableWidgetItem(format_pace(activity.pace)),
                QTableWidgetItem(activity.notes),
            ]
            if activity.id is not None:
                items[0].setData(Qt.ItemDataRole.UserRole, activity.id)
            for column, item in enumerate(items):
                if column in (2, 3, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                self.activity_table.setItem(row, column, item)

        self._refresh_week_label(activities)
        self._refresh_chart(activities)

    def _refresh_week_label(self, activities: list[Activity]) -> None:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        runs_this_week = [
            activity
            for activity in activities
            if activity.type == "run"
            and monday <= activity.date <= monday + timedelta(days=6)
        ]
        week_km = km_in_week(activities, today)
        self.week_label.setText(f"{week_km:.1f} km")
        longest = longest_run(runs_this_week)
        longest_text = (
            f"{longest.distance_km:.1f} km" if longest is not None else "n/a"
        )
        average_pace_text = format_pace(average_pace(runs_this_week))
        run_count = len(runs_this_week)
        run_word = "run" if run_count == 1 else "runs"
        self.week_details_label.setText(
            f"{run_count} {run_word} · longest {longest_text} · "
            f"avg {average_pace_text}"
        )

    def _set_progress_period(self, period: ProgressPeriod) -> None:
        self._progress_period = period
        self._progress_period_offset = 0
        self._refresh_progress_chart()

    def _on_period_back(self) -> None:
        self._progress_period_offset -= 1
        self._refresh_progress_chart()

    def _on_period_forward(self) -> None:
        if self._progress_period_offset < 0:
            self._progress_period_offset += 1
            self._refresh_progress_chart()

    def _refresh_progress_chart(self, *_values: object) -> None:
        del _values
        self._refresh_chart(list(self._activities_by_id.values()))

    def _refresh_chart(self, activities: list[Activity]) -> None:
        self.chart_axes.clear()
        self.chart_axes.set_facecolor(theme.PLOT_BACKGROUND)

        today = date.today()
        start, period_end = _progress_period_bounds(
            self._progress_period,
            self._progress_period_offset,
            today,
        )
        end = (
            min(period_end, today)
            if self._progress_period_offset == 0
            else period_end
        )
        current_period_is_incomplete = self._progress_period_offset == 0
        self.period_range_label.setText(_format_date_range(start, end))
        self.period_back_button.setEnabled(True)
        self.period_forward_button.setEnabled(self._progress_period_offset < 0)

        activity_type_by_label: dict[
            str,
            ActivityType | Literal["all"],
        ] = {
            "All activities": "all",
            **{
                activity_type.title(): activity_type
                for activity_type in ACTIVITY_TYPES
            },
        }
        selected_type = activity_type_by_label[
            self.chart_activity_filter.currentText()
        ]
        metric_by_label: dict[str, ProgressMetric] = {
            "Activities": "Activities",
            "Kilometers": "Kilometers",
            "Time": "Time",
        }
        metric = metric_by_label[self.chart_metric.currentText()]
        series = progress_series(
            activities,
            start,
            end,
            self._progress_period,
            metric,
            selected_type,
        )
        bucket_starts = [bucket_start for bucket_start, _ in series]
        values = [value for _, value in series]
        if self._progress_period == "7 Days":
            labels = [bucket.strftime("%a") for bucket in bucket_starts]
        elif self._progress_period == "4 Weeks":
            labels = [_format_day(bucket) for bucket in bucket_starts]
        else:
            labels = [bucket.strftime("%b") for bucket in bucket_starts]

        x_positions = list(range(len(bucket_starts)))
        self.chart_axes.plot(
            x_positions[:-1] if current_period_is_incomplete else x_positions,
            values[:-1] if current_period_is_incomplete else values,
            color=theme.BLUE,
            linewidth=2.5,
            marker="o",
            markersize=7,
            markerfacecolor=theme.BLUE,
            markeredgecolor=theme.PLOT_BACKGROUND,
            markeredgewidth=1.5,
        )
        if current_period_is_incomplete and x_positions:
            if len(x_positions) > 1:
                self.chart_axes.plot(
                    x_positions[-2:],
                    values[-2:],
                    color=theme.BLUE,
                    linewidth=2.5,
                    linestyle="--",
                )
            self.chart_axes.plot(
                [x_positions[-1]],
                [values[-1]],
                color=theme.BLUE,
                marker="o",
                markersize=7,
                markerfacecolor="none",
                markeredgecolor=theme.BLUE,
                markeredgewidth=1.5,
                linestyle="None",
            )
        self.chart_axes.set_xticks(x_positions, labels)
        self.chart_axes.set_xlim(-0.5, len(x_positions) - 0.5)
        self.chart_axes.set_ylim(0, max(1, max(values, default=0) * 1.15))
        if metric == "Activities":
            self.chart_axes.yaxis.set_major_locator(MaxNLocator(integer=True))

        y_label = {
            "Activities": "Activities",
            "Kilometers": "Kilometers",
            "Time": "Hours",
        }[metric]
        self._style_axes(
            f"{self.chart_activity_filter.currentText()} · {metric}",
            y_label,
        )
        self.chart_figure.tight_layout()
        self.chart_canvas.draw()

    def _style_axes(
        self,
        title: str,
        ylabel: str,
    ) -> None:
        self.chart_axes.set_title(title, color=theme.TEXT)
        self.chart_axes.set_ylabel(ylabel, color=theme.TEXT)
        self.chart_axes.tick_params(axis="x", colors=theme.MUTED_TEXT)
        self.chart_axes.tick_params(axis="y", colors=theme.MUTED_TEXT)
        self.chart_axes.grid(axis="y", color=theme.GRID, alpha=0.5)
        self.chart_axes.set_axisbelow(True)
        for spine in self.chart_axes.spines.values():
            spine.set_color(theme.BORDER)
        self.chart_axes.spines[["top", "right"]].set_visible(False)

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
            try:
                self.storage.update(activity)
            except LookupError as error:
                QMessageBox.warning(self, "Can't update", str(error))
                self._reset_form()
                self._reload()
                return
        self._reset_form()
        self._reload()

    def _edit_row(self, row: int, _column: int = 0) -> None:
        del _column
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

        try:
            self.storage.delete(activity_id)
        except LookupError as error:
            QMessageBox.warning(self, "Can't delete", str(error))
            if self._editing_id == activity_id:
                self._reset_form()
            self._reload()
            return
        if self._editing_id == activity_id:
            self._reset_form()
        self._reload()

    def _update_delete_button(self) -> None:
        self.delete_button.setEnabled(self.activity_table.currentRow() >= 0)
