import re

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QDateEdit

_SECTION_PATTERN = re.compile(r"\S+")


class SegmentedDateEdit(QDateEdit):
    """A date edit that treats each part of the date as one selectable unit.

    Clicking selects the whole part under the mouse, Up and Down change it,
    and Enter, Tab or Right move to the next part (Shift+Tab or Left go back).
    Leaving the last part with Enter or Tab moves focus to the next field.
    The display format must separate its parts with spaces, e.g. "ddd d MMM".
    """

    def __init__(self, *args: object) -> None:
        super().__init__(*args)
        self._focus_section: int | None = None
        self.lineEdit().installEventFilter(self)

    def _section_spans(self) -> list[tuple[int, int]]:
        return [
            (match.start(), match.end())
            for match in _SECTION_PATTERN.finditer(self.lineEdit().text())
        ]

    def select_section(self, index: int) -> None:
        self._focus_section = None
        spans = self._section_spans()
        if not spans:
            return
        index = max(0, min(index, len(spans) - 1))
        self.setCurrentSectionIndex(index)
        start, end = spans[index]
        self.lineEdit().setSelection(start, end - start)

    def _section_at_cursor(self) -> int:
        cursor = self.lineEdit().cursorPosition()
        spans = self._section_spans()
        for index, (_start, end) in enumerate(spans):
            if cursor <= end:
                return index
        return len(spans) - 1

    def _move_section(self, step: int, *, leave_at_edge: bool) -> None:
        target = self.currentSectionIndex() + step
        if 0 <= target < self.sectionCount():
            self.select_section(target)
        elif leave_at_edge:
            if step > 0:
                self.focusNextChild()
            else:
                self.focusPreviousChild()
        else:
            self.select_section(self.currentSectionIndex())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self._focus_section = None
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._move_section(1, leave_at_edge=True)
        elif key == Qt.Key.Key_Tab and not shift:
            self._move_section(1, leave_at_edge=True)
        elif key == Qt.Key.Key_Backtab or (key == Qt.Key.Key_Tab and shift):
            self._move_section(-1, leave_at_edge=True)
        elif key == Qt.Key.Key_Right:
            self._move_section(1, leave_at_edge=False)
        elif key == Qt.Key.Key_Left:
            self._move_section(-1, leave_at_edge=False)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            index = self.currentSectionIndex()
            super().keyPressEvent(event)
            self.select_section(index)
        else:
            super().keyPressEvent(event)
        event.accept()

    def event(self, event: QEvent) -> bool:
        # Qt turns Tab into focus changes before keyPressEvent sees it.
        if event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Tab,
            Qt.Key.Key_Backtab,
        ):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # Clicks land on the inner line edit, not on the date edit itself.
        if (
            watched is self.lineEdit()
            and event.type() == QEvent.Type.MouseButtonRelease
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            QTimer.singleShot(
                0, lambda: self.select_section(self._section_at_cursor())
            )
        return super().eventFilter(watched, event)

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        if event.reason() == Qt.FocusReason.BacktabFocusReason:
            index = self.sectionCount() - 1
        elif event.reason() == Qt.FocusReason.MouseFocusReason:
            return
        else:
            index = 0
        # Qt sets its own selection after focus-in, so apply ours afterwards,
        # unless a key press or another selection has already happened.
        self._focus_section = index
        QTimer.singleShot(0, self._apply_focus_section)

    def _apply_focus_section(self) -> None:
        if self._focus_section is not None and self.hasFocus():
            self.select_section(self._focus_section)
