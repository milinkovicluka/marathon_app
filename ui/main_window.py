import threading
from concurrent.futures import Future
from datetime import date, datetime, timedelta
from pathlib import Path
from collections.abc import Callable
from typing import Literal

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from PySide6.QtCore import QDate, QLocale, QSize, QTime, QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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

from core import strava
from core.fit_import import ImportResult, import_files
from core.watch_import import find_watch_activity_dirs, import_from_watch
from core.countdown import RACE_START_TIME, format_countdown, time_until_race
from core.formatting import format_duration, format_pace, format_segments
from core.models import (
    ACTIVITY_TYPES,
    SEGMENT_TYPES,
    Activity,
    ActivityType,
    Segment,
)
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
from ui.date_edit import SegmentedDateEdit


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
    def __init__(
        self,
        storage: Storage,
        strava_settings_path: Path | None = None,
        watch_volumes: Path | None = None,
    ) -> None:
        super().__init__()
        self.storage = storage
        self._editing_id: int | None = None
        self._editing_source_id: str | None = None
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
        self.date_edit = SegmentedDateEdit(QDate.currentDate(), self)
        self.date_edit.setDisplayFormat("ddd d MMM")
        self.date_edit.setMaximumDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setCalendarWidget(theme.ThemedCalendarWidget())
        theme.style_calendar(self.date_edit.calendarWidget())
        form_layout.addRow("Date", self.date_edit)

        self.type_combo = QComboBox(self)
        self.type_combo.addItems(ACTIVITY_TYPES)
        # macOS gives combo boxes Tab focus only with full keyboard access on.
        self.type_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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

        self._segments: list[Segment] = []
        self.segment_distance_spin = QDoubleSpinBox(self)
        self.segment_distance_spin.setRange(0, 100)
        self.segment_distance_spin.setSingleStep(0.1)
        self.segment_distance_spin.setLocale(QLocale.c())
        self.segment_distance_spin.setSuffix(" km")
        self.segment_distance_spin.setMinimumSize(100, 40)
        self.segment_distance_spin.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.segment_pace_edit = QTimeEdit(self)
        self.segment_pace_edit.setDisplayFormat("m:ss")
        self.segment_pace_edit.setTime(QTime(0, 0))
        self.segment_pace_edit.setMinimumSize(80, 40)
        self.segment_pace_edit.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        self.add_segment_button = QPushButton("Add", self)
        self.add_segment_button.setMinimumWidth(80)
        self.add_segment_button.clicked.connect(self._add_segment)
        self.remove_segment_button = QPushButton("Remove", self)
        self.remove_segment_button.setMinimumWidth(90)
        self.remove_segment_button.setEnabled(False)
        self.remove_segment_button.clicked.connect(self._remove_segment)
        segment_inputs = QHBoxLayout()
        segment_inputs.addWidget(self.segment_distance_spin)
        segment_inputs.addWidget(QLabel("@", self))
        segment_inputs.addWidget(self.segment_pace_edit)
        segment_inputs.addWidget(QLabel("/km", self))
        segment_inputs.addWidget(self.add_segment_button)
        segment_inputs.addWidget(self.remove_segment_button)
        segment_inputs.addStretch(1)
        self.segment_list = QListWidget(self)
        self.segment_list.setObjectName("segmentList")
        self.segment_list.setFlow(QListWidget.Flow.LeftToRight)
        self.segment_list.setWrapping(True)
        self.segment_list.setSpacing(4)
        self.segment_list.setFixedHeight(44)
        self.segment_list.itemSelectionChanged.connect(
            self._update_segment_buttons
        )
        self.segment_editor = QWidget(self)
        self.segment_editor.setObjectName("segmentEditor")
        segment_editor_layout = QVBoxLayout(self.segment_editor)
        segment_editor_layout.setContentsMargins(0, 0, 0, 0)
        segment_editor_layout.addLayout(segment_inputs)
        segment_editor_layout.addWidget(self.segment_list)
        form_layout.addRow("Segments", self.segment_editor)
        self._form_layout = form_layout
        self.type_combo.currentTextChanged.connect(
            self._update_segment_editor
        )
        self._update_segment_buttons()

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
        form_card_layout.addStretch(1)
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

        self.activity_table = QTableWidget(0, 7, self)
        self.activity_table.setHorizontalHeaderLabels(
            ["Date", "Type", "Distance", "Duration", "Pace", "Segments", "Notes"]
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
        table_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
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
        self.import_button = QPushButton("Import FIT…", self)
        self.import_button.setMinimumWidth(140)
        self.import_button.clicked.connect(self._import_fit)
        # Strava is only offered when the app is given a settings file.
        self._strava_path = strava_settings_path
        self._strava_settings = (
            strava.StravaSettings.load(strava_settings_path)
            if strava_settings_path is not None
            else strava.StravaSettings()
        )
        self._strava_job: Future | None = None
        self._strava_job_is_manual = False
        self._strava_poll = QTimer(self)
        self._strava_poll.setInterval(200)
        self._strava_poll.timeout.connect(self._check_strava_job)
        self.strava_button = QPushButton(self)
        self.strava_button.setMinimumWidth(150)
        self.strava_button.clicked.connect(self._on_strava_button)
        self.strava_status = QLabel(self)
        self.strava_status.setObjectName("weekDetails")
        self.strava_button.setVisible(strava_settings_path is not None)
        self.strava_status.setVisible(strava_settings_path is not None)
        self._update_strava_button()
        # Watching for a plugged-in Garmin watch is only on when the app is
        # given the folder where disks appear (/Volumes on a Mac).
        self._watch_volumes = watch_volumes
        self._watch_dirs_seen: set[Path] = set()
        self._watch_job: Future | None = None
        self._watch_progress = (0, 0)
        self.watch_status = QLabel(self)
        self.watch_status.setObjectName("weekDetails")
        self.watch_status.setVisible(watch_volumes is not None)
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(500)
        self._watch_timer.timeout.connect(self._check_watch)
        delete_row = QHBoxLayout()
        delete_row.addWidget(self.import_button)
        delete_row.addWidget(self.watch_status)
        delete_row.addWidget(self.strava_button)
        delete_row.addWidget(self.strava_status)
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
                QTableWidgetItem(format_segments(activity.segments)),
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
                source_id=self._editing_source_id,
                segments=(
                    tuple(self._segments)
                    if self.type_combo.currentText() in SEGMENT_TYPES
                    else ()
                ),
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
        self._editing_source_id = activity.source_id
        self.date_edit.setDate(QDate(activity.date.year, activity.date.month, activity.date.day))
        self.type_combo.setCurrentText(activity.type)
        self.distance_spin.setValue(activity.distance_km)
        self.duration_edit.setTime(
            QTime(0, 0).addSecs(int(activity.duration.total_seconds()))
        )
        self.notes_edit.setText(activity.notes)
        self._set_segments(list(activity.segments))
        self.save_button.setText("Update")
        self.cancel_button.show()

    def _set_segments(self, segments: list[Segment]) -> None:
        self._segments = segments
        self.segment_list.clear()
        for segment in segments:
            self.segment_list.addItem(QListWidgetItem(format_segments([segment])))
        self.segment_distance_spin.setValue(0)
        self.segment_pace_edit.setTime(QTime(0, 0))
        self._update_segment_buttons()

    def _add_segment(self) -> None:
        pace_seconds = QTime(0, 0).secsTo(self.segment_pace_edit.time())
        try:
            segment = Segment.from_pace(
                self.segment_distance_spin.value(),
                timedelta(seconds=pace_seconds),
            )
        except ValueError as error:
            QMessageBox.warning(self, "Can't add segment", str(error))
            return
        self._set_segments([*self._segments, segment])
        self.segment_distance_spin.setFocus()

    def _remove_segment(self) -> None:
        row = self.segment_list.currentRow()
        if 0 <= row < len(self._segments):
            self._set_segments(
                [s for index, s in enumerate(self._segments) if index != row]
            )

    def _update_segment_buttons(self) -> None:
        self.remove_segment_button.setEnabled(
            bool(self.segment_list.selectedItems())
        )
        self.segment_list.setVisible(bool(self._segments))

    def _update_segment_editor(self, activity_type: str) -> None:
        self._form_layout.setRowVisible(
            self.segment_editor, activity_type in SEGMENT_TYPES
        )

    def _import_fit(self) -> None:
        paths, _filter = QFileDialog.getOpenFileNames(
            self,
            "Import Garmin activities",
            str(Path.home() / "Downloads"),
            "Garmin activities (*.fit *.zip)",
        )
        if not paths:
            return
        result = import_files(self.storage, paths)
        self._reload()
        QMessageBox.information(self, "Import FIT", self._import_summary(result))

    def _import_summary(self, result: ImportResult) -> str:
        lines = [f"Imported {len(result.imported)}."]
        if result.already_imported:
            lines.append(
                f"Skipped {len(result.already_imported)} already imported."
            )
        for imported, logged in result.possible_duplicates:
            lines.append(
                f"{_format_day(imported.date, with_weekday=True)} "
                f"{imported.type} {imported.distance_km:.1f} km may be the same "
                f"workout as one you logged by hand ({logged.distance_km:.1f} km); "
                "delete the one you don't want."
            )
        for path, error in result.failed:
            lines.append(f"Couldn't read {path.name}: {error}")
        return "\n".join(lines)

    def start_watch_import(self) -> None:
        """Import from a Garmin watch now and whenever one is plugged in."""
        if self._watch_volumes is not None:
            self.watch_status.setText("Plug in your watch to import")
            self._check_watch()
            self._watch_timer.start()

    def _check_watch(self) -> None:
        assert self._watch_volumes is not None
        job = self._watch_job
        if job is not None:
            if not job.done():
                done, total = self._watch_progress
                self.watch_status.setText(f"Watch: reading {done}/{total}…")
                return
            self._watch_job = None
            self._finish_watch_import(job)

        # Checking for the disk every few seconds is enough.
        self._watch_timer.setInterval(3000)
        mounted = set(find_watch_activity_dirs(self._watch_volumes))
        new_dirs = sorted(mounted - self._watch_dirs_seen)
        self._watch_dirs_seen &= mounted  # forget unplugged watches
        if not new_dirs:
            return
        self._watch_dirs_seen.add(new_dirs[0])
        self._watch_progress = (0, 0)
        self.watch_status.setText("Watch: looking for new workouts…")

        def progress(done: int, total: int) -> None:
            self._watch_progress = (done, total)

        future: Future = Future()
        activity_dir = new_dirs[0]

        def work() -> None:
            try:
                future.set_result(import_from_watch(self.storage, activity_dir, progress))
            except BaseException as error:  # reported on the UI thread
                future.set_exception(error)

        threading.Thread(target=work, daemon=True).start()
        self._watch_job = future
        self._watch_timer.setInterval(500)

    def _finish_watch_import(self, job: Future) -> None:
        error = job.exception()
        if error is not None:
            self.watch_status.setText("Watch: import failed")
            QMessageBox.warning(self, "Watch import", str(error))
            return
        result = job.result()
        self._reload()
        self.watch_status.setText(
            f"Watch: {len(result.imported)} new · {datetime.now():%H:%M}"
        )
        if result.possible_duplicates or result.failed:
            QMessageBox.information(self, "Watch import", self._import_summary(result))

    def start_strava_auto_sync(self) -> None:
        if self._strava_settings.connected:
            self._run_strava_job(self._strava_sync_job, manual=False)

    def _update_strava_button(self) -> None:
        busy = self._strava_job is not None
        self.strava_button.setEnabled(not busy)
        self.strava_button.setText(
            "Sync Strava" if self._strava_settings.connected else "Connect Strava"
        )

    def _on_strava_button(self) -> None:
        if self._strava_settings.connected:
            self._run_strava_job(self._strava_sync_job, manual=True)
            return
        settings = self._strava_settings
        if not settings.has_app:
            client_id, ok = QInputDialog.getText(
                self,
                "Connect Strava",
                "Client ID of your Strava API app\n"
                "(strava.com/settings/api, callback domain: localhost):",
            )
            if not ok or not client_id.strip():
                return
            secret, ok = QInputDialog.getText(
                self,
                "Connect Strava",
                "Client Secret:",
                QLineEdit.EchoMode.Password,
            )
            if not ok or not secret.strip():
                return
            settings.client_id = client_id.strip()
            settings.client_secret = secret.strip()
            self._save_strava_settings()
        QDesktopServices.openUrl(QUrl(strava.authorize_url(settings.client_id)))
        self._run_strava_job(
            self._strava_connect_job,
            manual=True,
            status="Approve access in the browser…",
        )

    def _strava_connect_job(self) -> ImportResult:
        code = strava.wait_for_code()
        strava.exchange_code(self._strava_settings, code)
        return self._strava_sync_job()

    def _strava_sync_job(self) -> ImportResult:
        try:
            return strava.sync(self.storage, self._strava_settings)
        finally:
            self._save_strava_settings()

    def _save_strava_settings(self) -> None:
        if self._strava_path is not None:
            self._strava_settings.save(self._strava_path)

    def _run_strava_job(
        self,
        job: Callable[[], ImportResult],
        *,
        manual: bool,
        status: str = "Syncing Strava…",
    ) -> None:
        if self._strava_job is not None:
            return
        self._strava_job_is_manual = manual
        self.strava_status.setText(status)
        future: Future = Future()

        def work() -> None:
            try:
                future.set_result(job())
            except BaseException as error:  # reported on the UI thread
                future.set_exception(error)

        # A daemon thread, so quitting never waits for Strava or the browser.
        threading.Thread(target=work, daemon=True).start()
        self._strava_job = future
        self._update_strava_button()
        self._strava_poll.start()

    def _check_strava_job(self) -> None:
        job = self._strava_job
        if job is None or not job.done():
            return
        self._strava_poll.stop()
        self._strava_job = None
        self._update_strava_button()
        error = job.exception()
        if error is not None:
            self.strava_status.setText("Strava: sync failed")
            if self._strava_job_is_manual or not isinstance(error, strava.StravaError):
                QMessageBox.warning(self, "Strava", str(error))
            return
        result = job.result()
        self._reload()
        self.strava_status.setText(
            f"Strava: {len(result.imported)} new · {datetime.now():%H:%M}"
        )
        if self._strava_job_is_manual or result.possible_duplicates or result.failed:
            QMessageBox.information(self, "Strava", self._import_summary(result))

    def _cancel_edit(self) -> None:
        self._reset_form()

    def _reset_form(self) -> None:
        self._editing_id = None
        self._editing_source_id = None
        self.date_edit.setDate(QDate.currentDate())
        self.type_combo.setCurrentIndex(0)
        self.distance_spin.setValue(0)
        self.duration_edit.setTime(QTime(0, 0))
        self.notes_edit.clear()
        self._set_segments([])
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
