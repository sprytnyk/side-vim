"""r on a real QPlainTextEdit, where it differs from vim or vim can't be recorded.

The cases in tests/cases/replace.json check the rest against vim 9.1. Expected results
marked "vim" here were checked by typing into vim 9.1 (`vim -u NONE`) in a terminal.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QInputMethodEvent, QKeyEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QVBoxLayout, QWidget
from qtkeys import cursor_of, send, start_vim, text_of

import side_vim.vim as vim_module
from side_vim import Mode
from side_vim.edits import Register
from side_vim.keys import control_modifier
from side_vim.motions import Pos

pytestmark = pytest.mark.usefixtures("empty_register")

FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
UA = "\U0001f1fa\U0001f1e6"
E_ACUTE = "e\u0301"


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected", "cursor"),
    [
        # Joined emoji and flags are one character; vim splits them
        (f"a{FAMILY}b", 0, 1, "rX", "aXb", (0, 1)),
        (f"{UA}{UA}c", 0, 0, "2rX", "XXc", (0, 1)),
        ("abc", 0, 0, f"2r{UA}", f"{UA}{UA}c", (0, 1)),
        ("abc", 0, 1, f"r{FAMILY}", f"a{FAMILY}c", (0, 1)),
        (f"abc\nx{UA}z", 0, 1, "r<C-e>", f"a{UA}c\nx{UA}z", (0, 1)),
        (f"a{UA}b", 0, 0, "vlrX", "XXb", (0, 0)),
        # Ctrl+E and Ctrl+Y copy an accent made of two code points whole; vim copies the e
        (f"a{E_ACUTE}c\nxyz", 1, 1, "r<C-y>", f"a{E_ACUTE}c\nx{E_ACUTE}z", (1, 1)),
        # vim keeps a NUL as a line feed, so its recorded text can't tell them apart
        ("abc def", 0, 3, "r<C-v>000", "abc\x00def", (0, 3)),
        ("abc def", 0, 3, "r<C-v><C-j>", "abc\x00def", (0, 3)),
        ("abc def", 0, 1, "vlr<C-j>", "a\x00\x00 def", (0, 1)),
        # vim's recorder can't send Ctrl+\
        ("abc def", 0, 3, "r<C-\\>", "abc\x1cdef", (0, 3)),
        # Qt turns a carriage return into a line break, so r can't put one in
        ("abc def", 0, 3, "r<C-v><CR>", "abc def", (0, 3)),
        ("abc def", 0, 3, "r<C-v>013", "abc def", (0, 3)),
        ("abc def", 0, 3, "r<C-k>e<C-v><CR>", "abc def", (0, 3)),
        # vim: Ctrl+C cancels r in Normal mode, and l moves on. vim's :normal reads Ctrl+C
        # as a character, so the recorder can't check this
        ("abc def", 0, 3, "r<C-c>l", "abc def", (0, 4)),
        ("abc def", 0, 3, "3r<C-c>", "abc def", (0, 3)),
        ("abc def", 0, 3, "r<C-k><C-c>l", "abc def", (0, 4)),
        ("abc def", 0, 3, "r<C-k>e<C-c>l", "abc def", (0, 4)),
    ],
)
def test_r(
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
    assert vim_module._register == Register()


def test_visual_r_with_a_carriage_return_keeps_the_selection(editor: QPlainTextEdit) -> None:
    """vim puts in "\\r" characters there, which Qt can't hold. Like a cancelled r, the
    selection stays."""
    vim = start_vim(editor, "abc def", 0, 1)
    send(editor, "vlr<CR>")
    assert text_of(editor) == "abc def"
    assert vim.mode is Mode.VISUAL
    send(editor, "d")
    assert text_of(editor) == "a def"


def test_r_on_the_ukrainian_layout(editor: QPlainTextEdit) -> None:
    """к is r, but the character after it is text: ц stays ц, not w. Ctrl keys still map,
    so Ctrl+м is Ctrl+V and Ctrl+х is Esc."""
    vim = start_vim(editor, "abc def")
    send(editor, "кц")
    assert text_of(editor) == "цbc def"
    send(editor, "ц2кЇ")  # w, then 2r
    assert text_of(editor) == "цbc ЇЇf"
    assert cursor_of(editor) == Pos(0, 5)
    send(editor, "0к<C-м>065")
    assert text_of(editor) == "Abc ЇЇf"
    send(editor, "к<C-х>д")  # cancelled, then l
    assert text_of(editor) == "Abc ЇЇf"
    assert cursor_of(editor) == Pos(0, 1)
    vim.layout_map = None
    send(editor, "кц")  # not commands now
    assert text_of(editor) == "Abc ЇЇf"


def commit(editor: QPlainTextEdit, text: str) -> None:
    """Text from an input method, the way IBus or Fcitx send it."""
    event = QInputMethodEvent()
    event.setCommitString(text)
    QApplication.sendEvent(editor, event)


def test_input_method_text_after_r(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc def")
    commit(editor, "к")
    commit(editor, "ц")
    assert text_of(editor) == "цbc def"
    commit(editor, "lкї")  # one commit: l, r, then the text ї
    assert text_of(editor) == "цїc def"
    commit(editor, "r")
    commit(editor, UA)
    assert text_of(editor) == f"ц{UA}c def"
    commit(editor, f"wr{E_ACUTE}")
    assert text_of(editor) == f"ц{UA}{E_ACUTE} def"
    assert vim.mode is Mode.NORMAL


def test_pending_signal_for_r(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "abc def")
    pending: list[str] = []
    vim.pending_changed.connect(pending.append)
    send(editor, "3r<C-v>06")
    assert pending == ["3", "3r", "3r^V", "3r^V0", "3r^V06"]
    send(editor, "5")
    assert pending[-1] == ""
    assert text_of(editor) == "AAA def"  # 065
    send(editor, "r<C-k>e")
    assert pending[-2:] == ["r^K", "r^Ke"]
    send(editor, ":")
    assert pending[-1] == ""
    send(editor, "r<Esc>")
    assert pending[-2:] == ["r", ""]
    assert text_of(editor) == "AAë def"


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


@pytest.fixture
def window(qapp: QApplication) -> Iterator[Window]:
    w = Window()
    w.show()
    yield w
    w.close()
    w.deleteLater()


def test_esc_after_r_stays_with_vim(window: Window) -> None:
    vim = start_vim(window.editor, "abc def")
    hook_calls: list[None] = []
    vim.escape_hook = lambda: bool(hook_calls.append(None))
    send(window.editor, "r<Esc>r<C-v><Esc>")
    assert Qt.Key.Key_Escape not in window.passed_on
    assert text_of(window.editor) == "\x1bbc def"
    assert len(hook_calls) == 2  # the hook still sees every Esc first
    send(window.editor, "<Esc>")  # nothing pending: the app's
    assert window.passed_on.count(Qt.Key.Key_Escape) == 1


def test_r_claims_ctrl_keys_before_app_shortcuts(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc")

    def claimed(key: Qt.Key) -> bool:
        event = QKeyEvent(QEvent.Type.ShortcutOverride, key, control_modifier(), "")
        event.ignore()
        QApplication.sendEvent(editor, event)
        return event.isAccepted()

    assert not claimed(Qt.Key.Key_S)  # an app shortcut, say Save
    send(editor, "r")
    assert claimed(Qt.Key.Key_S)
    send(editor, "<C-v>")
    assert claimed(Qt.Key.Key_S)
    send(editor, "<C-s>")
    assert text_of(editor) == "\x13bc"
    assert not claimed(Qt.Key.Key_S)
