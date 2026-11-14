"""VimMode on a real QPlainTextEdit, driven by key events.

Expected results marked "vim" were checked against vim 9.1 (`vim -u NONE`).
"""

from collections.abc import Iterator
from math import ceil

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QGuiApplication, QInputMethodEvent, QKeyEvent, QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QVBoxLayout, QWidget
from qtkeys import cursor_of, put_cursor, send, start_vim, text_of, type_text

from side_vim import Mode, VimMode
from side_vim.keys import IS_MAC, control_modifier
from side_vim.motions import Pos
from side_vim.vim import QT_EDIT_KEYS

SMILE = "\U0001f600"
FAMILY = "\U0001f468‍\U0001f469‍\U0001f467"
UA = "\U0001f1fa\U0001f1e6"


class Window(QWidget):
    """An editor in a window that records the keys the editor passed on."""

    def __init__(self) -> None:
        super().__init__()
        self.editor = QPlainTextEdit(self)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 8)
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        self.passed_on: list[int] = []
        self.resize(600, 300)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self.passed_on.append(event.key())


@pytest.fixture
def window(qapp: QApplication) -> Iterator[Window]:
    w = Window()
    w.show()
    yield w
    w.close()
    w.deleteLater()


@pytest.fixture
def editor(window: Window) -> QPlainTextEdit:
    return window.editor


# --- motions ---


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    [
        ("😀👨\u200d👩\u200d👧🇺🇦x", 0, 0, "l", [0, 1]),
        ("😀👨\u200d👩\u200d👧🇺🇦x", 0, 0, "3l", [0, 3]),
        ("😀👨\u200d👩\u200d👧🇺🇦x", 0, 0, "$", [0, 3]),
        ("😀👨\u200d👩\u200d👧🇺🇦x", 0, 3, "h", [0, 2]),
        ("😀 👨\u200d👩\u200d👧 x", 0, 0, "w", [0, 2]),
        ("😀 👨\u200d👩\u200d👧 x", 0, 0, "2w", [0, 4]),
    ],
)
def test_motions(
    editor: QPlainTextEdit, text: str, line: int, col: int, keys: str, expected: tuple[int, int]
) -> None:
    start_vim(editor, text, line, col)
    send(editor, keys)
    assert cursor_of(editor) == Pos(*expected)
    assert text_of(editor) == text


def test_tab_width_comes_from_the_editor(editor: QPlainTextEdit) -> None:
    editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * 4)
    start_vim(editor, "\tx\nabcdefghij", 0, 1)
    send(editor, "j")
    assert cursor_of(editor) == Pos(1, 4)


def test_j_forgets_the_column_when_the_cursor_moves(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abcdef\nab\nabcdef", 0, 4)
    send(editor, "j")
    assert cursor_of(editor) == Pos(1, 1)
    put_cursor(editor, Pos(1, 0))  # a click, say
    send(editor, "j")
    assert cursor_of(editor) == Pos(2, 0)


def test_j_forgets_the_column_when_the_text_changes(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abcdef\nab\nabcdef", 0, 4)
    send(editor, "j")
    # the app adds text after the cursor, which stays where it is
    cursor = editor.textCursor()
    cursor.movePosition(cursor.MoveOperation.EndOfBlock)
    cursor.insertText("zzzz")
    assert cursor_of(editor) == Pos(1, 1)
    send(editor, "j")
    assert cursor_of(editor) == Pos(2, 1)


def test_a_click_forgets_the_column(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abcdef\nab", 1, 1)
    send(editor, "$")
    assert cursor_of(editor) == Pos(1, 1)
    rect = editor.cursorRect()
    QTest.mouseClick(
        editor.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(rect.x() + 1, rect.center().y()),
    )
    assert cursor_of(editor) == Pos(1, 1)
    send(editor, "k")
    assert cursor_of(editor) == Pos(0, 1)


def test_a_refused_motion_keeps_the_cursor(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc\ndef", 1, 1)
    send(editor, "j")
    assert cursor_of(editor) == Pos(1, 1)
    send(editor, "0h")
    assert cursor_of(editor) == Pos(1, 0)


def test_empty_document(editor: QPlainTextEdit) -> None:
    start_vim(editor, "")
    send(editor, "hjklwbeWBE0^$ggG3w")
    assert cursor_of(editor) == Pos(0, 0)
    assert text_of(editor) == ""


# --- Normal mode never types ---


# QTest gives Alt+x the text "x", which on macOS is what Option typed, so vim's x.
ALT_X = pytest.param("<A-x>", marks=pytest.mark.skipif(IS_MAC, reason="Option+x types ≈"))


@pytest.mark.parametrize(
    "keys", ["z", "q", " ", "<BS>", "<Del>", "<CR>", "<Tab>", "<S-Tab>", ALT_X, "~", "к"]
)
def test_normal_mode_keys_never_edit(editor: QPlainTextEdit, keys: str) -> None:
    start_vim(editor, "abc\ndef", 0, 1)
    send(editor, keys)
    assert text_of(editor) == "abc\ndef"
    assert cursor_of(editor) == Pos(0, 1)


def test_option_x_never_edits(editor: QPlainTextEdit) -> None:
    """What Option+x sends on a Mac with the English layout."""
    start_vim(editor, "abc\ndef", 0, 1)
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        event = QKeyEvent(kind, Qt.Key.Key_X, Qt.KeyboardModifier.AltModifier, "≈")
        QApplication.sendEvent(editor, event)
    assert text_of(editor) == "abc\ndef"
    assert cursor_of(editor) == Pos(0, 1)


@pytest.mark.parametrize("text", [FAMILY, UA, "e\u0301", "\u200d"])
def test_normal_mode_never_types_joined_characters(editor: QPlainTextEdit, text: str) -> None:
    """One key press that types a whole emoji, as some keyboards send it."""
    start_vim(editor, "abc", 0, 1)
    type_text(editor, text)
    assert text_of(editor) == "abc"


def test_insert_key_doesnt_turn_on_overwrite(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc")
    send(editor, "<Insert>")
    assert not editor.overwriteMode()


def commit(editor: QPlainTextEdit, text: str) -> None:
    """Text from an input method, the way IBus or Fcitx send it."""
    event = QInputMethodEvent()
    event.setCommitString(text)
    QApplication.sendEvent(editor, event)


def test_input_method_types_only_in_insert_mode(editor: QPlainTextEdit) -> None:
    """Outside Insert mode its text works as keys: here x deletes a character."""
    start_vim(editor, "abc def")
    commit(editor, "x")
    assert text_of(editor) == "bc def"
    commit(editor, "日")
    assert text_of(editor) == "bc def"
    send(editor, "i")
    commit(editor, "日")
    assert text_of(editor) == "日bc def"


def test_input_method_text_on_the_ukrainian_layout(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc def ghi")
    commit(editor, "ц")  # w
    assert cursor_of(editor) == Pos(0, 4)
    commit(editor, "в")  # d, then w
    commit(editor, "ц")
    assert text_of(editor) == "abc ghi"
    commit(editor, "2")
    commit(editor, "д")  # 2l
    assert cursor_of(editor) == Pos(0, 6)
    commit(editor, "м")  # v
    assert vim.mode is Mode.VISUAL
    commit(editor, "<")  # not a letter: no map, and not a key vim knows
    commit(editor, "н")  # y
    assert vim.mode is Mode.NORMAL
    vim.layout_map = None
    commit(editor, "ц")
    assert cursor_of(editor) == Pos(0, 6)


def test_input_method_text_that_starts_insert_mode(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc")
    commit(editor, "Шxy")  # I, then x and y are typed
    assert vim.mode is Mode.INSERT
    assert text_of(editor) == "xyabc"
    send(editor, "<Esc>u")
    assert text_of(editor) == "abc"


def test_other_ctrl_keys_go_to_the_editor(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc def")
    QTest.keySequence(editor, QKeySequence.StandardKey.SelectAll)
    assert editor.textCursor().selectedText() == "abc def"


@pytest.mark.parametrize("selection", ["", "v", "V"])
@pytest.mark.parametrize("key", QT_EDIT_KEYS, ids=[key.name for key in QT_EDIT_KEYS])
def test_qts_edit_keys_do_nothing_outside_insert_mode(
    editor: QPlainTextEdit, selection: str, key: QKeySequence.StandardKey
) -> None:
    if not QKeySequence.keyBindings(key):
        pytest.skip(f"{key.name} has no key on this platform")
    QGuiApplication.clipboard().setText("CLIP")
    vim = start_vim(editor, "abc def\nghi", 0, 4)
    send(editor, f"{selection}l")
    mode = vim.mode
    QTest.keySequence(editor, key)
    assert text_of(editor) == "abc def\nghi"
    assert vim.mode is mode


def test_paste_works_in_insert_mode(editor: QPlainTextEdit) -> None:
    QGuiApplication.clipboard().setText("CLIP")
    start_vim(editor, "abc", 0, 1)
    send(editor, "i")
    QTest.keySequence(editor, QKeySequence.StandardKey.Paste)
    assert text_of(editor) == "aCLIPbc"


def test_page_down_goes_to_the_editor(editor: QPlainTextEdit) -> None:
    start_vim(editor, "\n".join(f"line {i}" for i in range(200)))
    send(editor, "<PageDown>")
    assert cursor_of(editor).line > 0
    assert cursor_of(editor).col <= len("line 99") - 1


# --- Insert mode ---


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected", "cursor"),
    [
        ("abc\ndef", 0, 1, "3ixy<BS><Esc>", "axxxbc\ndef", [0, 3]),
        (
            "😀b",
            0,
            0,
            "2a👨\u200d👩\u200d👧<Esc>",
            "😀👨\u200d👩\u200d👧👨\u200d👩\u200d👧b",
            [0, 2],
        ),
        ("a🇺🇦b", 0, 1, "2a🇺🇦<Esc>", "a🇺🇦🇺🇦🇺🇦b", [0, 3]),
    ],
)
def test_insert(
    editor: QPlainTextEdit,
    text: str,
    line: int,
    col: int,
    keys: str,
    expected: str,
    cursor: tuple[int, int],
) -> None:
    vim = start_vim(editor, text, line, col)
    send(editor, keys)
    assert text_of(editor) == expected
    assert cursor_of(editor) == Pos(*cursor)
    assert vim.mode is Mode.NORMAL


def test_insert_mode_types_and_passes_keys(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc")
    send(editor, "A")
    assert vim.mode is Mode.INSERT
    send(editor, "hjkl <BS>x")
    QTest.keySequence(editor, QKeySequence.StandardKey.SelectAll)
    assert text_of(editor) == "abchjklx"
    assert editor.textCursor().selectedText() == "abchjklx"


def test_insert_mode_cursor_can_sit_after_the_last_character(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc")
    send(editor, "A")
    assert cursor_of(editor) == Pos(0, 3)
    send(editor, "<End>")
    assert cursor_of(editor) == Pos(0, 3)


# --- Esc ---


def test_esc_with_nothing_pending_goes_to_the_app(window: Window) -> None:
    start_vim(window.editor, "abc")
    send(window.editor, "<Esc>")
    assert window.passed_on == [Qt.Key.Key_Escape]


def test_esc_cancels_pending_keys(window: Window) -> None:
    vim = start_vim(window.editor, "abc def ghi")
    send(window.editor, "2<Esc>w")
    assert window.passed_on == []
    assert cursor_of(window.editor) == Pos(0, 4)
    assert vim.mode is Mode.NORMAL


def test_esc_in_insert_mode_stays_with_vim(window: Window) -> None:
    start_vim(window.editor, "abc")
    send(window.editor, "i<Esc>")
    assert window.passed_on == []
    send(window.editor, "i<C-[>")
    assert Qt.Key.Key_Escape not in window.passed_on


# --- signals ---


def test_mode_signal(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc")
    modes: list[Mode] = []
    vim.mode_changed.connect(modes.append)
    send(editor, "<Esc>")
    assert modes == []
    send(editor, "ix<Esc>")
    assert modes == [Mode.INSERT, Mode.NORMAL]
    send(editor, "o<Esc>A<Esc>")
    assert modes == [Mode.INSERT, Mode.NORMAL] * 3


def test_pending_signal(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc def")
    pending: list[str] = []
    vim.pending_changed.connect(pending.append)
    send(editor, "2w")
    assert pending == ["2", ""]
    send(editor, "1")
    send(editor, "2")
    send(editor, "g")
    send(editor, "g")
    assert pending == ["2", "", "1", "12", "12g", ""]
    send(editor, "g<Esc>")
    assert pending[-2:] == ["g", ""]
    send(editor, "3z")
    assert pending[-2:] == ["3", ""]


# --- the cursor ---


def test_block_cursor(editor: QPlainTextEdit) -> None:
    editor.setCursorWidth(2)
    start_vim(editor, "abc 日本")
    metrics = editor.fontMetrics()
    normal = editor.cursorWidth()
    assert normal > 2
    line = editor.document().firstBlock().layout().lineAt(0)
    assert normal == ceil(line.cursorToX(1)[0] - line.cursorToX(0)[0])
    send(editor, "$")
    assert editor.cursorWidth() >= metrics.horizontalAdvance("x")
    send(editor, "a")
    assert editor.cursorWidth() == 2
    send(editor, "<Esc>")
    assert editor.cursorWidth() > 2


def test_block_cursor_on_an_empty_line(editor: QPlainTextEdit) -> None:
    start_vim(editor, "")
    assert editor.cursorWidth() == max(editor.fontMetrics().horizontalAdvance("x"), 1)


def click(editor: QPlainTextEdit, line: int, x_offset: int) -> None:
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().findBlockByNumber(line).position())
    rect = editor.cursorRect(cursor)
    QTest.mouseClick(
        editor.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(rect.x() + x_offset, rect.center().y()),
    )


def test_a_click_after_the_line_end_lands_on_the_last_character(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc\ndef")
    click(editor, 1, 400)
    assert cursor_of(editor) == Pos(1, 2)


def test_a_click_in_insert_mode_may_land_after_the_line_end(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc\ndef")
    send(editor, "i")
    click(editor, 1, 400)
    assert cursor_of(editor) == Pos(1, 3)


def test_the_app_putting_the_cursor_at_the_line_end(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc\ndef")
    cursor = editor.textCursor()
    cursor.setPosition(3)
    editor.setTextCursor(cursor)
    assert cursor_of(editor) == Pos(0, 2)


def test_the_app_putting_the_cursor_inside_a_character(editor: QPlainTextEdit) -> None:
    start_vim(editor, f"a{FAMILY}b")
    cursor = editor.textCursor()
    cursor.setPosition(4)  # inside the family emoji
    editor.setTextCursor(cursor)
    assert editor.textCursor().position() == 1


def test_new_text_from_the_app(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc")
    editor.setPlainText("hello\nworld")
    send(editor, "$")
    assert cursor_of(editor) == Pos(0, 4)
    assert vim.mode is Mode.NORMAL


# --- turning vim off ---


def test_set_enabled(editor: QPlainTextEdit) -> None:
    editor.setCursorWidth(2)
    vim = start_vim(editor, "abc")
    modes: list[Mode] = []
    vim.mode_changed.connect(modes.append)
    vim.set_enabled(False)
    assert not vim.enabled
    assert editor.cursorWidth() == 2
    send(editor, "<End>x")
    assert text_of(editor) == "abcx"
    assert cursor_of(editor) == Pos(0, 4)
    vim.set_enabled(True)
    assert vim.enabled
    assert vim.mode is Mode.NORMAL
    assert cursor_of(editor) == Pos(0, 3)  # back on a character
    assert editor.cursorWidth() > 2
    assert modes == []


def test_set_enabled_from_insert_mode_returns_to_normal(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc")
    send(editor, "A")
    vim.set_enabled(False)
    vim.set_enabled(True)
    assert vim.mode is Mode.NORMAL
    assert cursor_of(editor) == Pos(0, 2)
    send(editor, "x")  # a Normal mode command, not typing
    assert text_of(editor) == "ab"


def test_set_enabled_drops_pending_keys(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc def")
    pending: list[str] = []
    vim.pending_changed.connect(pending.append)
    send(editor, "2")
    vim.set_enabled(False)
    assert pending == ["2", ""]
    vim.set_enabled(True)
    send(editor, "w")
    assert cursor_of(editor) == Pos(0, 4)


def test_disabled_esc_goes_to_the_app(window: Window) -> None:
    vim = start_vim(window.editor, "abc")
    send(window.editor, "i")
    vim.set_enabled(False)
    send(window.editor, "<Esc>")
    assert window.passed_on == [Qt.Key.Key_Escape]


def test_detach(editor: QPlainTextEdit) -> None:
    editor.setCursorWidth(2)
    vim = start_vim(editor, "abc")
    vim.detach()
    assert editor.cursorWidth() == 2
    send(editor, "x")
    assert text_of(editor) == "xabc"
    vim.set_enabled(True)
    send(editor, "y")
    assert text_of(editor) == "xyabc"
    vim.detach()  # twice is fine


def test_two_editors_have_their_own_modes(qapp: QApplication) -> None:
    a, b = QPlainTextEdit(), QPlainTextEdit()
    vim_a, vim_b = VimMode(a), VimMode(b)
    send(a, "i")
    assert vim_a.mode is Mode.INSERT
    assert vim_b.mode is Mode.NORMAL
    send(b, "x")
    assert b.toPlainText() == ""


def test_shortcut_override(editor: QPlainTextEdit) -> None:
    """Keys vim takes are claimed before app shortcuts can fire."""
    start_vim(editor, "abc")

    def claimed(key: Qt.Key, mods: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> bool:
        event = QKeyEvent(QEvent.Type.ShortcutOverride, key, mods, "")
        event.ignore()
        QApplication.sendEvent(editor, event)
        return event.isAccepted()

    assert claimed(Qt.Key.Key_R, control_modifier())
    assert not claimed(Qt.Key.Key_S, control_modifier())
    assert not claimed(Qt.Key.Key_Escape)  # nothing pending: the app may use it
    send(editor, "i")
    assert claimed(Qt.Key.Key_Escape)
    assert not claimed(Qt.Key.Key_R, control_modifier())


def test_a_vim_mode_python_already_cleared(
    editor: QPlainTextEdit, capfd: pytest.CaptureFixture[str]
) -> None:
    """When a window closes, Python's garbage collector may empty a VimMode while Qt
    still sends the editor's last events. They must go through, not crash."""
    vim = start_vim(editor, "abc")
    vim.__dict__.clear()
    # events a closing window still gets, none of which move the cursor
    for event in (
        QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier),
        QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier),
        QEvent(QEvent.Type.FontChange),
        QEvent(QEvent.Type.Hide),
    ):
        QApplication.sendEvent(editor, event)
    QApplication.sendEvent(editor.viewport(), QEvent(QEvent.Type.Hide))
    assert "Error" not in capfd.readouterr().err


def test_a_long_document(editor: QPlainTextEdit) -> None:
    rows = [f"{i} {SMILE}{FAMILY} {UA} word" for i in range(5000)]
    start_vim(editor, "\n".join(rows))
    send(editor, "G$")
    assert cursor_of(editor) == Pos(4999, len("4999 ") + 2 + 1 + 1 + 1 + 3)
    send(editor, "2500Gw")
    assert cursor_of(editor) == Pos(2499, 5)
    send(editor, "kA!<Esc>")
    assert text_of(editor).split("\n")[2498] == rows[2498] + "!"
