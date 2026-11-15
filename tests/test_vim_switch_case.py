"""~ on a real QPlainTextEdit, where it differs from vim or vim can't be recorded.

The cases in tests/cases/switch_case.json check the rest against vim 9.1.
"""

import pytest
from PySide6.QtWidgets import QPlainTextEdit
from qtkeys import cursor_of, send, start_vim, text_of

import side_vim.vim as vim_module
from side_vim import Mode
from side_vim.edits import Register
from side_vim.motions import Pos

pytestmark = pytest.mark.usefixtures("empty_register")

FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"
UA = "\U0001f1fa\U0001f1e6"


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected", "cursor"),
    [
        # Joined emoji and flags are one character; vim splits them
        (f"a{FAMILY}b", 0, 0, "3~", f"A{FAMILY}B", (0, 2)),
        (f"{UA}ab", 0, 0, "2~", f"{UA}Ab", (0, 2)),
        (f"a{FAMILY}b\ncd", 0, 1, "vj~", f"a{FAMILY}B\nCD", (0, 1)),
    ],
)
def test_tilde(
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
