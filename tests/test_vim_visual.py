"""Visual and Visual Line mode on a real QPlainTextEdit.

Expected results marked "vim" were checked against vim 9.1 (`vim -u NONE`, with
'nojoinspaces'): the text, the cursor and the unnamed register. In keys, | only splits
commands: vim's `:normal` makes one undo step of everything it runs, so the vim check
ran each part on its own.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QVBoxLayout, QWidget
from qtkeys import cursor_of, plain, put_cursor, send, text_of

from side_vim import Mode, VimMode
from side_vim.caret import char_width
from side_vim.edits import Register
from side_vim.motions import Pos
from side_vim.text import Lines
from side_vim.vim import _Shared

T = "ab cd ef\n  gh ij\nkl"
W = "foo bar\n\n  baz qux\nend"
S = "\U0001f600x \u65e5\u672c\u8a9e\ne\u0301a b\n\tc"
FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
UA = "\U0001f1fa\U0001f1e6"


@pytest.fixture(autouse=True)
def empty_register() -> Iterator[None]:
    _Shared.register = Register()
    yield
    _Shared.register = Register()


@pytest.fixture
def editor(qapp: QApplication) -> Iterator[QPlainTextEdit]:
    e = QPlainTextEdit()
    e.setTabStopDistance(e.fontMetrics().horizontalAdvance(" ") * 8)
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


def run(editor: QPlainTextEdit, keys: str) -> None:
    send(editor, keys.replace("|", ""))


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected", "cursor", "register"),
    [
        # all checked against vim
        # yank: what's selected, where the cursor goes
        (T, 0, 1, "vy", T, (0, 1), ("b", False)),
        (T, 0, 1, "vly", T, (0, 1), ("b ", False)),
        (T, 0, 1, "v3ly", T, (0, 1), ("b cd", False)),
        (T, 0, 4, "vhhy", T, (0, 2), (" cd", False)),
        (T, 0, 2, "v5hy", T, (0, 0), ("ab ", False)),
        (T, 0, 1, "vey", T, (0, 1), ("b cd", False)),
        (T, 0, 4, "vby", T, (0, 3), ("cd", False)),
        (T, 0, 1, "vwy", T, (0, 1), ("b c", False)),
        (T, 0, 7, "vwy", T, (0, 7), ("f\n  g", False)),
        (T, 1, 6, "vwy", T, (1, 6), ("j\nk", False)),
        (T, 0, 1, "vEy", T, (0, 1), ("b cd", False)),
        (T, 0, 1, "vWy", T, (0, 1), ("b c", False)),
        (T, 1, 5, "vBy", T, (1, 2), ("gh i", False)),
        (T, 0, 3, "v$y", T, (0, 3), ("cd ef\n", False)),
        (T, 1, 0, "v$y", T, (1, 0), ("  gh ij\n", False)),
        (T, 2, 0, "v$y", T, (2, 0), ("kl", False)),
        (T, 1, 4, "v0y", T, (1, 0), ("  gh ", False)),
        (T, 1, 4, "v^y", T, (1, 2), ("gh ", False)),
        (T, 0, 4, "vjy", T, (0, 4), ("d ef\n  gh ", False)),
        (T, 1, 4, "vky", T, (0, 4), ("d ef\n  gh ", False)),
        (T, 0, 7, "vjjy", T, (0, 7), ("f\n  gh ij\nkl", False)),
        (T, 1, 6, "vjy", T, (1, 6), ("j\nkl", False)),
        (T, 1, 6, "vjky", T, (1, 6), ("j", False)),
        (T, 1, 4, "vGy", T, (1, 4), (" ij\nk", False)),
        (T, 1, 4, "vggy", T, (0, 0), ("ab cd ef\n  gh ", False)),
        (T, 0, 5, "v$jy", T, (0, 5), (" ef\n  gh ij\n", False)),
        (T, 0, 0, "v$jy", T, (0, 0), ("ab cd ef\n  gh ij\n", False)),
        (T, 0, 2, "v2jy", T, (0, 2), (" cd ef\n  gh ij\nkl", False)),
        (T, 2, 1, "v2ky", T, (0, 1), ("b cd ef\n  gh ij\nkl", False)),
        (T, 1, 3, "v3Gy", T, (1, 3), ("h ij\nk", False)),
        (T, 1, 3, "v1Gy", T, (0, 0), ("ab cd ef\n  gh", False)),
        (T, 0, 1, "vllo|y", T, (0, 1), ("b c", False)),
        (T, 0, 1, "vllohy", T, (0, 0), ("ab c", False)),
        (T, 0, 3, "v$oy", T, (0, 3), ("cd ef\n", False)),
        (T, 0, 4, "vjohy", T, (0, 3), ("cd ef\n  gh ", False)),
        (W, 0, 0, "vwy", W, (0, 0), ("foo b", False)),
        (W, 0, 0, "v2wy", W, (0, 0), ("foo bar\n\n", False)),
        (W, 0, 4, "vjy", W, (0, 4), ("bar\n\n", False)),
        (W, 1, 0, "vy", W, (1, 0), ("\n", False)),
        (W, 1, 0, "vjy", W, (1, 0), ("\n ", False)),
        (W, 2, 4, "vkky", W, (0, 4), ("bar\n\n  baz", False)),
        (W, 3, 2, "vy", W, (3, 2), ("d", False)),
        (W, 2, 2, "v$y", W, (2, 2), ("baz qux\n", False)),
        # Visual Line
        (T, 1, 3, "Vy", T, (1, 0), ("  gh ij\n", True)),
        (T, 1, 3, "Vky", T, (0, 3), ("ab cd ef\n  gh ij\n", True)),
        (T, 0, 3, "Vjy", T, (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 1, 3, "Vhy", T, (1, 0), ("  gh ij\n", True)),
        (T, 1, 3, "Vly", T, (1, 0), ("  gh ij\n", True)),
        (T, 1, 3, "Vkoy", T, (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 1, 3, "Vjoy", T, (1, 3), ("  gh ij\nkl\n", True)),
        (T, 1, 4, "VGy", T, (1, 0), ("  gh ij\nkl\n", True)),
        (T, 1, 4, "Vggy", T, (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 0, 0, "V2jy", T, (0, 0), ("ab cd ef\n  gh ij\nkl\n", True)),
        (T, 0, 2, "vjVy", T, (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 0, 2, "Vjvy", T, (0, 2), (" cd ef\n  g", False)),
        (T, 1, 2, "Vkvy", T, (0, 2), (" cd ef\n  g", False)),
        # mode switches and Esc
        (T, 0, 0, "vV<Esc>|x", "b cd ef\n  gh ij\nkl", (0, 0), ("a", False)),
        (T, 0, 2, "Vv<Esc>|x", "abcd ef\n  gh ij\nkl", (0, 2), (" ", False)),
        (T, 0, 2, "VV<Esc>|x", "abcd ef\n  gh ij\nkl", (0, 2), (" ", False)),
        (T, 0, 2, "vv|x", "abcd ef\n  gh ij\nkl", (0, 2), (" ", False)),
        (T, 0, 1, "vll<Esc>|x", "ab d ef\n  gh ij\nkl", (0, 3), ("c", False)),
        (T, 0, 1, "v$<Esc>|x", "ab cd e\n  gh ij\nkl", (0, 6), ("f", False)),
        (T, 0, 1, "vjl<Esc>|x", "ab cd ef\n  h ij\nkl", (1, 2), ("g", False)),
        (T, 1, 3, "Vk<Esc>|x", "ab d ef\n  gh ij\nkl", (0, 3), ("c", False)),
        (T, 0, 1, "vl<Esc>|j|x", "ab cd ef\n  h ij\nkl", (1, 2), ("g", False)),
        (T, 0, 1, "v$<Esc>|j|x", "ab cd ef\n  gh i\nkl", (1, 5), ("j", False)),
        (T, 0, 1, "vj$<Esc>|k|x", "ab cd f\n  gh ij\nkl", (0, 6), ("e", False)),
        # delete
        (T, 0, 1, "vd", "a cd ef\n  gh ij\nkl", (0, 1), ("b", False)),
        (T, 0, 1, "vld", "acd ef\n  gh ij\nkl", (0, 1), ("b ", False)),
        (T, 0, 1, "vx", "a cd ef\n  gh ij\nkl", (0, 1), ("b", False)),
        (T, 0, 1, "vlx", "acd ef\n  gh ij\nkl", (0, 1), ("b ", False)),
        (T, 0, 3, "v$d", "ab   gh ij\nkl", (0, 3), ("cd ef\n", False)),
        (T, 1, 1, "v$d", "ab cd ef\n kl", (1, 1), (" gh ij\n", False)),
        (T, 2, 1, "v$d", "ab cd ef\n  gh ij\nk", (2, 0), ("l", False)),
        (T, 0, 2, "vjd", "abh ij\nkl", (0, 2), (" cd ef\n  g", False)),
        (T, 0, 2, "vjx", "abh ij\nkl", (0, 2), (" cd ef\n  g", False)),
        (T, 1, 4, "vkd", "ab cij\nkl", (0, 4), ("d ef\n  gh ", False)),
        (T, 2, 1, "vbd", "ab cd ef\n  gh ij\n", (2, 0), ("kl", False)),
        (T, 0, 4, "vwd", "ab cf\n  gh ij\nkl", (0, 4), ("d e", False)),
        (T, 0, 0, "v$jd", "kl", (0, 0), ("ab cd ef\n  gh ij\n", False)),
        (T, 0, 0, "vGd", "l", (0, 0), ("ab cd ef\n  gh ij\nk", False)),
        (T, 2, 1, "vggd", "", (0, 0), ("ab cd ef\n  gh ij\nkl", False)),
        (W, 1, 0, "vd", "foo bar\n  baz qux\nend", (1, 0), ("\n", False)),
        (W, 0, 7, "vd", "foo ba\n\n  baz qux\nend", (0, 5), ("r", False)),
        (W, 0, 3, "vjd", "foo  baz qux\nend", (0, 3), (" bar\n\n", False)),
        (T, 0, 3, "Vjd", "kl", (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 1, 3, "Vjd", "ab cd ef", (0, 0), ("  gh ij\nkl\n", True)),
        (T, 2, 1, "Vd", "ab cd ef\n  gh ij", (1, 2), ("kl\n", True)),
        (T, 1, 1, "Vd", "ab cd ef\nkl", (1, 0), ("  gh ij\n", True)),
        (T, 0, 1, "Vd", "  gh ij\nkl", (0, 2), ("ab cd ef\n", True)),
        (T, 0, 0, "VGd", "", (0, 0), ("ab cd ef\n  gh ij\nkl\n", True)),
        (T, 1, 4, "Vkd", "kl", (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 1, 4, "Vx", "ab cd ef\nkl", (1, 0), ("  gh ij\n", True)),
        ("", 0, 0, "vy", "", (0, 0), ("", False)),
        ("", 0, 0, "vd", "", (0, 0), ("", False)),
        ("", 0, 0, "Vd", "", (0, 0), ("\n", True)),
        ("", 0, 0, "Vy", "", (0, 0), ("\n", True)),
        ("a\n\n", 2, 0, "vd", "a\n\n", (2, 0), ("", False)),
        ("a\n\n", 2, 0, "vy", "a\n\n", (2, 0), ("", False)),
        ("a\n\nb", 1, 0, "vy", "a\n\nb", (1, 0), ("\n", False)),
        ("a\n\nb", 1, 0, "vd", "a\nb", (1, 0), ("\n", False)),
        # change
        (T, 0, 1, "vlcX<Esc>", "aXcd ef\n  gh ij\nkl", (0, 1), ("b ", False)),
        (T, 0, 3, "v$cX<Esc>", "ab X  gh ij\nkl", (0, 3), ("cd ef\n", False)),
        (T, 0, 3, "v$jcX<Esc>", "ab Xkl", (0, 3), ("cd ef\n  gh ij\n", False)),
        (T, 0, 3, "vjcX<Esc>", "ab X ij\nkl", (0, 3), ("cd ef\n  gh", False)),
        (T, 1, 4, "vkcX<Esc>", "ab cXij\nkl", (0, 4), ("d ef\n  gh ", False)),
        (T, 0, 1, "vcXY<Esc>", "aXY cd ef\n  gh ij\nkl", (0, 2), ("b", False)),
        (T, 2, 1, "vbcX<Esc>", "ab cd ef\n  gh ij\nX", (2, 0), ("kl", False)),
        (T, 0, 1, "VcX<Esc>", "X\n  gh ij\nkl", (0, 0), ("ab cd ef\n", True)),
        (T, 0, 1, "VjcX<Esc>", "X\nkl", (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 1, 1, "VjcX<Esc>", "ab cd ef\nX", (1, 0), ("  gh ij\nkl\n", True)),
        (T, 1, 1, "VkcX<Esc>", "X\nkl", (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 0, 0, "VGcX<Esc>", "X", (0, 0), ("ab cd ef\n  gh ij\nkl\n", True)),
        ("a\n\n", 2, 0, "vcX<Esc>", "a\n\nX", (2, 0), ("", False)),
        # p over a selection
        (T, 0, 0, "yw|wvlp", "ab ab  ef\n  gh ij\nkl", (0, 5), ("cd", False)),
        (T, 0, 0, "yw|wvl2p", "ab ab ab  ef\n  gh ij\nkl", (0, 8), ("cd", False)),
        (T, 0, 0, "yw|wvjp", "ab ab  ij\nkl", (0, 5), ("cd ef\n  gh", False)),
        (T, 0, 0, "yl|$vp", "ab cd ea\n  gh ij\nkl", (0, 7), ("f", False)),
        (T, 0, 3, "yl|v$p", "ab c  gh ij\nkl", (0, 3), ("cd ef\n", False)),
        (T, 0, 0, "yy|wvlp", "ab \nab cd ef\n ef\n  gh ij\nkl", (1, 0), ("cd", False)),
        (T, 0, 0, "yy|wv$p", "ab \nab cd ef\n  gh ij\nkl", (1, 0), ("cd ef\n", False)),
        (T, 0, 0, "yy|wvjp", "ab \nab cd ef\n ij\nkl", (1, 0), ("cd ef\n  gh", False)),
        (T, 0, 0, "yy|wvl2p", "ab \nab cd ef\nab cd ef\n ef\n  gh ij\nkl", (1, 0), ("cd", False)),
        (T, 2, 0, "yy|vp", "ab cd ef\n  gh ij\n\nkl\nl", (3, 0), ("k", False)),
        (T, 2, 1, "yy|v$p", "ab cd ef\n  gh ij\nk\nkl\n", (3, 0), ("l", False)),
        (T, 2, 0, "yy|vlp", "ab cd ef\n  gh ij\n\nkl\n", (3, 0), ("kl", False)),
        (T, 0, 0, "yy|jVp", "ab cd ef\nab cd ef\nkl", (1, 0), ("  gh ij\n", True)),
        (T, 0, 0, "yy|jVjp", "ab cd ef\nab cd ef", (1, 0), ("  gh ij\nkl\n", True)),
        (T, 0, 0, "yy|jVj2p", "ab cd ef\nab cd ef\nab cd ef", (1, 0), ("  gh ij\nkl\n", True)),
        (T, 0, 0, "jyy|ggVp", "  gh ij\n  gh ij\nkl", (0, 2), ("ab cd ef\n", True)),
        ("ab", 0, 0, "yy|Vp", "ab", (0, 0), ("ab\n", True)),
        ("ab\ncd", 0, 0, "yy|Vjp", "ab", (0, 0), ("ab\ncd\n", True)),
        (T, 0, 0, "yy|Vjjp", "ab cd ef", (0, 0), ("ab cd ef\n  gh ij\nkl\n", True)),
        (T, 0, 0, "yw|jVp", "ab cd ef\nab \nkl", (1, 0), ("  gh ij\n", True)),
        (T, 0, 0, "yw|jVjp", "ab cd ef\nab ", (1, 0), ("  gh ij\nkl\n", True)),
        (T, 0, 0, "yw|Vp", "ab \n  gh ij\nkl", (0, 0), ("ab cd ef\n", True)),
        (T, 0, 0, "yw|jV2p", "ab cd ef\nab \nab \nkl", (1, 0), ("  gh ij\n", True)),
        ("ab", 0, 0, "yl|Vp", "a", (0, 0), ("ab\n", True)),
        (T, 0, 0, "yl|Vjjp", "a", (0, 0), ("ab cd ef\n  gh ij\nkl\n", True)),
        (T, 0, 3, "vjly|Gvp", "ab cd ef\n  gh ij\ncd ef\n  gh l", (2, 0), ("k", False)),
        (T, 0, 3, "vjly|ggvp", "cd ef\n  gh b cd ef\n  gh ij\nkl", (0, 0), ("a", False)),
        (T, 0, 3, "vjly|ggVp", "cd ef\n  gh \n  gh ij\nkl", (0, 0), ("ab cd ef\n", True)),
        (
            T,
            0,
            3,
            "vjly|jV2p",
            "ab cd ef\ncd ef\n  gh \ncd ef\n  gh \nkl",
            (1, 0),
            ("  gh ij\n", True),
        ),
        (T, 0, 3, "vjly|G$vp", "ab cd ef\n  gh ij\nkcd ef\n  gh ", (2, 1), ("l", False)),
        (T, 0, 0, "vlp", " cd ef\n  gh ij\nkl", (0, 0), ("ab", False)),
        (T, 0, 0, "Vp", "  gh ij\nkl", (0, 2), ("ab cd ef\n", True)),
        (T, 0, 0, "Vjp", "kl", (0, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 1, 4, "Vjp", "ab cd ef", (0, 0), ("  gh ij\nkl\n", True)),
        ("a\n\n", 0, 0, "yl|Gvp", "a\n\na", (2, 0), ("a", False)),
        (T, 0, 1, "vly|wvlp|P", "ab bcd  ef\n  gh ij\nkl", (0, 5), ("cd", False)),
        (T, 0, 0, "yw|wvlp|wvlp", "ab ab  cd\n  gh ij\nkl", (0, 8), ("ef", False)),
        # undo and redo
        (T, 0, 3, "vjd|u", T, (0, 3), ("cd ef\n  gh", False)),
        (T, 1, 4, "vkd|u", T, (0, 4), ("d ef\n  gh ", False)),
        (T, 1, 4, "Vjd|u", T, (1, 0), ("  gh ij\nkl\n", True)),
        (T, 1, 4, "Vkd|u", T, (0, 4), ("ab cd ef\n  gh ij\n", True)),
        (T, 1, 3, "Vhd|u", T, (1, 0), ("  gh ij\n", True)),
        (T, 1, 3, "Vjod|u", T, (1, 3), ("  gh ij\nkl\n", True)),
        (T, 0, 3, "vjcX<Esc>|u", T, (0, 3), ("cd ef\n  gh", False)),
        (T, 1, 4, "VkcX<Esc>|u", T, (1, 4), ("ab cd ef\n  gh ij\n", True)),
        (T, 0, 4, "VjcX<Esc>|u", T, (1, 0), ("ab cd ef\n  gh ij\n", True)),
        (T, 0, 0, "yy|jVp|u", T, (1, 0), ("  gh ij\n", True)),
        (T, 0, 0, "yw|wvlp|u", T, (0, 3), ("cd", False)),
        (T, 0, 3, "vjly|Gvp|u", T, (2, 0), ("k", False)),
        (T, 1, 4, "Vkd|u|<C-r>", "kl", (0, 1), ("ab cd ef\n  gh ij\n", True)),
        (T, 0, 3, "vjd|u|<C-r>", "ab  ij\nkl", (0, 3), ("cd ef\n  gh", False)),
        (T, 0, 2, "vjx|u", T, (0, 2), (" cd ef\n  g", False)),
        (T, 0, 0, "yy|wvjp|u|<C-r>", "ab \nab cd ef\n ij\nkl", (0, 2), ("cd ef\n  gh", False)),
        # wide and combined characters vim agrees on
        (
            S,
            0,
            0,
            "vly",
            "\U0001f600x \u65e5\u672c\u8a9e\ne\u0301a b\n\tc",
            (0, 0),
            ("\U0001f600x", False),
        ),
        (
            S,
            0,
            0,
            "vey",
            "\U0001f600x \u65e5\u672c\u8a9e\ne\u0301a b\n\tc",
            (0, 0),
            ("\U0001f600x", False),
        ),
        (
            S,
            0,
            3,
            "vly",
            "\U0001f600x \u65e5\u672c\u8a9e\ne\u0301a b\n\tc",
            (0, 3),
            ("\u65e5\u672c", False),
        ),
        (
            S,
            0,
            4,
            "v$y",
            "\U0001f600x \u65e5\u672c\u8a9e\ne\u0301a b\n\tc",
            (0, 4),
            ("\u672c\u8a9e\n", False),
        ),
        (
            S,
            1,
            0,
            "vly",
            "\U0001f600x \u65e5\u672c\u8a9e\ne\u0301a b\n\tc",
            (1, 0),
            ("e\u0301a", False),
        ),
        (
            S,
            1,
            0,
            "vjy",
            "\U0001f600x \u65e5\u672c\u8a9e\ne\u0301a b\n\tc",
            (1, 0),
            ("e\u0301a b\n\t", False),
        ),
        (S, 2, 0, "vly", S, (2, 0), ("\tc", False)),
        (S, 0, 1, "vjd", "\U0001f600b\n\tc", (0, 1), ("x \u65e5\u672c\u8a9e\ne\u0301a ", False)),
        (S, 0, 0, "Vjd", "\tc", (0, 1), ("\U0001f600x \u65e5\u672c\u8a9e\ne\u0301a b\n", True)),
        (
            S,
            0,
            3,
            "vlcX<Esc>",
            "\U0001f600x X\u8a9e\ne\u0301a b\n\tc",
            (0, 3),
            ("\u65e5\u672c", False),
        ),
        (
            S,
            1,
            0,
            "yl|kvp",
            "e\u0301x \u65e5\u672c\u8a9e\ne\u0301a b\n\tc",
            (0, 0),
            ("\U0001f600", False),
        ),
    ],
)
def test_vim(
    editor: QPlainTextEdit,
    text: str,
    line: int,
    col: int,
    keys: str,
    expected: str,
    cursor: tuple[int, int],
    register: tuple[str, bool],
) -> None:
    vim = start(editor, text, line, col)
    run(editor, keys)
    assert text_of(editor) == expected
    assert cursor_of(editor) == Pos(*cursor)
    assert _Shared.register == Register(*register)
    assert vim.mode is Mode.NORMAL


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
    vim = start(editor, text, line, col)
    run(editor, keys)
    assert text_of(editor) == expected
    assert cursor_of(editor) == Pos(*cursor)
    assert _Shared.register == Register(*register)
    assert vim.mode is Mode.NORMAL


# --- what the editor shows ---


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
    start(editor, T, 0, 1)
    send(editor, keys)
    assert plain(editor.textCursor().selectedText()) == selected
    linewise = keys.startswith("V") or "V" in keys
    send(editor, "y")
    assert _Shared.register == Register(selected + "\n" if linewise else selected, linewise)


def test_an_empty_last_line_selects_nothing(editor: QPlainTextEdit) -> None:
    vim = start(editor, "a\n", 1, 0)
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
    vim = start(editor, T + "\n" + FAMILY + UA, 0, 1)
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
    vim = start(editor, "\n".join(f"line {i}" for i in range(200)), 100, 2)
    send(editor, "vl")
    assert caret_of(vim) == caret_rect(editor, Pos(100, 3))
    bar = editor.verticalScrollBar()
    bar.setValue(bar.value() - 5)
    QApplication.processEvents()
    assert caret_of(vim) == caret_rect(editor, Pos(100, 3))


def test_mode_signals(editor: QPlainTextEdit) -> None:
    vim = start(editor, T)
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
    vim = start(editor, T, 0, 0)
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
    assert _Shared.register == Register("ab cd ef\n  g", linewise=False)


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
    vim = start(window.editor, T)
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


# --- the mouse ---

LEFT = Qt.MouseButton.LeftButton
NO_KEYS = Qt.KeyboardModifier.NoModifier


def point(editor: QPlainTextEdit, pos: Pos) -> QPoint:
    """The point just before the character at pos."""
    cursor = QTextCursor(editor.document())
    cursor.setPosition(Lines(editor.document().toRawText()).to_qt(pos))
    rect = editor.cursorRect(cursor)
    return QPoint(rect.x(), rect.center().y())


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
    vim = start(editor, T)
    drag(editor, a, b)
    assert vim.mode is Mode.VISUAL
    assert plain(editor.textCursor().selectedText()) == selected
    assert caret_of(vim) == caret_rect(editor, cursor)
    send(editor, "y")
    assert _Shared.register == Register(selected, linewise=False)
    send(editor, "v")
    assert caret_of(vim) == caret_rect(editor, min(a, b))


def test_keys_go_on_from_a_drag(editor: QPlainTextEdit) -> None:
    vim = start(editor, T)
    drag(editor, Pos(0, 3), Pos(0, 5))
    send(editor, "l")
    assert plain(editor.textCursor().selectedText()) == "cd "
    send(editor, "d")
    assert text_of(editor) == "ab ef\n  gh ij\nkl"
    assert vim.mode is Mode.NORMAL


def test_a_double_click_selects_a_word(editor: QPlainTextEdit) -> None:
    vim = start(editor, T)
    QTest.mouseDClick(editor.viewport(), LEFT, NO_KEYS, point(editor, Pos(0, 4)))
    assert vim.mode is Mode.VISUAL
    send(editor, "d")
    assert text_of(editor) == "ab  ef\n  gh ij\nkl"


def test_a_click_ends_visual_mode(editor: QPlainTextEdit) -> None:
    vim = start(editor, T)
    send(editor, "vj")
    QTest.mouseClick(editor.viewport(), LEFT, NO_KEYS, point(editor, Pos(2, 1)))
    assert vim.mode is Mode.NORMAL
    assert not editor.textCursor().hasSelection()
    assert cursor_of(editor) == Pos(2, 1)
    assert caret_of(vim) is None


def test_a_drag_in_insert_mode_stays_a_plain_selection(editor: QPlainTextEdit) -> None:
    vim = start(editor, T)
    send(editor, "i")
    drag(editor, Pos(0, 1), Pos(0, 5))
    assert vim.mode is Mode.INSERT
    assert editor.textCursor().selectedText() == "b cd"
    assert caret_of(vim) is None


# --- the app ---


def test_the_app_changing_text_elsewhere_keeps_the_selection(editor: QPlainTextEdit) -> None:
    vim = start(editor, T, 1, 2)
    send(editor, "vl")
    edit = QTextCursor(editor.document())
    edit.insertText("new\n")
    assert vim.mode is Mode.VISUAL
    assert editor.textCursor().selectedText() == "gh"
    assert caret_of(vim) == caret_rect(editor, Pos(2, 3))
    send(editor, "y")
    assert _Shared.register == Register("gh", linewise=False)


def test_new_text_from_the_app_ends_visual_mode(editor: QPlainTextEdit) -> None:
    vim = start(editor, T, 1, 2)
    send(editor, "Vj")
    editor.setPlainText("other")
    assert vim.mode is Mode.NORMAL
    assert caret_of(vim) is None
    send(editor, "x")
    assert text_of(editor) == "ther"


def test_a_selection_by_the_app_in_visual_mode(editor: QPlainTextEdit) -> None:
    vim = start(editor, T)
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
    vim = start(editor, T)
    cursor = editor.textCursor()
    cursor.setPosition(1)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    editor.setTextCursor(cursor)
    assert vim.mode is Mode.NORMAL


def test_turning_vim_off_in_visual_mode(editor: QPlainTextEdit) -> None:
    plain_width = editor.cursorWidth()
    vim = start(editor, T)
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


# --- undo and the register ---


@pytest.mark.parametrize(
    "keys",
    ["vjd", "Vjd", "vjcXY<Esc>", "VcXY<Esc>", "vlp", "Vp", "vjp", "Vjp", "vx"],
)
def test_each_visual_command_is_one_undo_step(editor: QPlainTextEdit, keys: str) -> None:
    start(editor, T, 0, 1)
    _Shared.register = Register("reg\n", linewise=True) if "V" in keys else Register("r")
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
    vim = start(editor, T, 0, 3)
    vim.clipboard = True
    send(editor, "vly")
    assert QGuiApplication.clipboard().text() == "cd"
    send(editor, "Vd")
    assert QGuiApplication.clipboard().text() == "ab cd ef\n"
    QGuiApplication.clipboard().setText("new")
    send(editor, "vp")  # on the first non-blank after Vd
    assert text_of(editor) == "  newh ij\nkl"
    assert QGuiApplication.clipboard().text() == "g"
