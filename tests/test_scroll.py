"""The scrolling keys on line numbers. Every case was checked against vim 9.1 (`vim -u
NONE`) in a terminal with an 11-line window, on 60 lines: (top, cursor line, cursor
column) before and after. vim can scroll until only the last line is on the screen, so
these run with max_top at the last line."""

import re

import pytest

from side_vim.scroll import scroll

ROWS = [
    # a count past the end: vim beeps on the last page and keeps the column
    (10, 15, 5, "3<C-b>", (0, 10, 5)),
    (20, 25, 6, "5<C-b>", (0, 3, 6)),
    (40, 45, 7, "3<C-f>", (59, 59, 7)),
    (40, 45, 7, "2<C-f>", (59, 59, 4)),
    (45, 46, 6, "5<C-f>", (59, 59, 6)),
    (0, 7, 7, "2<C-b>", (0, 7, 7)),
    (10, 15, 3, "2<C-b>", (0, 10, 3)),
    (10, 10, 5, "<C-e>", (11, 11, 5)),
    (10, 10, 5, "3<C-e>", (13, 13, 5)),
    (10, 12, 5, "3<C-e>", (13, 13, 5)),
    (10, 12, 15, "3<C-e>", (13, 13, 6)),
    (10, 20, 5, "<C-y>", (9, 19, 5)),
    (10, 18, 5, "3<C-y>", (7, 17, 5)),
    (10, 19, 15, "3<C-y>", (7, 17, 10)),
    (10, 15, 5, "<C-e>", (11, 15, 5)),
    (10, 12, 5, "<C-d>", (15, 17, 4)),
    (10, 12, 5, "3<C-d>", (13, 15, 2)),
    (10, 12, 5, "3<C-d>|<C-d>", (16, 18, 2)),
    (10, 12, 5, "3<C-d>|<C-u>", (10, 12, 2)),
    (10, 15, 5, "<C-u>", (5, 10, 0)),
    (10, 15, 5, "2<C-u>", (8, 13, 0)),
    (10, 12, 5, "20<C-d>", (21, 23, 4)),
    (10, 12, 5, "<C-f>", (19, 19, 0)),
    (10, 15, 5, "<C-b>", (0, 10, 0)),
    (10, 12, 5, "2<C-f>", (28, 28, 0)),
    (20, 25, 5, "2<C-b>", (2, 12, 2)),
    (5, 8, 5, "<C-b>", (0, 6, 2)),
    (1, 8, 5, "<C-b>", (0, 2, 4)),
    (10, 20, 5, "<C-f>", (19, 19, 0)),
    (0, 3, 2, "<C-u>", (0, 0, 2)),
    (0, 3, 2, "<C-y>", (0, 3, 2)),
    (0, 3, 2, "<C-b>", (0, 3, 2)),
    (0, 0, 2, "<C-u>", (0, 0, 2)),
    (2, 3, 2, "<C-u>", (0, 0, 2)),
    (1, 5, 2, "3<C-y>", (0, 5, 2)),
    (49, 55, 2, "<C-d>", (49, 59, 4)),
    (45, 50, 2, "<C-d>", (49, 55, 0)),
    (49, 59, 2, "<C-d>", (49, 59, 2)),
    (49, 55, 2, "<C-e>", (50, 55, 2)),
    (45, 55, 2, "9<C-e>", (54, 55, 2)),
    (45, 50, 2, "<C-f>", (54, 54, 2)),
    (40, 45, 2, "<C-f>", (49, 49, 0)),
    (49, 52, 2, "<C-f>", (59, 59, 4)),
    (49, 52, 2, "<C-y>", (48, 52, 2)),
    (10, 10, 5, "<C-b>", (0, 10, 0)),
    (10, 11, 5, "<C-b>", (0, 10, 0)),
    (20, 20, 5, "<C-b>", (11, 21, 2)),
    (20, 25, 5, "<C-b>", (11, 21, 2)),
    (30, 35, 5, "3<C-b>", (3, 13, 0)),
    (30, 30, 5, "<C-b>", (21, 31, 0)),
    (11, 15, 5, "<C-b>", (2, 12, 2)),
    (12, 15, 5, "<C-b>", (3, 13, 0)),
    (13, 15, 5, "<C-b>", (4, 14, 4)),
    (40, 45, 5, "<C-b>", (31, 41, 4)),
    (2, 8, 5, "<C-b>", (0, 3, 2)),
    (3, 8, 5, "<C-b>", (0, 4, 0)),
    (3, 4, 5, "<C-b>", (0, 4, 0)),
    (10, 15, 5, "<C-f>", (19, 19, 0)),
    (10, 20, 5, "2<C-f>", (28, 28, 0)),
    (10, 20, 5, "<C-f>|<C-b>", (10, 20, 4)),
    (10, 12, 5, "<C-b>|<C-f>", (9, 9, 2)),
    (10, 12, 5, "<C-d>|<C-d>|<C-u>", (15, 17, 4)),
    (10, 12, 5, "4<C-u>|<C-d>", (10, 12, 2)),
    (20, 25, 5, "<C-f>|<C-f>|<C-b>|<C-b>", (20, 30, 2)),
    (30, 35, 5, "0<C-d>", (35, 40, 0)),
    (50, 59, 2, "<C-f>", (59, 59, 4)),
    (59, 59, 2, "<C-f>", (59, 59, 2)),
    (40, 45, 5, "3<C-f>", (59, 59, 5)),
    (25, 30, 5, "<C-e>|<C-y>|<C-y>", (24, 30, 5)),
]


@pytest.mark.parametrize(("top", "line", "col", "keys", "expected"), ROWS)
def test_vim(top: int, line: int, col: int, keys: str, expected: tuple[int, int, int]) -> None:
    amount = None
    start_line = line
    keep = False
    for chunk in keys.split("|"):
        found = re.fullmatch(r"(\d*)(<C-.>)", chunk)
        assert found is not None
        count = int(found.group(1)) if found.group(1) else None
        scrolled = scroll(
            found.group(2),
            count,
            top=top,
            line=line,
            height=11,
            lines=60,
            max_top=59,
            amount=amount,
        )
        if scrolled is not None:
            top, line, amount = scrolled.top, scrolled.line, scrolled.amount
            keep = scrolled.keep_column
    assert (top, line) == expected[:2]
    if expected[1] != start_line and keys[-1] in "fb":
        # Ctrl+F and Ctrl+B go to the first non-blank, unless they beeped
        assert keep == (expected[2] == col)


def test_an_editor_that_stops_at_the_end() -> None:
    """With the last line at the bottom, the cursor still goes where vim's goes."""
    args = {"height": 11, "lines": 60, "max_top": 49}
    scrolled = scroll("<C-f>", None, top=45, line=50, **args)
    assert scrolled is not None
    assert (scrolled.top, scrolled.line) == (49, 54)
    assert scroll("<C-e>", None, top=49, line=55, **args) is None
    scrolled = scroll("<C-e>", 9, top=45, line=46, **args)
    assert scrolled is not None
    assert (scrolled.top, scrolled.line) == (49, 49)


def test_counts_set_what_ctrl_d_scrolls() -> None:
    args = {"height": 11, "lines": 60, "max_top": 49}
    scrolled = scroll("<C-d>", 3, top=10, line=12, **args)
    assert scrolled is not None
    assert scrolled.amount == 3
    again = scroll("<C-u>", None, top=scrolled.top, line=scrolled.line, amount=3, **args)
    assert again is not None
    assert (again.top, again.line) == (10, 12)
    big = scroll("<C-d>", 99, top=10, line=12, **args)
    assert big is not None
    assert big.amount == 11


def test_short_text_and_tiny_screen() -> None:
    assert scroll("<C-d>", None, top=0, line=0, height=11, lines=1, max_top=0) is None
    assert scroll("<C-f>", None, top=0, line=0, height=11, lines=3, max_top=0) is not None
    scrolled = scroll("<C-f>", None, top=0, line=0, height=1, lines=10, max_top=9)
    assert scrolled is not None
    assert (scrolled.top, scrolled.line) == (1, 1)
    with pytest.raises(ValueError, match="not a scrolling key"):
        scroll("x", None, top=0, line=0, height=1, lines=1, max_top=0)
