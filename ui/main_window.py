from datetime import date, timedelta

import matplotlib.dates as mdates
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter
from PySide6.QtCore import QDate, QLocale, QTime, QTimer, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from core.countdown import format_countdown, time_until_race
from core.formatting import format_duration, format_pace
from core.models import ACTIVITY_TYPES, Activity
from core.stats import (
    average_pace,
    daily_km_series,
    km_in_week,
    linear_trend,
    longest_run,
    weekly_km_series,
)
from core.storage import Storage
from ui import theme


def _format_day(day: date, *, with_weekday: bool = False) -> str:
    prefix = f"{day:%a} " if with_weekday else ""
    return f"{prefix}{day.day} {day:%b}"


def _weekly_label_step(count: int) -> int:
    if count > 32:
        return 4
    if count > 16:
        return 2
    return 1


def _daily_tick_interval(monday_count: int) -> int:
    if monday_count > 24:
        return 4
    if monday_count > 10:
        return 2
    return 1


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
        self.countdown_title = QLabel("PRAGUE MARATHON · 2 MAY 2027")
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
        self.chart_granularity = QComboBox(progress_tab)
        self.chart_granularity.addItems(["By week", "By day"])
        self.chart_granularity.currentIndexChanged.connect(
            self._on_chart_controls_changed
        )
        chart_controls.addWidget(self.chart_granularity)

        self.trend_checkbox = QCheckBox("Trend line", progress_tab)
        self.trend_checkbox.toggled.connect(self._on_chart_controls_changed)
        chart_controls.addWidget(self.trend_checkbox)
        chart_controls.addSpacing(16)

        today = date.today()
        default_start = today - timedelta(days=today.weekday(), weeks=11)
        self.chart_from_edit = QDateEdit(progress_tab)
        self.chart_from_edit.setCalendarPopup(True)
        self.chart_from_edit.setDisplayFormat("d MMM yyyy")
        self.chart_from_edit.setMinimumWidth(130)
        self.chart_from_edit.setDate(
            QDate(default_start.year, default_start.month, default_start.day)
        )
        self.chart_from_edit.setMaximumDate(QDate.currentDate())
        self.chart_from_edit.dateChanged.connect(self._on_start_date_changed)
        chart_controls.addWidget(QLabel("From", progress_tab))
        chart_controls.addWidget(self.chart_from_edit)

        self.chart_to_edit = QDateEdit(progress_tab)
        self.chart_to_edit.setCalendarPopup(True)
        self.chart_to_edit.setDisplayFormat("d MMM yyyy")
        self.chart_to_edit.setMinimumWidth(130)
        self.chart_to_edit.setMinimumDate(self.chart_from_edit.date())
        self.chart_to_edit.setMaximumDate(QDate.currentDate())
        self.chart_to_edit.setDate(QDate(today.year, today.month, today.day))
        self.chart_to_edit.dateChanged.connect(self._on_chart_controls_changed)
        chart_controls.addWidget(QLabel("To", progress_tab))
        chart_controls.addWidget(self.chart_to_edit)
        chart_controls.addStretch(1)
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
            self.chart_from_edit.setMaximumDate(today_qdate)
            self.chart_to_edit.setMaximumDate(today_qdate)
            if self.chart_to_edit.date().toPython() == self._last_reload_date:
                self.chart_to_edit.setDate(today_qdate)
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

    def _refresh_chart(self, activities: list[Activity]) -> None:
        self.chart_axes.clear()
        self.chart_axes.set_facecolor(theme.PLOT_BACKGROUND)

        start = self.chart_from_edit.date().toPython()
        end = self.chart_to_edit.date().toPython()
        today = date.today()
        current_monday = today - timedelta(days=today.weekday())
        weekly = self.chart_granularity.currentText() == "By week"
        positions: list[int] = []
        if weekly:
            chart_activities = [
                activity
                for activity in activities
                if start <= activity.date <= end
            ]
            series = weekly_km_series(chart_activities, start, end)
            dates = [monday for monday, _ in series]
            values = [km for _, km in series]
            positions = list(range(len(series)))
            bar_x: list[int] | list[date] = positions
            bar_width = 0.7
            kind = "Weekly"
        else:
            series = daily_km_series(activities, start, end)
            dates = [day for day, _ in series]
            values = [km for _, km in series]
            bar_x = dates
            bar_width = 0.8
            kind = "Daily"
        title = (
            f"{kind} distance · {_format_day(start)} – {_format_day(end)} · "
            f"{sum(values):.0f} km"
        )

        bars = self.chart_axes.bar(
            bar_x,
            values,
            width=bar_width,
            color=theme.ACCENT,
        )
        if weekly or (end - start).days < 31:
            labels: list[str] = []
            for day, value in zip(dates, values):
                if value <= 0:
                    labels.append("")
                elif weekly and day == current_monday and end >= today:
                    labels.append(f"{value:g} · so far")
                else:
                    labels.append(f"{value:g}")
            self.chart_axes.bar_label(
                bars,
                labels=labels,
                padding=4,
                color=theme.TEXT,
                fontsize=9,
            )

        trend_x: list[int] | list[date] = []
        trend_values: list[float] = []
        if self.trend_checkbox.isChecked():
            note: str | None = None
            if weekly:
                complete_week_indexes = [
                    index
                    for index, day in enumerate(dates)
                    if start <= day
                    and day + timedelta(days=6) <= end
                    and day < current_monday
                ]
                trend_input = [
                    values[index] for index in complete_week_indexes
                ]
                if len(trend_input) >= 2 and any(
                    value > 0 for value in trend_input
                ):
                    trend_values = linear_trend(trend_input)
                    trend_x = [
                        positions[index]
                        for index in complete_week_indexes
                    ]
                elif len(trend_input) < 2:
                    note = "Trend needs 2 complete weeks"
                else:
                    note = "No completed distance yet"
            else:
                if len(values) >= 2 and any(value > 0 for value in values):
                    trend_values = linear_trend(values)
                    trend_x = dates
                elif len(values) < 2:
                    note = "Trend needs 2 days"
                else:
                    note = "No distance to trend yet"

            if trend_values:
                for width in range(4, 20, 2):
                    self.chart_axes.plot(
                        trend_x,
                        trend_values,
                        color=theme.TREND,
                        linewidth=width,
                        alpha=0.04,
                        solid_capstyle="round",
                    )
                self.chart_axes.plot(
                    trend_x,
                    trend_values,
                    color=theme.TREND,
                    linewidth=2,
                    label=(
                        f"Trend: {trend_values[1] - trend_values[0]:+.1f} "
                        f"km/{'week' if weekly else 'day'}"
                    ),
                    solid_capstyle="round",
                )
                self.chart_axes.legend(
                    facecolor=theme.SURFACE,
                    edgecolor=theme.BORDER,
                    labelcolor=theme.TEXT,
                )
            elif note is not None:
                self.chart_axes.text(
                    0.98,
                    0.95,
                    note,
                    transform=self.chart_axes.transAxes,
                    ha="right",
                    va="top",
                    color=theme.MUTED_TEXT,
                    fontsize=9,
                )

        if weekly:
            x_limits = (-0.5, max(len(series), 8) - 0.5)
        else:
            x_limits = (
                mdates.date2num(start) - 0.5,
                mdates.date2num(end) + 0.5,
            )
        top = max(10, max(values, default=0) * 1.15)
        if trend_values:
            top = max(top, max(trend_values) * 1.15)
        gradient = np.linspace(0, 1, 256).reshape(-1, 1)
        gloss = LinearSegmentedColormap.from_list(
            "marathon_bar_gloss",
            [theme.ACCENT, theme.BAR_GLOSS],
        )
        for index, bar in enumerate(bars):
            in_progress = weekly and dates[index] == current_monday
            if in_progress:
                bar.set_edgecolor(theme.ACCENT)
                bar.set_linestyle("--")
            if bar.get_height() <= 0:
                continue
            x, y = bar.get_xy()
            image = self.chart_axes.imshow(
                gradient,
                cmap=gloss,
                origin="lower",
                aspect="auto",
                extent=(x, x + bar.get_width(), y, y + bar.get_height()),
                interpolation="bicubic",
                zorder=bar.get_zorder(),
            )
            image.set_clip_path(bar)
            bar.set_facecolor("none")
        self.chart_axes.set_xlim(x_limits)
        self.chart_axes.set_ylim(0, top)

        if weekly:
            label_step = _weekly_label_step(len(dates))
            tick_positions = positions[::label_step]
            self.chart_axes.set_xticks(
                tick_positions,
                [_format_day(dates[index]) for index in tick_positions],
            )
        else:
            monday_count = sum(1 for day in dates if day.weekday() == 0)
            if monday_count:
                self.chart_axes.xaxis.set_major_locator(
                    mdates.WeekdayLocator(
                        byweekday=mdates.MO,
                        interval=_daily_tick_interval(monday_count),
                    )
                )
            else:
                self.chart_axes.xaxis.set_major_locator(mdates.DayLocator())
            self.chart_axes.xaxis.set_major_formatter(
                FuncFormatter(
                    lambda value, _position: _format_day(
                        mdates.num2date(value).date()
                    )
                )
            )
        self._style_axes(title, "Kilometers", rotate_x_labels=not weekly)

        self.chart_figure.tight_layout()
        self.chart_canvas.draw()

    def _on_start_date_changed(self, _date: QDate) -> None:
        del _date
        self.chart_to_edit.setMinimumDate(self.chart_from_edit.date())
        self._refresh_chart(list(self._activities_by_id.values()))

    def _on_chart_controls_changed(self, *_values: object) -> None:
        del _values
        self._refresh_chart(list(self._activities_by_id.values()))

    def _style_axes(
        self,
        title: str,
        ylabel: str,
        *,
        rotate_x_labels: bool = True,
    ) -> None:
        self.chart_axes.set_title(title, color=theme.TEXT)
        self.chart_axes.set_ylabel(ylabel, color=theme.TEXT)
        self.chart_axes.tick_params(
            axis="x",
            colors=theme.MUTED_TEXT,
            rotation=45 if rotate_x_labels else 0,
        )
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
