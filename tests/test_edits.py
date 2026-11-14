"""J and the cursor after undo, on plain text. Joins marked "vim" were checked against
vim 9.1 with 'nojoinspaces' (the cursor index there is a column)."""

import pytest

from side_vim.edits import join, join_parts, undo_cursor
from side_vim.motions import Pos


@pytest.mark.parametrize(
    ("lines", "joined", "cursor"),
    [
        # all vim
        (["ab", "  cd"], "ab cd", 2),
        (["ab", "  cd", "ef"], "ab cd ef", 5),
        (["ab ", "  cd"], "ab cd", 3),
        (["ab\t", "  cd"], "ab\tcd", 3),
        (["ab", ""], "ab", 2),
        (["ab", "", "cd"], "ab cd", 2),
        (["", "cd"], "cd", 0),
        (["", "", ""], "", 0),
        (["ab.", "cd"], "ab. cd", 3),
        (["ab?", "cd"], "ab? cd", 3),
        (["ab", ")cd"], "ab)cd", 2),
        (["ab", "   "], "ab", 2),
        (["ab", "", ""], "ab", 2),
        (["  ab", "  cd"], "  ab cd", 4),
        (["ab", "\t cd"], "ab cd", 2),
        (["\U0001f600", "日本"], "\U0001f600 日本", 1),
    ],
)
def test_join(lines: list[str], joined: str, cursor: int) -> None:
    assert join(lines) == (joined, cursor)


def test_join_parts() -> None:
    assert join_parts(["ab", "  cd", "", "\tef"]) == [(2, " "), (0, ""), (1, " ")]


def test_join_keeps_trailing_blanks_of_the_line_before() -> None:
    assert join(["ab  ", "cd"]) == ("ab  cd", 4)


LINES = ["  foo", "  bar", "baz", ""]


@pytest.mark.parametrize(
    ("saved", "first", "last", "expected"),
    [
        # in the changed lines: back where the change was made
        (Pos(1, 4), 1, 1, Pos(1, 4)),
        (Pos(1, 4), 1, 2, Pos(1, 4)),
        # next to them, as after undoing `o` or a paste below the cursor
        (Pos(0, 3), 1, 1, Pos(0, 3)),
        (Pos(2, 1), 1, 1, Pos(2, 1)),
        # far from them: the first changed line, on its first non-blank
        (Pos(3, 0), 0, 0, Pos(0, 2)),
        (None, 1, 2, Pos(1, 2)),
        # a column past the end of the line now
        (Pos(2, 9), 2, 2, Pos(2, 2)),
        # a line that is gone
        (Pos(9, 0), 8, 9, Pos(3, 0)),
    ],
)
def test_undo_cursor(saved: Pos | None, first: int, last: int, expected: Pos) -> None:
    assert undo_cursor(LINES, saved, first, last) == expected
