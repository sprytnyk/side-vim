"""The scrolling keys on a real QPlainTextEdit that shows 11 lines, like the vim window
the cases were checked in (see test_scroll.py). The editor can't scroll past the last
line at its bottom (line 49 at the top), so the top stops there; the cursor still goes
to vim's line and column."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QVBoxLayout, QWidget
from qtkeys import cursor_of, put_cursor, send
from test_scroll import ROWS

from side_vim import Mode, VimMode
from side_vim.motions import Pos


def line_text(i: int) -> str:
    indent = "    " if i % 3 == 0 else "  " if i % 3 == 1 else ""
    return indent + f"line {i}" + ("" if i % 4 else " with more text here")


TEXT = "\n".join(line_text(i) for i in range(1, 61))
MAX_TOP = 49


@pytest.fixture
def editor(qapp: QApplication) -> Iterator[QPlainTextEdit]:
    e = QPlainTextEdit()
    e.setTabStopDistance(e.fontMetrics().horizontalAdvance(" ") * 8)
    e.resize(600, 11 * e.fontMetrics().lineSpacing() + 2 * e.frameWidth() + 10)
    e.show()
    e.setPlainText(TEXT)
    yield e
    e.close()
    e.deleteLater()


def start(editor: QPlainTextEdit, top: int, line: int, col: int) -> VimMode:
    vim = VimMode(editor)
    put_cursor(editor, Pos(line, col))
    editor.verticalScrollBar().setValue(top)
    assert editor.firstVisibleBlock().blockNumber() == top
    assert vim._view() == (top, 11, MAX_TOP)
    return vim


def top_of(editor: QPlainTextEdit) -> int:
    return editor.firstVisibleBlock().blockNumber()


@pytest.mark.parametrize(
    ("top", "line", "col", "keys", "expected"), [row for row in ROWS if row[0] <= MAX_TOP]
)
def test_vim(
    editor: QPlainTextEdit, top: int, line: int, col: int, keys: str, expected: tuple[int, int, int]
) -> None:
    vim = start(editor, top, line, col)
    send(editor, keys.replace("|", ""))
    vim_top, vim_line, vim_col = expected
    assert (top_of(editor), cursor_of(editor)) == (min(vim_top, MAX_TOP), Pos(vim_line, vim_col))
    assert vim.mode is Mode.NORMAL


def test_the_column_j_and_k_aim_for_stays(editor: QPlainTextEdit) -> None:
    """vim: from line 12 column 8 (a short line next), 3 Ctrl+E then j."""
    start(editor, 10, 12, 8)
    send(editor, "3<C-e>")
    assert cursor_of(editor) == Pos(13, 6)
    send(editor, "j")
    assert cursor_of(editor) == Pos(14, 8)


def test_scrolling_moves_the_end_of_a_selection(editor: QPlainTextEdit) -> None:
    vim = start(editor, 10, 12, 2)
    send(editor, "v<C-d>")
    assert vim.mode is Mode.VISUAL
    assert top_of(editor) == 15
    assert vim._caret.position == editor.document().findBlockByNumber(17).position() + 4
    send(editor, "y")
    assert cursor_of(editor) == Pos(12, 2)


def test_scrolling_works_in_a_read_only_editor(editor: QPlainTextEdit) -> None:
    editor.setReadOnly(True)
    start(editor, 10, 12, 2)
    send(editor, "<C-f>")
    assert (top_of(editor), cursor_of(editor)) == (19, Pos(19, 0))


class Window(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.editor = QPlainTextEdit(self)
        QVBoxLayout(self).addWidget(self.editor)
        self.fired: list[str] = []
        for key in ("Ctrl+E", "Ctrl+D", "Ctrl+B", "Ctrl+R", "Ctrl+S"):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(lambda key=key: self.fired.append(key))


def test_vims_ctrl_keys_win_over_the_apps_shortcuts(qapp: QApplication) -> None:
    window = Window()
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    window.editor.setFocus()
    window.editor.setPlainText(TEXT)
    vim = VimMode(window.editor)
    send(window.editor, "<C-e><C-d><C-b><C-r><C-s>")
    assert window.fired == ["Ctrl+S"]
    send(window.editor, "i<C-e><C-d><C-b><C-r>")
    assert vim.mode is Mode.INSERT
    assert window.fired == ["Ctrl+S", "Ctrl+E", "Ctrl+D", "Ctrl+B", "Ctrl+R"]
    window.close()
    window.deleteLater()


def test_key_names_match_qt() -> None:
    assert QKeySequence("Ctrl+E")[0].key() == Qt.Key.Key_E
