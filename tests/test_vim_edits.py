"""Operators, paste, join, undo and the register, on a real QPlainTextEdit.

Expected results marked "vim" were checked against vim 9.1 (`vim -u NONE`, with
'nojoinspaces'). In keys, | only splits commands: vim's `:normal` makes one undo step of
everything it runs, so the vim check ran each part on its own.
"""

import pytest
from PySide6.QtGui import QGuiApplication, QKeySequence, QTextCursor, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextDocumentLayout, QPlainTextEdit
from qtkeys import cursor_of, send, start_vim, text_of

import side_vim.vim as vim_module
from side_vim import Mode, VimMode
from side_vim.edits import Register
from side_vim.motions import Pos

pytestmark = pytest.mark.usefixtures("empty_register")

SMILE = "\U0001f600"
FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
UA = "\U0001f1fa\U0001f1e6"
E_ACUTE = "e\u0301"


def run(editor: QPlainTextEdit, keys: str) -> None:
    send(editor, keys.replace("|", ""))


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected", "cursor"),
    [
        ("abc\ndef", 0, 1, "ixy<BS><Esc>|u", "abc\ndef", [0, 1]),
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
    vim = start_vim(editor, text, line, col)
    run(editor, keys)
    assert text_of(editor) == expected
    assert cursor_of(editor) == Pos(*cursor)
    assert vim.mode is Mode.NORMAL


# Edits take whole characters. Vim splits family emoji and flags into parts.
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
    start_vim(editor, text, line, col)
    run(editor, keys)
    assert text_of(editor) == expected
    assert cursor_of(editor) == Pos(*cursor)


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
    start_vim(editor, UNDO_TEXT, 0, 4)
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
    start_vim(editor, "abc", 0, 1)
    send(editor, "xu")
    send(editor, "i<Esc>")
    send(editor, "<C-r>")
    assert text_of(editor) == "ac"


def test_a_new_change_drops_the_redo(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abcd", 0, 0)
    send(editor, "xxuu")
    send(editor, "$x")
    send(editor, "<C-r>")
    assert text_of(editor) == "abc"
    assert not editor.document().isRedoAvailable()


def test_the_editors_own_undo_in_insert_mode(editor: QPlainTextEdit) -> None:
    """The editor's undo shortcut works in Insert mode. Vim's u still works after it."""
    vim = start_vim(editor, "abc", 0, 0)
    send(editor, "x")
    send(editor, "Afoo")
    QTest.keySequence(editor, QKeySequence.StandardKey.Undo)
    assert text_of(editor) == "bc"
    assert vim.mode is Mode.INSERT
    send(editor, "<Esc>u")
    assert text_of(editor) == "abc"
    send(editor, "<C-r>")
    assert text_of(editor) == "bc"
    send(editor, "x")
    assert cursor_of(editor).col <= 1


def test_an_edit_by_the_app_is_undone_in_its_turn(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abc def", 0, 0)
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
    start_vim(editor, "abc")
    send(editor, "x")
    editor.setPlainText("new text")
    send(editor, "u")
    assert text_of(editor) == "new text"
    send(editor, "x")
    send(editor, "u")
    assert text_of(editor) == "new text"


def test_undo_in_a_long_document(editor: QPlainTextEdit) -> None:
    rows = [f"{i} {SMILE} word" for i in range(5000)]
    start_vim(editor, "\n".join(rows))
    send(editor, "2500G3dd")
    assert text_of(editor).split("\n")[2499] == rows[2502]
    send(editor, "Gofoo<CR>bar<Esc>")
    send(editor, "uu")
    assert text_of(editor) == "\n".join(rows)
    assert cursor_of(editor) == Pos(2499, 0)


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
    start_vim(editor, "foo bar\nbaz", 0, 4)
    send(editor, "yw")
    assert vim_module._register == Register("bar", linewise=False)
    send(editor, "yy")
    assert vim_module._register == Register("foo bar\n", linewise=True)
    send(editor, "x")
    assert vim_module._register == Register("b", linewise=False)
    send(editor, "2dd")
    assert vim_module._register == Register("foo ar\nbaz\n", linewise=True)
    send(editor, "cwx<Esc>")  # an empty line: nothing to delete
    assert vim_module._register == Register("foo ar\nbaz\n", linewise=True)


def test_clipboard(editor: QPlainTextEdit) -> None:
    clipboard = QGuiApplication.clipboard()
    clipboard.setText("")
    vim = start_vim(editor, "foo bar\nbaz")
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
    vim = start_vim(editor, "ab\ncd\nef", 0, 1)
    vim.clipboard = True
    send(editor, "yj")  # whole lines
    send(editor, "y2w")  # part of lines, yet it ends at a line end
    assert QGuiApplication.clipboard().text() == "b\ncd"
    vim_module._register = Register("x\n", linewise=False)
    QGuiApplication.clipboard().setText("x\n")
    send(editor, "Gp")
    assert text_of(editor) == "ab\ncd\nex\nf"


def test_clipboard_off_pastes_the_register(editor: QPlainTextEdit) -> None:
    QGuiApplication.clipboard().setText("from the clipboard")
    start_vim(editor, "abc", 0, 0)
    send(editor, "ylp")
    assert text_of(editor) == "aabc"


def test_signals_for_operators(editor: QPlainTextEdit) -> None:
    vim = start_vim(editor, "foo bar baz")
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
    start_vim(editor, "foo bar baz")
    send(editor, "d<Esc>w")
    assert text_of(editor) == "foo bar baz"
    assert cursor_of(editor) == Pos(0, 4)
    send(editor, "2d<Esc>x")
    assert text_of(editor) == "foo ar baz"


def test_counts_multiply(editor: QPlainTextEdit) -> None:
    start_vim(editor, "a b c d e f g")
    send(editor, "2d2w")
    assert text_of(editor) == "e f g"


def swap_in(editor: QPlainTextEdit, text: str, revision: int) -> None:
    """Give the editor a new document, as an app with tabs does, and edit it until its
    revision is the one given. Then the revision alone can't tell the two apart."""
    document = QTextDocument(editor)
    document.setDocumentLayout(QPlainTextDocumentLayout(document))
    document.setPlainText(text)
    edit = QTextCursor(document)
    while document.revision() < revision:  # each edit adds one
        if document.toPlainText() == text:
            edit.insertText(text[0])
        else:
            edit.deletePreviousChar()
    assert document.revision() == revision
    editor.setDocument(document)


def test_undo_steps_stay_with_their_document(editor: QPlainTextEdit) -> None:
    start_vim(editor, "ab")
    send(editor, "xxdd")  # the last step is one only vim has: an empty line to none
    swap_in(editor, "alpha\nb\nc", editor.document().revision())
    before = text_of(editor)
    send(editor, "u")
    assert text_of(editor) != before  # undoes the new document's own last step


def test_j_forgets_the_column_from_another_document(editor: QPlainTextEdit) -> None:
    start_vim(editor, "abcdefghij\nx\nabcdefghij", 0, 9)
    send(editor, "j")  # aims for column 9 on the next j
    position = editor.textCursor().position()
    swap_in(editor, "abcdefghij\nabcdefghij\nabcdefghij", editor.document().revision())
    cursor = editor.textCursor()
    cursor.setPosition(position)  # line 1, column 0
    editor.setTextCursor(cursor)
    send(editor, "j")
    assert cursor_of(editor) == Pos(2, 0)
