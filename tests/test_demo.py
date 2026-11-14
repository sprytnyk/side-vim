"""The demo window (`make run`) works: the find bar, the Esc hook, read-only."""

from collections.abc import Iterator

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from qtkeys import cursor_of, send, text_of, type_text

from side_vim import Mode
from side_vim.__main__ import Demo
from side_vim.motions import Pos


@pytest.fixture
def demo(qapp: QApplication) -> Iterator[Demo]:
    window = Demo()
    window.show()
    window.activateWindow()
    assert QTest.qWaitForWindowActive(window)
    window.editor.setFocus()
    yield window
    window.close()
    window.deleteLater()


def test_the_text_is_long_enough_to_scroll(demo: Demo) -> None:
    assert demo.editor.document().blockCount() > 300
    assert demo.editor.verticalScrollBar().maximum() > 0
    send(demo.editor, "<C-f>")
    assert demo.editor.firstVisibleBlock().blockNumber() > 0


def test_find_down_and_up(demo: Demo) -> None:
    send(demo.editor, "/")
    assert demo.find.isVisible()
    assert demo.find.hasFocus()
    send(demo.find, "rent<CR>")
    assert not demo.find.isVisible()
    first = cursor_of(demo.editor)
    line = demo.editor.document().findBlockByNumber(first.line).text()
    assert line[first.col : first.col + 4] == "rent"
    send(demo.editor, "n")
    assert cursor_of(demo.editor) > first
    send(demo.editor, "N")
    assert cursor_of(demo.editor) == first
    send(demo.editor, "?")
    type_text(demo.find, "😀")
    send(demo.find, "<CR>")
    emoji = cursor_of(demo.editor)
    assert emoji < first  # upwards, wrapping round the end
    assert "😀" in demo.editor.document().findBlockByNumber(emoji.line).text()


def test_esc_closes_the_find_bar_first(demo: Demo) -> None:
    send(demo.editor, "i/")
    assert demo.vim.mode is Mode.INSERT
    send(demo.editor, "<Esc>v/")
    assert demo.find.isVisible()
    send(demo.find, "<Esc>")
    assert not demo.find.isVisible()
    assert demo.editor.hasFocus()
    assert demo.vim.mode is Mode.VISUAL
    demo.open_find(True)
    demo.editor.setFocus()
    send(demo.editor, "<Esc>")  # the hook closes the find bar, Visual mode stays
    assert not demo.find.isVisible()
    assert demo.vim.mode is Mode.VISUAL
    send(demo.editor, "<Esc>")
    assert demo.vim.mode is Mode.NORMAL


def test_read_only_box(demo: Demo) -> None:
    before = text_of(demo.editor)
    demo.editor.setReadOnly(True)
    send(demo.editor, "xddp")
    assert text_of(demo.editor) == before
    send(demo.editor, "j")
    assert cursor_of(demo.editor) == Pos(1, 0)
