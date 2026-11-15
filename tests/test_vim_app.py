"""What the app sets up: the search and Esc hooks, set_search with n and N, read-only
editors, and the keyboard layout map. Cases marked "vim" were checked against vim 9.1
(`vim -u NONE`)."""

from collections.abc import Iterator

import pytest
import shiboken6
from PySide6.QtCore import QEvent, QKeyCombination, QObject, Qt
from PySide6.QtGui import (
    QFocusEvent,
    QFont,
    QKeyEvent,
    QKeySequence,
    QPaintEvent,
    QRegion,
    QShortcut,
    QSyntaxHighlighter,
    QTextDocument,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QPlainTextDocumentLayout,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)
from qtkeys import cursor_of, plain, put_cursor, send, start_vim, text_of, type_text

import side_vim.vim as vim_module
from side_vim import UKRAINIAN, Mode, VimMode
from side_vim.edits import Register
from side_vim.keys import control_modifier
from side_vim.motions import Pos
from side_vim.parser import NORMAL_ACTIONS, OPERATORS, VISUAL_ACTIONS

pytestmark = pytest.mark.usefixtures("empty_register")

T = "foo bar foo\nbaz foo\nfoo"
FAMILY = "\U0001f468‍\U0001f469‍\U0001f467"
UA = "\U0001f1fa\U0001f1e6"


@pytest.fixture
def editor(qapp: QApplication) -> Iterator[QPlainTextEdit]:
    e = QPlainTextEdit()
    e.resize(600, 300)
    e.show()
    yield e
    e.close()
    e.deleteLater()


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "pattern", "forward", "cursor"),
    [
        ("👨\u200d👩\u200d👧a👨\u200d👩\u200d👧", 0, 0, "n", "👨\u200d👩\u200d👧", True, [0, 2]),
        ("🇺🇦🇺🇦x🇺🇦", 0, 0, "n", "🇺🇦", True, [0, 1]),
        ("🇺🇦🇺🇦x🇺🇦", 0, 1, "n", "🇺🇦x", True, [0, 1]),
        ("🇺🇦x", 0, 0, "n", "🇦", True, [0, 0]),
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
    vim = start_vim(editor, text, line, col)
    vim.set_search(pattern, forward)
    put_cursor(editor, Pos(line, col))
    send(editor, keys)
    assert cursor_of(editor) == Pos(*cursor)
    assert text_of(editor) == text


def test_set_search_moves_the_end_in_visual_mode(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T, 0, 1)
    send(editor, "v")
    vim.set_search("foo")
    assert vim.mode is Mode.VISUAL
    assert plain(editor.textCursor().selectedText()) == "oo bar f"


def test_set_search_doesnt_jump_in_insert_mode_or_when_off(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T, 0, 1)
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
    vim = start_vim(editor, T, 0, 1)
    send(editor, "nN")
    assert cursor_of(editor) == Pos(0, 1)
    vim.set_search("")
    send(editor, "n")
    assert cursor_of(editor) == Pos(0, 1)


def test_line_breaks_in_the_search_text(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    vim.set_search("o\r\nb")
    assert cursor_of(editor) == Pos(0, 10)
    send(editor, "gg0")
    vim.set_search("o b")
    assert cursor_of(editor) == Pos(0, 10)


def test_n_in_visual_mode_moves_the_end(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T, 0, 1)
    vim.set_search("foo")
    put_cursor(editor, Pos(0, 1))
    send(editor, "vn")
    assert vim.mode is Mode.VISUAL
    assert plain(editor.textCursor().selectedText()) == "oo bar f"
    send(editor, "Ny")
    assert vim_module._register == Register("fo", linewise=False)


def test_search_keys_call_the_hook(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    send(editor, "/")  # no hook: nothing happens
    calls: list[bool] = []
    vim.search_hook = calls.append
    send(editor, "/?v/<Esc>2?")
    assert calls == [True, False, True, False]
    assert vim.mode is Mode.NORMAL
    assert cursor_of(editor) == Pos(0, 0)


def test_ctrl_w_and_a_key_call_the_window_hook(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    send(editor, "<C-w>l")  # no hook: nothing happens
    calls: list[str] = []
    vim.window_hook = calls.append
    pending: list[str] = []
    vim.pending_changed.connect(pending.append)
    send(editor, "<C-w>h<C-w><C-l>2<C-w>j<C-w><Esc>")
    assert calls == ["h", "l", "j"]  # Esc drops a Ctrl+W
    assert pending == ["^W", "", "^W", "", "2", "2^W", "", "^W", ""]
    assert cursor_of(editor) == Pos(0, 0)  # h and j went to the hook, not the cursor
    send(editor, "i<C-w>")
    assert calls == ["h", "l", "j"]  # Insert mode: not vim's


def test_spelling_commands_call_the_spell_hook(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, T)
    send(editor, "z=")  # no hook: nothing happens
    calls: list[tuple[str, int | None]] = []
    vim.spell_hook = lambda name, count: calls.append((name, count))
    send(editor, "z=2]s[szgzGzx")
    assert calls == [("z=", None), ("]s", 2), ("[s", None), ("zg", None), ("zG", None)]
    assert cursor_of(editor) == Pos(0, 0)
    editor.setReadOnly(True)
    send(editor, "z=]s")  # z= would change the text
    assert calls[5:] == [("]s", None)]
    editor.setReadOnly(False)
    send(editor, "iz=")
    assert len(calls) == 6  # Insert mode: typed


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
    vim = start_vim(window.editor, "abc")
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


def test_every_command_has_a_handler(editor: QPlainTextEdit) -> None:
    vim = VimMode(editor)
    assert set(vim._normal_handlers) == {"move"} | set(OPERATORS) | set(NORMAL_ACTIONS)
    assert set(vim._visual_handlers) == {"move"} | set(VISUAL_ACTIONS)


@pytest.mark.parametrize(
    "keys",
    [
        "x",
        "dd",
        "dw",
        "D",
        "cwab<Esc>",
        "ix<Esc>",
        "ox<Esc>",
        "J",
        "p",
        "P",
        "vd",
        "Vc",
        "vp",
        "rX",
        "3r<CR>",
        "r<C-e>",
        "vrX",
        "Vr<Tab>",
        "~",
        "3~",
        "v~",
        "V~",
    ],
)
def test_a_read_only_editor_doesnt_edit(editor: QPlainTextEdit, keys: str) -> None:
    editor.setReadOnly(True)
    vim = start_vim(editor, "abc def\nghi", 0, 1)
    vim_module._register = Register("reg", linewise=False)
    send(editor, keys)
    assert text_of(editor) == "abc def\nghi"
    assert vim.mode in (Mode.NORMAL, Mode.VISUAL, Mode.VISUAL_LINE)


def test_a_read_only_editor_moves_selects_and_yanks(editor: QPlainTextEdit) -> None:
    editor.setReadOnly(True)
    vim = start_vim(editor, "abc def\nghi", 0, 1)
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
    start_vim(editor, "abc def", 0, 1)
    send(editor, "vllo")
    assert cursor_of(editor) == Pos(0, 1)
    send(editor, "y")
    assert vim_module._register == Register("bc ", linewise=False)


def test_a_read_only_editor_shows_vims_cursor(editor: QPlainTextEdit) -> None:
    editor.setReadOnly(True)
    vim = start_vim(editor, "abc", 0, 1)
    assert vim._caret.isVisible()
    assert vim._caret.position == 1
    send(editor, "l")
    assert vim._caret.position == 2
    editor.setReadOnly(False)
    assert not vim._caret.isVisible()


def test_turning_read_only_on_in_insert_mode(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc", 0, 1)
    send(editor, "ix")
    editor.setReadOnly(True)
    assert vim.mode is Mode.NORMAL
    assert text_of(editor) == "axbc"
    send(editor, "u")  # read-only: no undo
    assert text_of(editor) == "axbc"
    editor.setReadOnly(False)
    send(editor, "u")
    assert text_of(editor) == "abc"


def test_the_ukrainian_layout_types_vim_keys(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc def ghi")
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
    vim = start_vim(editor, "abc def")
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
    shortcut = QShortcut(QKeySequence(QKeyCombination(control_modifier(), Qt.Key.Key_R)), window)
    shortcut.activated.connect(lambda: fired.append("Ctrl+R"))
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    window.editor.setFocus()
    vim = start_vim(window.editor, "abc")
    send(window.editor, "x<C-к>")
    assert fired == []
    assert vim.mode is Mode.NORMAL
    window.close()
    window.deleteLater()


def test_the_key_after_ctrl_w_wins_over_app_shortcuts(qapp: QApplication) -> None:
    window = Window()
    fired: list[str] = []
    shortcut = QShortcut(QKeySequence(QKeyCombination(control_modifier(), Qt.Key.Key_L)), window)
    shortcut.activated.connect(lambda: fired.append("Ctrl+L"))
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    window.editor.setFocus()
    vim = start_vim(window.editor, "abc")
    calls: list[str] = []
    vim.window_hook = calls.append
    send(window.editor, "<C-w><C-l>")
    assert (calls, fired) == (["l"], [])
    send(window.editor, "<C-l>")  # on its own it's the app's
    assert fired == ["Ctrl+L"]
    window.close()
    window.deleteLater()


@pytest.mark.parametrize(
    ("reason", "dropped"),
    [
        (Qt.FocusReason.MouseFocusReason, True),
        (Qt.FocusReason.TabFocusReason, True),
        (Qt.FocusReason.OtherFocusReason, True),
        (Qt.FocusReason.ActiveWindowFocusReason, False),
        (Qt.FocusReason.PopupFocusReason, False),
    ],
)
def test_moving_the_focus_to_another_widget_drops_pending_keys(
    editor: QPlainTextEdit, reason: Qt.FocusReason, dropped: bool
) -> None:
    vim = start_vim(editor, "abc")
    pending: list[str] = []
    vim.pending_changed.connect(pending.append)
    send(editor, "2d")
    QApplication.sendEvent(editor, QFocusEvent(QEvent.Type.FocusOut, reason))
    assert pending == (["2", "2d", ""] if dropped else ["2", "2d"])
    send(editor, "<Esc>r")
    QApplication.sendEvent(editor, QFocusEvent(QEvent.Type.FocusOut, reason))
    send(editor, "l")  # dropped: a motion. Kept: r's character
    expected = ("abc", Pos(0, 1)) if dropped else ("lbc", Pos(0, 0))
    assert (text_of(editor), cursor_of(editor)) == expected


def test_insert_mode_types_cyrillic(editor: QPlainTextEdit) -> None:
    start_vim(editor, "")
    send(editor, "i")
    type_text(editor, "ц")
    send(editor, "<Esc>")
    assert text_of(editor) == "ц"


def test_ctrl_and_the_key_of_the_bracket_is_esc(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc")
    send(editor, "i")
    send(editor, "<C-х>")  # Ctrl+[
    assert vim.mode is Mode.NORMAL
    send(editor, "v")
    send(editor, "<C-х>")
    assert vim.mode is Mode.NORMAL
    vim.layout_map = None
    send(editor, "i")
    send(editor, "<C-х>")
    assert vim.mode is Mode.INSERT


class Highlighter(QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:  # noqa: N802
        pass


@pytest.mark.parametrize("shared", [True, False])
def test_an_editor_can_go_away_in_insert_mode(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, shared: bool
) -> None:
    """When the editor goes, on quit say, its highlighter lets go of the document, and Qt
    reports the whole text as changed to the insert session still listening. The editor
    is half gone by then. An app with tabs keeps the document (shared), or it goes too."""
    errors: list[BaseException] = []
    monkeypatch.setattr("sys.excepthook", lambda kind, error, trace: errors.append(error))
    e = QPlainTextEdit()
    document = QTextDocument() if shared else e.document()
    if shared:
        document.setDocumentLayout(QPlainTextDocumentLayout(document))
        e.setDocument(document)
    document.setPlainText("abc\ndef")
    Highlighter(document).setParent(e)  # the editor's, made before vim, so it goes first
    VimMode(e)
    send(e, "GA")
    shiboken6.delete(e)
    assert errors == []
    if shared:
        assert document.toPlainText() == "abc\ndef"


@pytest.mark.parametrize("change", ["resize", "font"])
@pytest.mark.parametrize("keys", ["", "v"])
def test_an_editor_can_go_away_right_after_a_resize_or_font_change(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, change: str, keys: str
) -> None:
    """A resize or a font change makes vim schedule a call for later. When the app
    deletes the editor before that call runs, Qt skips the call."""
    errors: list[BaseException] = []
    monkeypatch.setattr("sys.excepthook", lambda kind, error, trace: errors.append(error))
    e = QPlainTextEdit()
    e.resize(300, 200)
    e.show()
    start_vim(e, "abc\ndef")
    send(e, keys)
    if change == "resize":
        e.resize(400, 250)
    else:
        font = QFont(e.font())
        font.setPointSize(font.pointSize() + 6)
        e.setFont(font)
    e.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    QTest.qWait(10)
    assert errors == []


class Paints(QObject):
    """The parts of a widget it paints."""

    def __init__(self) -> None:
        super().__init__()
        self.region = QRegion()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if isinstance(event, QPaintEvent):
            self.region += event.region()
        return False


@pytest.mark.parametrize("key", ["i", "a"])
def test_the_whole_block_cursor_goes_in_insert_mode(
    qapp: QApplication, editor: QPlainTextEdit, key: str
) -> None:
    """Qt repaints only the new cursor's area when the cursor's width changes, which left
    the rest of the block on screen next to Insert mode's line, as in |]."""
    font = QFont(editor.font())
    font.setPointSize(28)  # a W wider than the margin Qt repaints around the cursor
    editor.setFont(font)
    start_vim(editor, "Wi")
    qapp.processEvents()
    block = editor.cursorRect()
    paints = Paints()
    editor.viewport().installEventFilter(paints)
    send(editor, key)
    qapp.processEvents()
    editor.viewport().removeEventFilter(paints)
    assert (QRegion(block) - paints.region).isEmpty()
