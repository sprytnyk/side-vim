"""Visual and Visual Line mode on a real QPlainTextEdit.

Expected results marked "vim" were checked against vim 9.1 (`vim -u NONE`, with
'nojoinspaces'): the text, the cursor and the unnamed register. In keys, | only splits
commands: vim's `:normal` makes one undo step of everything it runs, so the vim check
ran each part on its own.
"""

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QVBoxLayout, QWidget
from qtkeys import cursor_of, plain, send, start_vim, text_of

import side_vim.vim as vim_module
from side_vim import Mode, VimMode
from side_vim.caret import char_width
from side_vim.edits import Register
from side_vim.motions import Pos
from side_vim.text import Lines

pytestmark = pytest.mark.usefixtures("empty_register")

T = "ab cd ef\n  gh ij\nkl"
FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
UA = "\U0001f1fa\U0001f1e6"


def run(editor: QPlainTextEdit, keys: str) -> None:
    send(editor, keys.replace("|", ""))


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected", "cursor", "register"),
    [
        # vim splits these into code points; here each is one character
        (FAMILY + UA + "x", 0, 0, "vly", FAMILY + UA + "x", (0, 0), (FAMILY + UA, False)),
        ("a" + FAMILY + UA, 0, 1, "vld", "a", (0, 0), (FAMILY + UA, False)),
        ("a" + FAMILY + UA, 0, 2, "vhd", "a", (0, 0), (FAMILY + UA, False)),
        (UA + UA + "\nb", 0, 1, "v$y", UA + UA + "\nb", (0, 1), (UA + "\n", False)),
        (UA + UA + "\nb", 0, 1, "v$d", UA + "b", (0, 1), (UA + "\n", False)),
        (FAMILY + "\n" + UA, 0, 0, "vjy", FAMILY + "\n" + UA, (0, 0), (FAMILY + "\n" + UA, False)),
        ("a" + FAMILY + "b", 0, 1, "vcX<Esc>", "aXb", (0, 1), (FAMILY, False)),
        ("a" + FAMILY + "b", 0, 0, "yl|lvp", "aab", (0, 1), (FAMILY, False)),
        ("ab\n" + UA, 0, 0, "yy|jvp", "ab\n\nab\n", (2, 0), (UA, False)),
        (UA + "\nab", 0, 0, "jyl|kVp", "a\nab", (0, 0), (UA + "\n", True)),
    ],
)
def test_whole_characters(
    editor: QPlainTextEdit,
    text: str,
    line: int,
    col: int,
    keys: str,
    expected: str,
    cursor: tuple[int, int],
    register: tuple[str, bool],
) -> None:
    vim = start_vim(editor, text, line, col)
    run(editor, keys)
    assert text_of(editor) == expected
    assert cursor_of(editor) == Pos(*cursor)
    assert vim_module._register == Register(*register)
    assert vim.mode is Mode.NORMAL


@pytest.mark.parametrize(
    ("keys", "selected"),
    [
        ("v", "b"),
        ("vl", "b "),
        ("vh", "ab"),
        ("vj", "b cd ef\n  "),
        ("vjoh", "ab cd ef\n  "),
        ("v$", "b cd ef\n"),
        ("vj$", "b cd ef\n  gh ij\n"),
        ("vG$", "b cd ef\n  gh ij\nkl"),
        ("V", "ab cd ef"),
        ("Vj", "ab cd ef\n  gh ij"),
        ("jVk", "ab cd ef\n  gh ij"),
        ("VG", "ab cd ef\n  gh ij\nkl"),
    ],
)
def test_the_editor_selects_what_vim_does(editor: QPlainTextEdit, keys: str, selected: str) -> None:
    """The editor's own selection holds the Visual selection, so the app's copy copies
    it. Whole lines leave out the last line break."""
    start_vim(editor, T, 0, 1)
    send(editor, keys)
    assert plain(editor.textCursor().selectedText()) == selected
    linewise = keys.startswith("V") or "V" in keys
    send(editor, "y")
    assert vim_module._register == Register(selected + "\n" if linewise else selected, linewise)


def test_an_empty_last_line_selects_nothing(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "a\n", 1, 0)
    send(editor, "v")
    assert vim.mode is Mode.VISUAL
    assert not editor.textCursor().hasSelection()


def caret_rect(editor: QPlainTextEdit, pos: Pos) -> tuple[int, int, int]:
    """Where vim's cursor should be drawn: x, y and width."""
    cursor = QTextCursor(editor.document())
    cursor.setPosition(Lines(editor.document().toRawText()).to_qt(pos))
    rect = editor.cursorRect(cursor)
    return rect.x(), rect.y(), char_width(editor, cursor.position())


def caret_of(vim: VimMode) -> tuple[int, int, int] | None:
    caret = vim._caret
    if not caret.isVisible():
        return None
    return caret.x(), caret.y(), caret.width()


def test_the_cursor_is_drawn_where_vims_is(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T + "\n" + FAMILY + UA, 0, 1)
    block = editor.cursorWidth()
    assert caret_of(vim) is None
    send(editor, "vl")
    # the editor's own cursor is at the end of its selection, after vim's
    assert editor.cursorWidth() == 0
    assert caret_of(vim) == caret_rect(editor, Pos(0, 2))
    send(editor, "j")
    assert caret_of(vim) == caret_rect(editor, Pos(1, 2))
    send(editor, "$")
    assert caret_of(vim) == caret_rect(editor, Pos(1, 7))
    send(editor, "o")
    assert caret_of(vim) == caret_rect(editor, Pos(0, 1))
    send(editor, "V")
    assert caret_of(vim) == caret_rect(editor, Pos(0, 1))
    send(editor, "3j")  # the family emoji takes columns 0 and 1 on screen
    assert caret_of(vim) == caret_rect(editor, Pos(3, 0))
    assert caret_rect(editor, Pos(3, 0))[2] > caret_rect(editor, Pos(0, 0))[2]
    send(editor, "l")
    assert caret_of(vim) == caret_rect(editor, Pos(3, 1))
    send(editor, "<Esc>")
    assert caret_of(vim) is None
    assert editor.cursorWidth() == char_width(editor, editor.textCursor().position())
    assert block == char_width(editor, 1)
    send(editor, "vi")  # i does nothing in Visual mode yet
    send(editor, "c")
    assert caret_of(vim) is None
    assert editor.cursorWidth() == 1


def test_the_cursor_follows_a_scroll(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "\n".join(f"line {i}" for i in range(200)), 100, 2)
    send(editor, "vl")
    assert caret_of(vim) == caret_rect(editor, Pos(100, 3))
    bar = editor.verticalScrollBar()
    bar.setValue(bar.value() - 5)
    QApplication.processEvents()
    assert caret_of(vim) == caret_rect(editor, Pos(100, 3))


def test_mode_signals(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    modes: list[Mode] = []
    vim.mode_changed.connect(modes.append)
    send(editor, "vVvv")
    send(editor, "Vy")
    send(editor, "v<Esc>")
    assert modes == [
        Mode.VISUAL,
        Mode.VISUAL_LINE,
        Mode.VISUAL,
        Mode.NORMAL,
        Mode.VISUAL_LINE,
        Mode.NORMAL,
        Mode.VISUAL,
        Mode.NORMAL,
    ]


def test_counts_and_pending_keys(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T, 0, 0)
    shown: list[str] = []
    vim.pending_changed.connect(shown.append)
    send(editor, "v2")
    assert shown == ["2"]
    send(editor, "<Esc>")
    assert shown == ["2", ""]
    assert vim.mode is Mode.NORMAL
    send(editor, "v2gg")
    assert shown == ["2", "", "2", "2g", ""]
    assert vim.mode is Mode.VISUAL
    send(editor, "y")
    assert vim_module._register == Register("ab cd ef\n  g", linewise=False)


class Window(QWidget):
    """An editor in a window that records the keys the editor passed on."""

    def __init__(self) -> None:
        super().__init__()
        self.editor = QPlainTextEdit(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        self.passed_on: list[int] = []

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self.passed_on.append(event.key())


def test_esc_in_visual_mode_stays_with_vim(qapp: QApplication) -> None:
    window = Window()
    window.show()
    vim = start_vim(window.editor, T)
    send(window.editor, "v<Esc>")
    assert vim.mode is Mode.NORMAL
    assert window.passed_on == []
    send(window.editor, "V<C-[>")
    assert vim.mode is Mode.NORMAL
    assert Qt.Key.Key_Escape not in window.passed_on
    window.passed_on.clear()
    send(window.editor, "<Esc>")
    assert window.passed_on == [Qt.Key.Key_Escape]
    window.close()
    window.deleteLater()


LEFT = Qt.MouseButton.LeftButton
NO_KEYS = Qt.KeyboardModifier.NoModifier


def point(editor: QPlainTextEdit, pos: Pos) -> QPoint:
    """A point just inside the character at pos. Outside Insert mode the editor is in
    overwrite mode, where a click goes on the character under it, and the character's
    left edge can fall inside the pixel column before it."""
    cursor = QTextCursor(editor.document())
    cursor.setPosition(Lines(editor.document().toRawText()).to_qt(pos))
    rect = editor.cursorRect(cursor)
    return QPoint(rect.x() + 1, rect.center().y())


def drag(editor: QPlainTextEdit, a: Pos, b: Pos) -> None:
    viewport = editor.viewport()
    QTest.mousePress(viewport, LEFT, NO_KEYS, point(editor, a))
    QTest.mouseMove(viewport, point(editor, b))
    QTest.mouseRelease(viewport, LEFT, NO_KEYS, point(editor, b))


@pytest.mark.parametrize(
    ("a", "b", "selected", "cursor"),
    [
        (Pos(0, 1), Pos(0, 5), "b cd", Pos(0, 4)),
        (Pos(0, 5), Pos(0, 1), "b cd", Pos(0, 1)),
        (Pos(0, 3), Pos(1, 3), "cd ef\n  g", Pos(1, 2)),
        (Pos(1, 3), Pos(0, 3), "cd ef\n  g", Pos(0, 3)),
        (Pos(0, 6), Pos(1, 0), "ef\n", Pos(0, 8)),
    ],
)
def test_a_drag_starts_visual_mode(
    editor: QPlainTextEdit, a: Pos, b: Pos, selected: str, cursor: Pos
) -> None:
    """The characters the drag selected stay selected, with vim's cursor on the last
    one at the end the mouse is."""
    vim = start_vim(editor, T)
    drag(editor, a, b)
    assert vim.mode is Mode.VISUAL
    assert plain(editor.textCursor().selectedText()) == selected
    assert caret_of(vim) == caret_rect(editor, cursor)
    send(editor, "y")
    assert vim_module._register == Register(selected, linewise=False)
    send(editor, "v")
    assert caret_of(vim) == caret_rect(editor, min(a, b))


def test_keys_go_on_from_a_drag(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    drag(editor, Pos(0, 3), Pos(0, 5))
    send(editor, "l")
    assert plain(editor.textCursor().selectedText()) == "cd "
    send(editor, "d")
    assert text_of(editor) == "ab ef\n  gh ij\nkl"
    assert vim.mode is Mode.NORMAL


def test_a_double_click_selects_a_word(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    QTest.mouseDClick(editor.viewport(), LEFT, NO_KEYS, point(editor, Pos(0, 4)))
    assert vim.mode is Mode.VISUAL
    send(editor, "d")
    assert text_of(editor) == "ab  ef\n  gh ij\nkl"


def test_a_click_ends_visual_mode(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    send(editor, "vj")
    QTest.mouseClick(editor.viewport(), LEFT, NO_KEYS, point(editor, Pos(2, 1)))
    assert vim.mode is Mode.NORMAL
    assert not editor.textCursor().hasSelection()
    assert cursor_of(editor) == Pos(2, 1)
    assert caret_of(vim) is None


def test_a_drag_in_insert_mode_stays_a_plain_selection(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    send(editor, "i")
    drag(editor, Pos(0, 1), Pos(0, 5))
    assert vim.mode is Mode.INSERT
    assert editor.textCursor().selectedText() == "b cd"
    assert caret_of(vim) is None


def test_the_app_changing_text_elsewhere_keeps_the_selection(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T, 1, 2)
    send(editor, "vl")
    edit = QTextCursor(editor.document())
    edit.insertText("new\n")
    assert vim.mode is Mode.VISUAL
    assert editor.textCursor().selectedText() == "gh"
    assert caret_of(vim) == caret_rect(editor, Pos(2, 3))
    send(editor, "y")
    assert vim_module._register == Register("gh", linewise=False)


def test_new_text_from_the_app_ends_visual_mode(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T, 1, 2)
    send(editor, "Vj")
    editor.setPlainText("other")
    assert vim.mode is Mode.NORMAL
    assert caret_of(vim) is None
    send(editor, "x")
    assert text_of(editor) == "ther"


def test_a_selection_by_the_app_in_visual_mode(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    send(editor, "v")
    cursor = editor.textCursor()
    cursor.setPosition(4)
    cursor.setPosition(1, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    assert vim.mode is Mode.VISUAL
    assert caret_of(vim) == caret_rect(editor, Pos(0, 1))
    send(editor, "d")
    assert text_of(editor) == "ad ef\n  gh ij\nkl"


def test_a_selection_by_the_app_in_normal_mode_stays_the_apps(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    cursor = editor.textCursor()
    cursor.setPosition(1)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    assert vim.mode is Mode.NORMAL


def test_turning_vim_off_in_visual_mode(editor: QPlainTextEdit) -> None:
    plain_width = editor.cursorWidth()
    vim = start_vim(editor, T)
    send(editor, "vl")
    vim.set_enabled(False)
    assert caret_of(vim) is None
    assert editor.cursorWidth() == plain_width
    assert editor.textCursor().selectedText() == "ab"
    vim.set_enabled(True)
    assert vim.mode is Mode.NORMAL
    send(editor, "v")
    assert caret_of(vim) is not None
    vim.detach()
    assert caret_of(vim) is None
    assert editor.cursorWidth() == plain_width


@pytest.mark.parametrize(
    "keys",
    ["vjd", "Vjd", "vjcXY<Esc>", "VcXY<Esc>", "vlp", "Vp", "vjp", "Vjp", "vx"],
)
def test_each_visual_command_is_one_undo_step(editor: QPlainTextEdit, keys: str) -> None:
    start_vim(editor, T, 0, 1)
    vim_module._register = Register("reg\n", linewise=True) if "V" in keys else Register("r")
    send(editor, keys)
    assert text_of(editor) != T
    after = text_of(editor)
    send(editor, "u")
    assert text_of(editor) == T
    send(editor, "<C-r>")
    assert text_of(editor) == after
    editor.document().undo()
    assert text_of(editor) == T


def test_yank_to_the_clipboard(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T, 0, 3)
    vim.clipboard = True
    send(editor, "vly")
    assert QGuiApplication.clipboard().text() == "cd"
    send(editor, "Vd")
    assert QGuiApplication.clipboard().text() == "ab cd ef\n"
    QGuiApplication.clipboard().setText("new")
    send(editor, "vp")  # on the first non-blank after Vd
    assert text_of(editor) == "  newh ij\nkl"
    assert QGuiApplication.clipboard().text() == "g"


def test_the_editors_cursor_is_off_in_visual_mode(editor: QPlainTextEdit) -> None:
    flags = editor.textInteractionFlags()
    vim = start_vim(editor, T)
    send(editor, "V")
    assert not editor.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable
    send(editor, "v<Esc>")
    assert editor.textInteractionFlags() == flags
    send(editor, "vl")
    vim.set_enabled(False)
    assert editor.textInteractionFlags() == flags


def test_flags_the_app_sets_in_visual_mode_stay(editor: QPlainTextEdit) -> None:
    start_vim(editor, T)
    send(editor, "v")
    editor.setReadOnly(True)
    send(editor, "<Esc>")
    assert editor.isReadOnly()
    editor.setReadOnly(False)
    send(editor, "v")
    editor.setReadOnly(False)
    assert not editor.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable
    send(editor, "<Esc>")
    assert not editor.isReadOnly()
    send(editor, "v")
    editor.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    send(editor, "<Esc>")
    assert editor.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction


def caret_pixels(editor: QPlainTextEdit, vim: VimMode) -> set[str]:
    """The colours at the middle of vim's cursor over a few blinks."""
    caret = vim._caret
    seen = set()
    for _ in range(6):
        QTest.qWait(30)
        image = editor.viewport().grab().toImage()
        seen.add(image.pixelColor(caret.geometry().center()).name())
    return seen


@pytest.fixture
def fast_blink(qapp: QApplication) -> Iterator[None]:
    hints = QGuiApplication.styleHints()
    flash = hints.cursorFlashTime()
    hints.setCursorFlashTime(80)
    yield
    hints.setCursorFlashTime(flash)


@pytest.mark.usefixtures("fast_blink")
def test_the_cursor_blinks_while_the_editor_has_focus(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc")
    editor.activateWindow()
    editor.setFocus()
    send(editor, "v")
    assert len(caret_pixels(editor, vim)) == 2
    editor.clearFocus()
    assert len(caret_pixels(editor, vim)) == 1


SCALED = """
import sys
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from side_vim import VimMode

app = QApplication([])
# blink 5 times faster than the default; 8 looks still see two blinks
app.styleHints().setCursorFlashTime(200)
editor = QPlainTextEdit()
editor.resize(400, 200)
editor.show()
editor.activateWindow()
editor.setFocus()
editor.setPlainText("abcdef\\nxyz")
vim = VimMode(editor)
QTest.keyClick(editor, "V")
cursor = QTextCursor(editor.document())
cursor.setPosition(editor.textCursor().position())
rect = editor.cursorRect(cursor)
ratio = editor.devicePixelRatioF()
seen = set()
for _ in range(8):
    QTest.qWait(30)
    image = editor.viewport().grab().toImage()
    x = round(rect.x() * ratio)
    column = tuple(
        image.pixel(x + dx, y)
        for dx in (-1, 0, 1)
        for y in range(round(rect.top() * ratio), round(rect.bottom() * ratio))
    )
    seen.add(column)
print(ratio, len(seen))
"""


def test_no_editor_cursor_on_a_scaled_screen(qapp: QApplication) -> None:
    """At 150%, Qt draws a cursor of width 0 as a thin line. Nothing may blink at
    the end of the selection, where the editor's cursor is."""
    env = {**os.environ, "QT_SCALE_FACTOR": "1.5", "QT_QPA_PLATFORM": "offscreen"}
    out = subprocess.run(
        [sys.executable, "-c", SCALED], env=env, capture_output=True, text=True, check=True
    )
    assert out.stdout.split() == ["1.5", "1"]
