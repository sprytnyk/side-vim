"""Check the editor against saved Vim results without running Vim."""

from collections.abc import Iterator

import pytest
from casefiles import load_cases
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from qtkeys import cursor_of, put_cursor, send, text_of

import side_vim.vim as vim_module
from side_vim import Mode, VimMode
from side_vim.edits import Register
from side_vim.motions import Pos

# Qt can't scroll past the last full page, so scroll cases that start lower run
# only in test_scroll.
CASES = [
    c
    for c in load_cases()
    if "height" not in c or c["top"] <= len(c["text"].split("\n")) - c["height"]
]


@pytest.fixture
def editor(qapp: QApplication, empty_register: None) -> Iterator[QPlainTextEdit]:
    editor = QPlainTextEdit()
    editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * 8)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    editor.resize(800, 300)
    editor.show()
    yield editor
    editor.close()
    editor.deleteLater()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_parity(editor: QPlainTextEdit, case: dict) -> None:
    editor.setPlainText(case["text"])
    vim = VimMode(editor)
    put_cursor(editor, Pos(*case["cursor"]))
    if "height" in case:
        height = case["height"]
        editor.resize(
            800, height * editor.fontMetrics().lineSpacing() + 2 * editor.frameWidth() + 10
        )
        editor.verticalScrollBar().setValue(case["top"])
        assert editor.firstVisibleBlock().blockNumber() == case["top"]
        assert editor.verticalScrollBar().pageStep() == height
    if "search" in case:
        search = case["search"]
        vim.set_search(search["text"], search["forward"])
        if not search["jump"]:
            put_cursor(editor, Pos(*case["cursor"]))
    send(editor, case["keys"].replace("|", ""))
    expected = case["expected"]
    assert text_of(editor) == expected["text"]
    assert cursor_of(editor) == Pos(*expected["cursor"])
    assert vim_module._register == Register(*expected["register"])
    assert vim.mode is Mode.NORMAL
    if "top" in expected:
        # Qt stops with the last line at the bottom; vim can put it at the top.
        max_top = len(case["text"].split("\n")) - case["height"]
        assert editor.firstVisibleBlock().blockNumber() == min(expected["top"], max_top)
