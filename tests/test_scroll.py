"""The scrolling keys on line numbers. Every case was checked against vim 9.1 (`vim -u
NONE`) in a terminal with an 11-line window, on 60 lines: (top, cursor line, cursor
column) before and after. vim can scroll until only the last line is on the screen, so
these run with max_top at the last line."""

import re

import pytest
from casefiles import scroll_rows

from side_vim.scroll import scroll

ROWS = scroll_rows()


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
