"""vim's block cursor in Visual mode.

The selection is the editor's own, so the app's copy (Ctrl+C) copies what `y` yanks.
But Qt draws its cursor at one end of its selection, and in vim the character under
the cursor is part of the selection, so the two don't line up. In Visual mode the
editor's cursor is hidden and this widget draws vim's one on top of the text.
"""

from math import ceil

from PySide6.QtCore import QPointF, QRect, Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPalette, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from side_vim.text import split_clusters, utf16_len


class Caret(QWidget):
    def __init__(self, editor: QPlainTextEdit) -> None:
        super().__init__(editor.viewport())
        self._editor = editor
        self._position: int | None = None
        self._text = ""
        self._ascent = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hide()
        editor.updateRequest.connect(self._on_update_request)

    @property
    def position(self) -> int | None:
        """The Qt position of the character it's on, or None when hidden."""
        return self._position

    def show_at(self, position: int | None) -> None:
        """Draw the cursor on the character at this Qt position; None hides it."""
        self._position = position
        self.place()

    def place(self) -> None:
        """Put the widget over its character again, after a scroll or a change."""
        position = self._position
        document = self._editor.document()
        if position is None or position >= document.characterCount():
            self.hide()
            return
        cursor = QTextCursor(document)
        cursor.setPosition(position)
        block = cursor.block()
        offset = position - block.position()
        line = block.layout().lineForTextPosition(offset)
        if not line.isValid():
            self.hide()
            return
        self._text = char_at(block.text(), offset)
        self._ascent = line.ascent()
        rect = self._editor.cursorRect(cursor)
        width = char_width(self._editor, position)
        geometry = QRect(rect.left(), rect.top(), width, ceil(line.height()))
        if self.geometry() != geometry:
            self.setGeometry(geometry)
        self.update()
        self.show()
        self.raise_()

    def _on_update_request(self, _rect: QRect, _dy: int) -> None:
        if self._position is not None:
            self.place()

    def paintEvent(self, event: QPaintEvent) -> None:
        palette = self._editor.palette()
        painter = QPainter(self)
        painter.fillRect(self.rect(), palette.color(QPalette.ColorRole.Text))
        if self._text.strip():
            painter.setPen(palette.color(QPalette.ColorRole.Base))
            painter.setFont(self._editor.font())
            painter.drawText(QPointF(0, self._ascent), self._text)
        painter.end()


def char_at(text: str, offset: int) -> str:
    """The character starting at a UTF-16 offset in a block's text, or "" at its end."""
    end = 0
    for cluster in split_clusters(text):
        end += utf16_len(cluster)
        if end > offset:
            return cluster
    return ""


def char_width(editor: QPlainTextEdit, position: int) -> int:
    """The width of the character at a Qt position, as the editor draws it. At the end
    of a line, the width of an "x"."""
    cursor = QTextCursor(editor.document())
    cursor.setPosition(position)
    block = cursor.block()
    offset = position - block.position()
    metrics = editor.fontMetrics()
    cluster = char_at(block.text(), offset)
    if not cluster:
        return max(metrics.horizontalAdvance("x"), 1)
    line = block.layout().lineForTextPosition(offset)
    end = offset + utf16_len(cluster)
    if line.isValid() and end <= line.textStart() + line.textLength():
        width = line.cursorToX(end)[0] - line.cursorToX(offset)[0]
        if width >= 1:
            return ceil(width)
    return max(metrics.horizontalAdvance(cluster), metrics.horizontalAdvance("x"), 1)
