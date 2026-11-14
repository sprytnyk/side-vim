"""Operators, paste, join, undo and the register, on a real QPlainTextEdit.

Expected results marked "vim" were checked against vim 9.1 (`vim -u NONE`, with
'nojoinspaces'). In keys, | only splits commands: vim's `:normal` makes one undo step of
everything it runs, so the vim check ran each part on its own.
"""

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QGuiApplication, QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from qtkeys import cursor_of, put_cursor, send, text_of

from side_vim import Mode, VimMode
from side_vim.edits import Register
from side_vim.motions import Pos
from side_vim.vim import _Shared

SMILE = "\U0001f600"
FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
UA = "\U0001f1fa\U0001f1e6"
E_ACUTE = "e\u0301"


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
    ("text", "line", "col", "keys", "expected", "cursor"),
    [
        # all checked against vim
        # d, x and D
        ("foo bar baz", 0, 4, "dw", "foo baz", (0, 4)),
        ("foo bar baz", 0, 4, "d2w", "foo ", (0, 3)),
        ("foo bar baz", 0, 4, "2dw", "foo ", (0, 3)),
        ("foo bar baz", 0, 4, "de", "foo  baz", (0, 4)),
        ("foo bar baz", 0, 4, "db", "bar baz", (0, 0)),
        ("foo bar baz", 0, 4, "d$", "foo ", (0, 3)),
        ("foo bar baz", 0, 4, "D", "foo ", (0, 3)),
        ("foo bar baz", 0, 4, "d0", "bar baz", (0, 0)),
        ("  foo bar", 0, 6, "d^", "  bar", (0, 2)),
        ("foo bar", 0, 4, "dh", "foobar", (0, 3)),
        ("foo bar", 0, 4, "dl", "foo ar", (0, 4)),
        ("foo bar", 0, 4, "x", "foo ar", (0, 4)),
        ("foo bar", 0, 4, "3x", "foo ", (0, 3)),
        ("foo bar", 0, 6, "x", "foo ba", (0, 5)),
        ("foo bar", 0, 4, "9x", "foo ", (0, 3)),
        ("", 0, 0, "x", "", (0, 0)),
        ("a\n\nb", 1, 0, "x", "a\n\nb", (1, 0)),
        ("  a\n  b\n  c\n  d", 1, 3, "dj", "  a\n  d", (1, 2)),
        ("  a\n  b\n  c\n  d", 1, 3, "dk", "  c\n  d", (0, 2)),
        ("  a\n  b\n  c\n  d", 1, 3, "dG", "  a", (0, 2)),
        ("  a\n  b\n  c\n  d", 2, 3, "dgg", "  d", (0, 2)),
        ("  a\n  b\n  c\n  d", 1, 3, "dd", "  a\n  c\n  d", (1, 2)),
        ("  a\n  b\n  c\n  d", 1, 3, "2dd", "  a\n  d", (1, 2)),
        ("  a\n  b\n  c\n  d", 3, 3, "dd", "  a\n  b\n  c", (2, 2)),
        ("  a\n  b\n  c\n  d", 2, 3, "5dd", "  a\n  b", (1, 2)),
        ("abc", 0, 1, "dd", "", (0, 0)),
        ("", 0, 0, "dd", "", (0, 0)),
        ("foo bar\nbaz", 0, 4, "2D", "foo ", (0, 3)),
        ("foo bar\nbaz", 0, 4, "d3l", "foo \nbaz", (0, 3)),
        (f"{SMILE}{SMILE} ab", 0, 0, "x", f"{SMILE} ab", (0, 0)),
        (f"{SMILE}{SMILE} ab", 0, 1, "dw", f"{SMILE}ab", (0, 1)),
        ("日本語 x", 0, 1, "x", "日語 x", (0, 1)),
        ("日本語 x", 0, 1, "D", "日", (0, 0)),
        (f"a{SMILE}b", 0, 0, "dl", f"{SMILE}b", (0, 0)),
        # c and C
        ("foo bar baz", 0, 4, "cwxy<Esc>", "foo xy baz", (0, 5)),
        ("foo bar baz", 0, 4, "cexy<Esc>", "foo xy baz", (0, 5)),
        ("foo bar baz", 0, 4, "c$xy<Esc>", "foo xy", (0, 5)),
        ("foo bar baz", 0, 4, "Cxy<Esc>", "foo xy", (0, 5)),
        ("foo bar baz", 0, 4, "cbxy<Esc>", "xybar baz", (0, 1)),
        ("foo bar baz", 0, 4, "c0xy<Esc>", "xybar baz", (0, 1)),
        ("foo bar baz", 0, 0, "chxy<Esc>", "xyfoo bar baz", (0, 1)),
        ("foo   bar", 0, 3, "cwxy<Esc>", "fooxybar", (0, 4)),
        ("foo bar baz", 0, 0, "3cwxy<Esc>", "xy", (0, 1)),
        ("foo bar baz", 0, 0, "c2exy<Esc>", "xy baz", (0, 1)),
        ("  a\n  b\n  c", 1, 3, "ccxy<Esc>", "  a\nxy\n  c", (1, 1)),
        ("  a\n  b\n  c", 1, 3, "2ccxy<Esc>", "  a\nxy", (1, 1)),
        ("  a\n  b\n  c", 0, 3, "cjxy<Esc>", "xy\n  c", (0, 1)),
        ("  a\n  b\n  c", 2, 3, "ccxy<Esc>", "  a\n  b\nxy", (2, 1)),
        ("  a\n  b\n  c", 2, 3, "ckxy<Esc>", "  a\nxy", (1, 1)),
        ("abc", 0, 1, "cc<Esc>", "", (0, 0)),
        ("", 0, 0, "ccxy<Esc>", "xy", (0, 1)),
        ("a\n\nb", 1, 0, "cwxy<Esc>", "a\nxy\nb", (1, 1)),
        ("foo bar", 0, 4, "cwxy<CR>z<Esc>", "foo xy\nz", (1, 0)),
        # y, p and P
        ("foo bar baz", 0, 4, "yw|P", "foo bar bar baz", (0, 7)),
        ("foo bar baz", 0, 4, "yw|p", "foo bbar ar baz", (0, 8)),
        ("foo bar baz", 0, 4, "yb", "foo bar baz", (0, 0)),
        ("foo bar baz", 0, 4, "ye", "foo bar baz", (0, 4)),
        ("foo bar baz", 0, 4, "y0", "foo bar baz", (0, 0)),
        ("foo bar baz", 0, 4, "y$|$|p", "foo bar bazbar baz", (0, 17)),
        ("  a\n  b\n  c", 1, 3, "yy|p", "  a\n  b\n  b\n  c", (2, 2)),
        ("  a\n  b\n  c", 1, 3, "yy|P", "  a\n  b\n  b\n  c", (1, 2)),
        ("  a\n  b\n  c", 1, 3, "yy|2p", "  a\n  b\n  b\n  b\n  c", (2, 2)),
        ("  a\n  b\n  c", 1, 3, "yy|G|p", "  a\n  b\n  c\n  b", (3, 2)),
        ("  a\n  b\n  c", 1, 3, "yy|gg|P", "  b\n  a\n  b\n  c", (0, 2)),
        ("  a\n  b\n  c", 0, 3, "2yy|G|p", "  a\n  b\n  c\n  a\n  b", (3, 2)),
        ("  a\n  b\n  c", 1, 3, "yk", "  a\n  b\n  c", (0, 2)),
        ("  a\n  b\n  c", 1, 3, "yj|p", "  a\n  b\n  b\n  c\n  c", (2, 2)),
        ("  a\n  b\n  c", 2, 3, "ygg", "  a\n  b\n  c", (0, 2)),
        ("  a\n  b\n  c", 0, 3, "yG|P", "  a\n  b\n  c\n  a\n  b\n  c", (0, 2)),
        ("abc\n\nxyz", 0, 1, "yl|j|3p", "abc\nbbb\nxyz", (1, 2)),
        ("abc\n\nxyz", 0, 1, "yl|j|P", "abc\nb\nxyz", (1, 0)),
        ("abc", 0, 1, "yl|3p", "abbbbc", (0, 4)),
        ("abc", 0, 1, "yl|3P", "abbbbc", (0, 3)),
        ("abc\ndef\nxyz", 0, 1, "y2w|j|p", "abc\ndebc\ndeff\nxyz", (1, 2)),
        ("abc\ndef\nxyz", 0, 1, "y2w|j|2p", "abc\ndebc\ndefbc\ndeff\nxyz", (1, 2)),
        ("abc\ndef\nxyz", 0, 1, "y2w|j|P", "abc\ndbc\ndefef\nxyz", (1, 1)),
        ("abc\ndef", 0, 0, "dd|p", "def\nabc", (1, 0)),
        ("abc\ndef", 1, 0, "dd|p", "abc\ndef", (1, 0)),
        ("abc\ndef", 1, 0, "dd|P", "def\nabc", (0, 0)),
        ("abc", 0, 0, "dd|p", "\nabc", (1, 0)),
        ("abc", 0, 0, "dd|P", "abc\n", (0, 0)),
        ("abc", 0, 0, "x|p", "bac", (0, 1)),
        ("abc", 0, 1, "x|p", "acb", (0, 2)),
        ("foo bar", 0, 4, "dw|0|P", "barfoo ", (0, 2)),
        ("foo bar", 0, 0, "cwxy<Esc>|$|p", "xy barfoo", (0, 8)),
        ("  a\n  b", 1, 3, "cc<Esc>|p", "  a\n\n  b", (2, 2)),
        ("abc def", 0, 1, "yy|x|p", "acb def", (0, 2)),
        ("abc", 0, 0, "yl|d0|p", "aabc", (0, 1)),
        ("abc", 0, 0, "p", "abc", (0, 0)),
        (f"{SMILE} 日本", 0, 0, "yl|$|p", f"{SMILE} 日本{SMILE}", (0, 4)),
        (f"{SMILE} 日本", 0, 2, "x|0|P", f"日{SMILE} 本", (0, 0)),
        (f"{SMILE} 日本", 0, 2, "yl|2P", f"{SMILE} 日日日本", (0, 3)),
        # J, with 'nojoinspaces'
        ("ab\n  cd\nef", 0, 0, "J", "ab cd\nef", (0, 2)),
        ("ab\n  cd\nef", 0, 0, "3J", "ab cd ef", (0, 5)),
        ("ab\n  cd\nef", 0, 0, "9J", "ab cd ef", (0, 5)),
        ("ab\n  cd\nef", 1, 1, "J", "ab\n  cd ef", (1, 4)),
        ("ab\n  cd\nef", 2, 1, "J", "ab\n  cd\nef", (2, 1)),
        ("ab\n  cd\nef", 2, 1, "3J", "ab\n  cd\nef", (2, 0)),
        ("ab\n  cd\nef", 1, 1, "3J", "ab\n  cd ef", (1, 4)),
        ("ab \n  cd", 0, 0, "J", "ab cd", (0, 3)),
        ("ab\t\n  cd", 0, 0, "J", "ab\tcd", (0, 3)),
        ("ab\n\ncd", 0, 0, "J", "ab\ncd", (0, 1)),
        ("ab\n\ncd", 0, 0, "3J", "ab cd", (0, 2)),
        ("\ncd", 0, 0, "J", "cd", (0, 0)),
        ("ab.\ncd", 0, 0, "J", "ab. cd", (0, 3)),
        ("ab?\ncd", 0, 0, "J", "ab? cd", (0, 3)),
        ("ab\n)cd", 0, 0, "J", "ab)cd", (0, 2)),
        ("ab\n   ", 0, 0, "J", "ab", (0, 1)),
        ("ab\n\n", 0, 0, "3J", "ab", (0, 1)),
        ("  ab\n  cd", 0, 3, "J", "  ab cd", (0, 4)),
        ("\n\n", 0, 0, "3J", "", (0, 0)),
        ("ab\n\t cd", 0, 0, "J", "ab cd", (0, 2)),
        (f"{SMILE}\n日本", 0, 0, "J", f"{SMILE} 日本", (0, 1)),
        # u and Ctrl+R: where the cursor goes back to
        ("foo bar baz", 0, 4, "dw|u", "foo bar baz", (0, 4)),
        ("foo bar baz", 0, 4, "dw|0|u", "foo bar baz", (0, 4)),
        ("foo bar baz", 0, 4, "dw|0|u|0|<C-r>", "foo baz", (0, 4)),
        ("foo bar baz", 0, 4, "u", "foo bar baz", (0, 4)),
        ("foo bar baz", 0, 4, "<C-r>", "foo bar baz", (0, 4)),
        ("  a\n  b\n  c", 1, 3, "dd|u", "  a\n  b\n  c", (1, 2)),
        ("  a\n  b\n  c", 1, 0, "dd|u", "  a\n  b\n  c", (1, 0)),
        ("  a\n  b\n  c", 1, 3, "dd|j|u|G|<C-r>", "  a\n  c", (1, 2)),
        ("  a\n  b\n  c", 2, 3, "dk|u", "  a\n  b\n  c", (1, 2)),
        ("  a\n  b\n  c", 2, 0, "dgg|u", "  a\n  b\n  c", (0, 2)),
        ("  a\n  b\n  c", 0, 3, "dG|u", "  a\n  b\n  c", (0, 2)),
        ("a b c d", 0, 0, "x|w|x|w|x|u|u", " b c d", (0, 1)),
        ("a b c d", 0, 0, "x|w|x|w|x|u|u|<C-r>", "  c d", (0, 1)),
        ("a b c d", 0, 0, "x|w|x|w|x|3u|2<C-r>", "  c d", (0, 1)),
        ("a b c d", 0, 0, "x|w|x|w|x|9u", "a b c d", (0, 0)),
        ("a b c d", 0, 0, "x|w|x|w|x|9u|9<C-r>", "   d", (0, 2)),
        ("a b c d", 0, 0, "x|w|x|w|x|2u|x|<C-r>", "  c d", (0, 1)),
        ("abc\ndef", 0, 1, "ix<Esc>|ay<Esc>|u", "axbc\ndef", (0, 2)),
        ("abc\ndef", 0, 1, "ix<Esc>|ay<Esc>|u|u", "abc\ndef", (0, 1)),
        ("abc\ndef", 0, 1, "ixy<BS><Esc>|u", "abc\ndef", (0, 1)),
        ("abc\ndef", 0, 1, "3ix<Esc>|u", "abc\ndef", (0, 1)),
        ("abc\ndef", 0, 1, "3ix<Esc>|u|<C-r>", "axxxbc\ndef", (0, 1)),
        ("abc\ndef", 0, 1, "3ofoo<Esc>|u", "abc\ndef", (0, 1)),
        ("abc\ndef", 0, 1, "ofoo<CR>bar<Esc>|u", "abc\ndef", (0, 1)),
        ("abc\ndef", 0, 1, "ofoo<CR>bar<Esc>|u|<C-r>", "abc\nfoo\nbar\ndef", (0, 1)),
        ("  abc\ndef", 0, 3, "ofoo<Esc>|u", "  abc\ndef", (0, 3)),
        ("  abc\ndef", 1, 1, "Ofoo<Esc>|u", "  abc\ndef", (1, 1)),
        ("abc def", 0, 2, "Axyz<Esc>|0|u", "abc def", (0, 6)),
        ("abc def", 0, 2, "Axyz<Esc>|0|u|0|<C-r>", "abc defxyz", (0, 7)),
        ("abc def", 0, 2, "ixyz<Esc>|0|u", "abc def", (0, 2)),
        ("  abc def\nghi", 0, 3, "cwxy<Esc>|j|u", "  abc def\nghi", (0, 3)),
        ("  abc def\nghi", 0, 3, "cwxy<Esc>|j|u|<C-r>", "  axy def\nghi", (0, 3)),
        ("  a\n  b\n  c", 1, 3, "ccxy<Esc>|u", "  a\n  b\n  c", (1, 2)),
        ("  a\n  b\n  c", 0, 3, "yy|j|p|u", "  a\n  b\n  c", (1, 2)),
        ("ab\n  cd\nef", 0, 1, "3J|u", "ab\n  cd\nef", (0, 1)),
        ("ab\n  cd\nef", 0, 1, "3J|u|<C-r>", "ab cd ef", (0, 1)),
        ("ab\ncd\nef\ngh", 1, 1, "yy|G|p|gg|u", "ab\ncd\nef\ngh", (3, 0)),
        ("abc", 0, 1, "ix<Esc>|u|ay<Esc>|<C-r>", "abyc", (0, 2)),
        ("abc", 0, 1, "x|u|<C-r>|<C-r>", "ac", (0, 1)),
        ("abc", 0, 1, "x|x|u|i<Esc>|<C-r>", "a", (0, 0)),
        # operators on nothing: h at column 0, l on an empty line
        ("abc\n\nx", 0, 0, "yl|j|yl|k|p", "abc\n\nx", (0, 0)),
        ("abc\n\nx", 0, 0, "yl|j|clz<Esc>", "abc\nz\nx", (1, 0)),
        ("abc\n\nx", 0, 0, "yl|j|cl<Esc>|k|p", "aabc\n\nx", (0, 1)),
        ("abc", 0, 0, "yl|yh|p", "abc", (0, 0)),
        ("abc", 0, 0, "yl|ch<Esc>|p", "aabc", (0, 1)),
        ("abc", 0, 0, "yl|y0|p", "abc", (0, 0)),
        ("abc", 0, 0, "2ch<Esc>", "abc", (0, 0)),
        ("abc", 0, 1, "3dh", "bc", (0, 0)),
        ("abc", 0, 1, "3ch<Esc>", "bc", (0, 0)),
        ("abcdef\nab\nabcdef", 0, 4, "$|yy|j", "abcdef\nab\nabcdef", (1, 1)),
        ("abcdef\nab\nabcdef", 0, 4, "$|j|yy|j", "abcdef\nab\nabcdef", (2, 1)),
        ("abcdef\nab\nabcdef", 0, 4, "$|j|x|j", "abcdef\na\nabcdef", (2, 0)),
        ("abc", 0, 0, "chxy<Esc>", "xyabc", (0, 1)),
        ("abc", 0, 0, "dh|p", "abc", (0, 0)),
        ("", 0, 0, "clx<Esc>", "x", (0, 0)),
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
) -> None:
    vim = start(editor, text, line, col)
    run(editor, keys)
    assert text_of(editor) == expected
    assert cursor_of(editor) == Pos(*cursor)
    assert vim.mode is Mode.NORMAL


# --- whole characters, which vim doesn't do for family emoji and flags ---


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected", "cursor"),
    [
        (f"a{FAMILY}b", 0, 1, "x", "ab", (0, 1)),
        (f"a{FAMILY}b", 0, 1, "2x", "a", (0, 0)),
        (f"{UA}{UA}", 0, 0, "x", UA, (0, 0)),
        # a flag after an emoji, which Qt 6.12 splits in two on its own
        (f"{SMILE}{UA}x", 0, 1, "x", f"{SMILE}x", (0, 1)),
        (f"a{E_ACUTE}b", 0, 1, "x", "ab", (0, 1)),
        (f"{FAMILY} {UA}", 0, 0, "dw", UA, (0, 0)),
        (f"{FAMILY} {UA}", 0, 0, "yw|$|p", f"{FAMILY} {UA}{FAMILY} ", (0, 4)),
        (f"a{FAMILY}\n  {UA}b", 0, 0, "J", f"a{FAMILY} {UA}b", (0, 2)),
        (f"{FAMILY}x", 0, 0, "x|u", f"{FAMILY}x", (0, 0)),
        (f"{FAMILY}x", 0, 0, "x|p", f"x{FAMILY}", (0, 1)),
        (f"{UA}x", 0, 0, "x|p", f"x{UA}", (0, 1)),
        (f"a{FAMILY}b", 0, 1, f"cw{UA}<Esc>", f"a{UA}b", (0, 1)),
        ("日本語", 0, 1, "yl|$|p", "日本語本", (0, 3)),
        (f"{SMILE}\n{FAMILY}", 0, 0, "dd|p", f"{FAMILY}\n{SMILE}", (1, 0)),
        (f"x{UA}", 0, 1, "yl|0|P", f"{UA}x{UA}", (0, 0)),
        (f"{UA}", 0, 0, "yl|p", f"{UA}{UA}", (0, 1)),
        # a soft line break (U+2028) is part of its line
        ("ab cd\nef", 0, 0, "dd|p", "ef\nab cd", (1, 0)),
        ("ab cd\nef", 0, 0, "J", "ab cd ef", (0, 5)),
        ("ab cd\nef", 0, 1, "d$", "a\nef", (0, 0)),
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
) -> None:
    start(editor, text, line, col)
    run(editor, keys)
    assert text_of(editor) == expected
    assert cursor_of(editor) == Pos(*cursor)


# --- undo steps ---

UNDO_TEXT = "abc def ghi\n  jkl\nmno pqr\nstu"


@pytest.mark.parametrize(
    "keys",
    [
        "3dd",
        "d2w",
        "x|x|x",
        "5x",
        "D",
        "3J",
        "yy|p",
        "yw|P",
        "x|p|x|P",
        "cwfoo<Esc>",
        "cw<Esc>",
        "ccx<CR>y<Esc>",
        "C<CR><Esc>",
        "3ix<Esc>",
        "Afoo<Esc>",
        "o<Esc>",
        "3ofoo<CR>bar<Esc>",
        "ifoo<BS><BS>x<Left>y<Esc>",
        "a<CR><CR><BS>z<Esc>",
        "ix<Del><Del><Esc>",
        "ix<BS><Esc>",
        f"a{SMILE}<CR>{UA}{FAMILY}<Esc>",
        "dd|ix<Esc>",
        "x|a<Esc>",
        # Qt adds typing right after a paste or an earlier insert to that undo step;
        # each must still be its own step
        "ix<Esc>|ay<Esc>",
        "ix<Esc>|ix<Esc>",
        "yy|p|A!<Esc>",
        "yw|P|a!<Esc>",
        "o<Esc>|ix<Esc>",
    ],
)
def test_each_command_is_one_undo_step(editor: QPlainTextEdit, keys: str) -> None:
    """The document's own undo (the app's Ctrl+Z or Edit menu) and vim's u both step
    back one command or one insert session at a time."""
    start(editor, UNDO_TEXT, 0, 4)
    states = [text_of(editor)]
    for part in keys.split("|"):
        send(editor, part)
        if text_of(editor) != states[-1]:
            states.append(text_of(editor))
    final = states[-1]

    for state in reversed(states[:-1]):
        send(editor, "u")
        assert text_of(editor) == state
    send(editor, "u")
    assert text_of(editor) == states[0]
    for state in states[1:]:
        send(editor, "<C-r>")
        assert text_of(editor) == state
    send(editor, "<C-r>")
    assert text_of(editor) == final

    document = editor.document()
    for state in reversed(states[:-1]):
        document.undo()
        assert text_of(editor) == state
    assert not document.isUndoAvailable()
    for state in states[1:]:
        document.redo()
        assert text_of(editor) == state
    assert not document.isRedoAvailable()


def test_an_empty_insert_keeps_the_redo(editor: QPlainTextEdit) -> None:
    start(editor, "abc", 0, 1)
    send(editor, "xu")
    send(editor, "i<Esc>")
    send(editor, "<C-r>")
    assert text_of(editor) == "ac"


def test_a_new_change_drops_the_redo(editor: QPlainTextEdit) -> None:
    start(editor, "abcd", 0, 0)
    send(editor, "xxuu")
    send(editor, "$x")
    send(editor, "<C-r>")
    assert text_of(editor) == "abc"
    assert not editor.document().isRedoAvailable()


def test_the_editors_own_undo_in_insert_mode(editor: QPlainTextEdit) -> None:
    """Ctrl+Z is the editor's in Insert mode. Vim's u still works after it."""
    vim = start(editor, "abc", 0, 0)
    send(editor, "x")
    send(editor, "Afoo<C-z>")
    assert text_of(editor) == "bc"
    assert vim.mode is Mode.INSERT
    send(editor, "<Esc>u")
    assert text_of(editor) == "abc"
    send(editor, "<C-r>")
    assert text_of(editor) == "bc"
    send(editor, "x")
    assert cursor_of(editor).col <= 1


def test_an_edit_by_the_app_is_undone_in_its_turn(editor: QPlainTextEdit) -> None:
    start(editor, "abc def", 0, 0)
    send(editor, "x")
    cursor = QTextCursor(editor.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText("!")
    send(editor, "u")
    assert text_of(editor) == "bc def"
    send(editor, "u")
    assert text_of(editor) == "abc def"
    assert cursor_of(editor) == Pos(0, 0)
    send(editor, "2<C-r>")
    assert text_of(editor) == "bc def!"
    assert cursor_of(editor).col <= len("bc def!") - 1


def test_new_text_from_the_app_has_nothing_to_undo(editor: QPlainTextEdit) -> None:
    start(editor, "abc")
    send(editor, "x")
    editor.setPlainText("new text")
    send(editor, "u")
    assert text_of(editor) == "new text"
    send(editor, "x")
    send(editor, "u")
    assert text_of(editor) == "new text"


def test_undo_in_a_long_document(editor: QPlainTextEdit) -> None:
    rows = [f"{i} {SMILE} word" for i in range(5000)]
    start(editor, "\n".join(rows))
    send(editor, "2500G3dd")
    assert text_of(editor).split("\n")[2499] == rows[2502]
    send(editor, "Gofoo<CR>bar<Esc>")
    send(editor, "uu")
    assert text_of(editor) == "\n".join(rows)
    assert cursor_of(editor) == Pos(2499, 0)


# --- the register ---


def test_the_register_is_shared_by_editors(qapp: QApplication) -> None:
    a, b = QPlainTextEdit(), QPlainTextEdit()
    a.setPlainText("foo bar")
    b.setPlainText("x")
    vims = VimMode(a), VimMode(b)
    send(a, "yw")
    send(b, "p")
    assert b.toPlainText() == "xfoo "
    send(b, "dd")
    send(a, "P")
    assert a.toPlainText() == "xfoo \nfoo bar"
    assert all(vim.mode is Mode.NORMAL for vim in vims)


def test_operators_fill_the_register(editor: QPlainTextEdit) -> None:
    start(editor, "foo bar\nbaz", 0, 4)
    send(editor, "yw")
    assert _Shared.register == Register("bar", linewise=False)
    send(editor, "yy")
    assert _Shared.register == Register("foo bar\n", linewise=True)
    send(editor, "x")
    assert _Shared.register == Register("b", linewise=False)
    send(editor, "2dd")
    assert _Shared.register == Register("foo ar\nbaz\n", linewise=True)
    send(editor, "cwx<Esc>")  # an empty line: nothing to delete
    assert _Shared.register == Register("foo ar\nbaz\n", linewise=True)


def test_clipboard(editor: QPlainTextEdit) -> None:
    clipboard = QGuiApplication.clipboard()
    clipboard.setText("")
    vim = start(editor, "foo bar\nbaz")
    send(editor, "yw")
    assert clipboard.text() == ""  # off by default
    vim.clipboard = True
    send(editor, "yw")
    assert clipboard.text() == "foo "
    send(editor, "yyjp")  # our own yank keeps its kind: whole lines
    assert text_of(editor) == "foo bar\nbaz\nfoo bar"
    # text from another app: whole lines if it ends in a newline
    clipboard.setText("one\n")
    send(editor, "ggP")
    assert text_of(editor) == "one\nfoo bar\nbaz\nfoo bar"
    clipboard.setText("two")
    send(editor, "P")
    assert text_of(editor) == "twoone\nfoo bar\nbaz\nfoo bar"
    clipboard.setText("w\r\nx\r\n")
    send(editor, "Gp")
    assert text_of(editor) == "twoone\nfoo bar\nbaz\nfoo bar\nw\nx"


def test_clipboard_keeps_the_kind_of_our_own_yank(editor: QPlainTextEdit) -> None:
    vim = start(editor, "ab\ncd\nef", 0, 1)
    vim.clipboard = True
    send(editor, "yj")  # whole lines
    send(editor, "y2w")  # part of lines, yet it ends at a line end
    assert QGuiApplication.clipboard().text() == "b\ncd"
    _Shared.register = Register("x\n", linewise=False)
    QGuiApplication.clipboard().setText("x\n")
    send(editor, "Gp")
    assert text_of(editor) == "ab\ncd\nex\nf"


def test_clipboard_off_pastes_the_register(editor: QPlainTextEdit) -> None:
    QGuiApplication.clipboard().setText("from the clipboard")
    start(editor, "abc", 0, 0)
    send(editor, "ylp")
    assert text_of(editor) == "aabc"


# --- keys and signals ---


def test_signals_for_operators(editor: QPlainTextEdit) -> None:
    vim = start(editor, "foo bar baz")
    pending: list[str] = []
    modes: list[Mode] = []
    vim.pending_changed.connect(pending.append)
    vim.mode_changed.connect(modes.append)
    send(editor, "d2w")
    assert pending == ["d", "d2", ""]
    send(editor, "cwx<Esc>")
    assert modes == [Mode.INSERT, Mode.NORMAL]
    assert text_of(editor) == "x"


def test_esc_cancels_a_pending_operator(editor: QPlainTextEdit) -> None:
    start(editor, "foo bar baz")
    send(editor, "d<Esc>w")
    assert text_of(editor) == "foo bar baz"
    assert cursor_of(editor) == Pos(0, 4)
    send(editor, "2d<Esc>x")
    assert text_of(editor) == "foo ar baz"


def test_counts_multiply(editor: QPlainTextEdit) -> None:
    start(editor, "a b c d e f g")
    send(editor, "2d2w")
    assert text_of(editor) == "e f g"
