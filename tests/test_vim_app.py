"""What the app sets up: the search and Esc hooks, set_search with n and N, read-only
editors, and the keyboard layout map. Cases marked "vim" were checked against vim 9.1
(`vim -u NONE`)."""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QVBoxLayout, QWidget
from qtkeys import cursor_of, plain, put_cursor, send, text_of, type_text

import side_vim.vim as vim_module
from side_vim import UKRAINIAN, Mode, VimMode
from side_vim.edits import Register
from side_vim.motions import Pos
from side_vim.parser import NORMAL_ACTIONS, OPERATORS, VISUAL_ACTIONS

T = "foo bar foo\nbaz foo\nfoo"
FAMILY = "\U0001f468‍\U0001f469‍\U0001f467"
UA = "\U0001f1fa\U0001f1e6"


@pytest.fixture(autouse=True)
def empty_register() -> Iterator[None]:
    vim_module._register = Register()
    yield
    vim_module._register = Register()


@pytest.fixture
def editor(qapp: QApplication) -> Iterator[QPlainTextEdit]:
    e = QPlainTextEdit()
    e.resize(600, 300)
    e.show()
    yield e
    e.close()
    e.deleteLater()


def start(editor: QPlainTextEdit, text: str, line: int = 0, col: int = 0) -> VimMode:
    editor.setPlainText(text)
    vim = VimMode(editor)
    put_cursor(editor, Pos(line, col))
    return vim


# --- search ---


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "pattern", "forward", "cursor"),
    [
        # all vim
        (T, 0, 0, "n", "foo", True, (0, 8)),
        (T, 0, 0, "3n", "foo", True, (2, 0)),
        (T, 0, 0, "4n", "foo", True, (0, 0)),
        (T, 0, 0, "N", "foo", True, (2, 0)),
        (T, 0, 0, "n", "foo", False, (2, 0)),
        (T, 1, 4, "N", "foo", True, (0, 8)),
        ("aaaa", 0, 0, "n", "aa", True, (0, 2)),
        ("xée", 0, 0, "n", "e", True, (0, 2)),
        ("\U0001f600a\U0001f600a", 0, 1, "n", "\U0001f600", True, (0, 2)),
        (T, 0, 0, "n", "o\nb", True, (0, 10)),
        ("ab\ncd", 0, 0, "n", "\nc", True, (0, 1)),
        (T, 0, 0, "n", "zzz", True, (0, 0)),
        # vim splits these into code points; here each is one character
        (FAMILY + "a" + FAMILY, 0, 0, "n", FAMILY, True, (0, 2)),
        (UA + UA + "x" + UA, 0, 0, "n", UA, True, (0, 1)),
        (UA + UA + "x" + UA, 0, 1, "n", UA + "x", True, (0, 1)),
        (UA + "x", 0, 0, "n", "\U0001f1e6", True, (0, 0)),  # half a flag never matches
    ],
)
def test_n_and_n(
    editor: QPlainTextEdit,
    text: str,
    line: int,
    col: int,
    keys: str,
    pattern: str,
    forward: bool,
    cursor: tuple[int, int],
) -> None:
    vim = start(editor, text, line, col)
    vim.set_search(pattern, forward)
    put_cursor(editor, Pos(line, col))
    send(editor, keys)
    assert cursor_of(editor) == Pos(*cursor)
    assert text_of(editor) == text


@pytest.mark.parametrize(
    ("line", "col", "pattern", "forward", "cursor"),
    [
        # all vim, as `/foo<CR>` or `?foo<CR>`
        (0, 0, "foo", True, (0, 8)),
        (0, 8, "foo", True, (1, 4)),
        (2, 0, "foo", True, (0, 0)),
        (0, 0, "foo", False, (2, 0)),
        (1, 4, "foo", False, (0, 8)),
        (0, 1, "zzz", True, (0, 1)),
        (0, 1, "", True, (0, 1)),
    ],
)
def test_set_search_jumps_to_the_next_match(
    editor: QPlainTextEdit,
    line: int,
    col: int,
    pattern: str,
    forward: bool,
    cursor: tuple[int, int],
) -> None:
    vim = start(editor, T, line, col)
    vim.set_search(pattern, forward)
    assert cursor_of(editor) == Pos(*cursor)


def test_set_search_moves_the_end_in_visual_mode(editor: QPlainTextEdit) -> None:
    vim = start(editor, T, 0, 1)
    send(editor, "v")
    vim.set_search("foo")
    assert vim.mode is Mode.VISUAL
    assert plain(editor.textCursor().selectedText()) == "oo bar f"


def test_set_search_doesnt_jump_in_insert_mode_or_when_off(editor: QPlainTextEdit) -> None:
    vim = start(editor, T, 0, 1)
    send(editor, "i")
    vim.set_search("foo")
    assert editor.textCursor().position() == 1
    send(editor, "<Esc>")
    vim.set_enabled(False)
    vim.set_search("foo")
    assert editor.textCursor().position() == 0
    vim.set_enabled(True)
    send(editor, "n")
    assert cursor_of(editor) == Pos(0, 8)


def test_no_search_text(editor: QPlainTextEdit) -> None:
    vim = start(editor, T, 0, 1)
    send(editor, "nN")
    assert cursor_of(editor) == Pos(0, 1)
    vim.set_search("")
    send(editor, "n")
    assert cursor_of(editor) == Pos(0, 1)


def test_line_breaks_in_the_search_text(editor: QPlainTextEdit) -> None:
    vim = start(editor, T)
    vim.set_search("o\r\nb")
    assert cursor_of(editor) == Pos(0, 10)
    send(editor, "gg0")
    vim.set_search("o b")
    assert cursor_of(editor) == Pos(0, 10)


def test_n_in_visual_mode_moves_the_end(editor: QPlainTextEdit) -> None:
    vim = start(editor, T, 0, 1)
    vim.set_search("foo")
    put_cursor(editor, Pos(0, 1))
    send(editor, "vn")
    assert vim.mode is Mode.VISUAL
    assert plain(editor.textCursor().selectedText()) == "oo bar f"
    send(editor, "Ny")
    assert vim_module._register == Register("fo", linewise=False)


def test_search_keys_call_the_hook(editor: QPlainTextEdit) -> None:
    vim = start(editor, T)
    send(editor, "/")  # no hook: nothing happens
    calls: list[bool] = []
    vim.search_hook = calls.append
    send(editor, "/?v/<Esc>2?")
    assert calls == [True, False, True, False]
    assert vim.mode is Mode.NORMAL
    assert cursor_of(editor) == Pos(0, 0)


# --- the Esc hook ---


class Window(QWidget):
    """An editor in a window that records the keys the editor passed on."""

    def __init__(self) -> None:
        super().__init__()
        self.editor = QPlainTextEdit(self)
        QVBoxLayout(self).addWidget(self.editor)
        self.passed_on: list[int] = []

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self.passed_on.append(event.key())


@pytest.fixture
def window(qapp: QApplication) -> Iterator[Window]:
    w = Window()
    w.show()
    yield w
    w.close()
    w.deleteLater()


def test_the_esc_hook_comes_first(window: Window) -> None:
    vim = start(window.editor, "abc")
    used = [True]
    calls: list[Mode] = []

    def hook() -> bool:
        calls.append(vim.mode)
        return used[0]

    vim.escape_hook = hook
    send(window.editor, "i<Esc>")
    assert vim.mode is Mode.INSERT  # the hook took it: still typing
    send(window.editor, "x")
    assert text_of(window.editor) == "xabc"
    used[0] = False
    send(window.editor, "<Esc>")
    assert vim.mode is Mode.NORMAL
    used[0] = True
    send(window.editor, "v<Esc>")
    assert vim.mode is Mode.VISUAL
    used[0] = False
    send(window.editor, "<Esc>")
    assert vim.mode is Mode.NORMAL
    used[0] = True
    send(window.editor, "2<Esc>l")  # the hook took Esc, so 2l: column 2, not 1
    assert cursor_of(window.editor) == Pos(0, 2)
    send(window.editor, "<Esc>")
    assert window.passed_on == []  # with nothing pending, the hook took it too
    used[0] = False
    send(window.editor, "<Esc>")
    assert window.passed_on == [Qt.Key.Key_Escape]
    assert calls == [Mode.INSERT, Mode.INSERT, Mode.VISUAL, Mode.VISUAL] + [Mode.NORMAL] * 3


# --- the command table ---


def test_every_command_has_a_handler(editor: QPlainTextEdit) -> None:
    vim = VimMode(editor)
    assert set(vim._normal_handlers) == {"move"} | set(OPERATORS) | set(NORMAL_ACTIONS)
    assert set(vim._visual_handlers) == {"move"} | set(VISUAL_ACTIONS)


# --- read-only ---


@pytest.mark.parametrize(
    "keys",
    ["x", "dd", "dw", "D", "cwab<Esc>", "ix<Esc>", "ox<Esc>", "J", "p", "P", "vd", "Vc", "vp"],
)
def test_a_read_only_editor_doesnt_edit(editor: QPlainTextEdit, keys: str) -> None:
    editor.setReadOnly(True)
    vim = start(editor, "abc def\nghi", 0, 1)
    vim_module._register = Register("reg", linewise=False)
    send(editor, keys)
    assert text_of(editor) == "abc def\nghi"
    assert vim.mode in (Mode.NORMAL, Mode.VISUAL, Mode.VISUAL_LINE)


def test_a_read_only_editor_moves_selects_and_yanks(editor: QPlainTextEdit) -> None:
    editor.setReadOnly(True)
    vim = start(editor, "abc def\nghi", 0, 1)
    send(editor, "w")
    assert cursor_of(editor) == Pos(0, 4)
    send(editor, "yw")
    assert vim_module._register == Register("def", linewise=False)
    send(editor, "vjy")  # j goes past the end of the short last line
    assert vim_module._register == Register("def\nghi", linewise=False)
    vim.set_search("gh")
    assert cursor_of(editor) == Pos(1, 0)
    send(editor, "u<C-r>")
    assert text_of(editor) == "abc def\nghi"


def test_a_read_only_editor_swaps_the_ends_of_the_selection(editor: QPlainTextEdit) -> None:
    # Visual mode's o isn't Normal mode's o, which opens a line
    editor.setReadOnly(True)
    vim = start(editor, "abc def", 0, 1)
    send(editor, "vllo")
    assert vim._pos(vim._lines()) == Pos(0, 1)
    send(editor, "y")
    assert vim_module._register == Register("bc ", linewise=False)


def test_a_read_only_editor_shows_vims_cursor(editor: QPlainTextEdit) -> None:
    editor.setReadOnly(True)
    vim = start(editor, "abc", 0, 1)
    assert vim._caret.isVisible()
    assert vim._caret.position == 1
    send(editor, "l")
    assert vim._caret.position == 2
    editor.setReadOnly(False)
    assert not vim._caret.isVisible()


def test_turning_read_only_on_in_insert_mode(editor: QPlainTextEdit) -> None:
    vim = start(editor, "abc", 0, 1)
    send(editor, "ix")
    editor.setReadOnly(True)
    assert vim.mode is Mode.NORMAL
    assert text_of(editor) == "axbc"
    send(editor, "u")  # read-only: no undo
    assert text_of(editor) == "axbc"
    editor.setReadOnly(False)
    send(editor, "u")
    assert text_of(editor) == "abc"


# --- the keyboard layout ---


def test_the_ukrainian_layout_types_vim_keys(editor: QPlainTextEdit) -> None:
    vim = start(editor, "abc def ghi")
    assert vim.layout_map is UKRAINIAN
    send(editor, "ц")  # w
    assert cursor_of(editor) == Pos(0, 4)
    send(editor, "вц")  # dw
    assert text_of(editor) == "abc ghi"
    send(editor, "шЖ<Esc>")  # i, then a typed Ж
    assert text_of(editor) == "abc Жghi"
    send(editor, "г")  # u
    assert text_of(editor) == "abc ghi"
    send(editor, "<C-к>")  # Ctrl+R
    assert text_of(editor) == "abc Жghi"
    send(editor, "0мдн")  # v l y
    assert vim.mode is Mode.NORMAL
    assert vim_module._register == Register("ab", linewise=False)


def test_the_layout_map_can_be_changed(editor: QPlainTextEdit) -> None:
    vim = start(editor, "abc def")
    vim.layout_map = None
    send(editor, "ц")
    assert cursor_of(editor) == Pos(0, 0)
    assert text_of(editor) == "abc def"
    vim.layout_map = {"ö": "w"}
    send(editor, "ö")
    assert cursor_of(editor) == Pos(0, 4)


def test_ctrl_and_the_ukrainian_layout_win_over_app_shortcuts(qapp: QApplication) -> None:
    window = Window()
    fired: list[str] = []
    shortcut = QShortcut(QKeySequence("Ctrl+R"), window)
    shortcut.activated.connect(lambda: fired.append("Ctrl+R"))
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    window.editor.setFocus()
    vim = start(window.editor, "abc")
    send(window.editor, "x<C-к>")
    assert fired == []
    assert vim.mode is Mode.NORMAL
    window.close()
    window.deleteLater()


def test_insert_mode_types_cyrillic(editor: QPlainTextEdit) -> None:
    start(editor, "")
    send(editor, "i")
    type_text(editor, "ц")
    send(editor, "<Esc>")
    assert text_of(editor) == "ц"


def test_ctrl_and_the_key_of_the_bracket_is_esc(editor: QPlainTextEdit) -> None:
    vim = start(editor, "abc")
    send(editor, "i")
    QTest.keyClick(editor, Qt.Key(0x445), Qt.KeyboardModifier.ControlModifier)  # Ctrl+х
    assert vim.mode is Mode.NORMAL
    send(editor, "v")
    QTest.keyClick(editor, Qt.Key(0x445), Qt.KeyboardModifier.ControlModifier)
    assert vim.mode is Mode.NORMAL
    vim.layout_map = None
    send(editor, "i")
    QTest.keyClick(editor, Qt.Key(0x445), Qt.KeyboardModifier.ControlModifier)
    assert vim.mode is Mode.INSERT
