"""Motions and operator ranges on plain strings.

The expected results were checked against vim 9.1 (vim -u NONE -N, plus nojoinspaces).
Lines and columns in the tables are 1-based, as vim shows them, and columns count
characters as the user sees them (vim's charcol()).
"""

import pytest
from casefiles import motion_rows, operator_rows

from side_vim.motions import (
    MAXCOL,
    Kind,
    Line,
    Move,
    Pos,
    Range,
    line_range,
    move,
    operator_range,
    range_text,
    screen_col,
)
from side_vim.parser import LINE, Command, Parser
from side_vim.text import split_clusters


def split(text: str) -> list[tuple[str, ...]]:
    return [split_clusters(line) for line in text.split("\n")]


def parse(keys: str) -> Command:
    parser = Parser()
    cmd = None
    for key in keys:
        cmd = parser.feed(key)
    assert cmd is not None, keys
    return cmd


def go(text: str, line: int, col: int, keys: str) -> tuple[int, int]:
    """Run plain motions in Normal mode; return the cursor, 1-based."""
    lines = split(text)
    pos, want = Pos(line - 1, col - 1), None
    parser = Parser()
    for key in keys:
        cmd = parser.feed(key)
        if cmd is None:
            continue
        assert cmd.name == "move", keys
        assert cmd.motion is not None
        moved = move(lines, pos, cmd.motion, cmd.count, want=want)
        if moved is not None:
            pos, want = moved.pos, moved.want
    return pos.line + 1, pos.col + 1


def remove(lines: list[Line], r: Range, insert: str = "") -> str:
    """Delete a range, then type `insert` where it was (how `c` ends up)."""
    rows = ["".join(line) for line in lines]
    if r.linewise:
        middle = [insert] if insert else []
        return "\n".join(rows[: r.start.line] + middle + rows[r.end.line + 1 :])
    head = "".join(lines[r.start.line][: r.start.col])
    tail = "".join(lines[r.end.line][r.end.col :])
    return "\n".join(rows[: r.start.line] + [head + insert + tail] + rows[r.end.line + 1 :])


def operate(text: str, line: int, col: int, keys: str) -> str:
    """Run one operator command; `c` types an X. Returns the new text."""
    lines = split(text)
    pos = Pos(line - 1, col - 1)
    cmd = parse(keys)
    assert cmd.motion is not None
    if cmd.motion == LINE:
        r = line_range(lines, pos, cmd.count)
    else:
        moved = move(lines, pos, cmd.motion, cmd.count, op=cmd.name)
        r = None if moved is None else operator_range(lines, pos, moved, cmd.name)
    if r is None:
        return text
    return remove(lines, r, "X" if cmd.name == "c" else "")


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    motion_rows("word-motions"),
)
def test_word_motions(text: str, line: int, col: int, keys: str, expected: tuple[int, int]) -> None:
    assert go(text, line, col, keys) == expected


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    motion_rows("line-motions"),
)
def test_line_motions(text: str, line: int, col: int, keys: str, expected: tuple[int, int]) -> None:
    assert go(text, line, col, keys) == expected


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    operator_rows("operator-ranges"),
)
def test_operators(text: str, line: int, col: int, keys: str, expected: str) -> None:
    assert operate(text, line, col, keys) == expected


def test_yank_ranges() -> None:
    lines = ["foo bar", "baz"]
    start = Pos(0, 4)
    yw = operator_range(lines, start, move(lines, start, "w", op="y"), "y")
    assert range_text(lines, yw) == "bar"
    assert not yw.linewise
    yj = operator_range(lines, start, move(lines, start, "j", op="y"), "y")
    assert range_text(lines, yj) == "foo bar\nbaz\n"
    assert yj.linewise
    # "y2w" over an empty line turns linewise, the same as "d2w"
    lines = ["foo", "", "bar"]
    r = operator_range(lines, Pos(0, 0), move(lines, Pos(0, 0), "w", 2, op="y"), "y")
    assert r.linewise
    assert range_text(lines, r) == "foo\n\n"


def test_only_delete_turns_linewise_when_blanks_follow() -> None:
    lines = ["a", "", "b"]
    moved = move(lines, Pos(1, 0), "e", op="d")
    assert operator_range(lines, Pos(1, 0), moved, "d").linewise
    assert not operator_range(lines, Pos(1, 0), moved, "y").linewise


def test_kinds_and_wanted_column() -> None:
    lines = ["abc", "de"]
    assert move(lines, Pos(0, 0), "w").kind is Kind.EXCLUSIVE
    assert move(lines, Pos(0, 0), "e").kind is Kind.INCLUSIVE
    assert move(lines, Pos(0, 0), "j").kind is Kind.LINEWISE
    assert move(lines, Pos(0, 0), "$").want == MAXCOL
    assert move(lines, Pos(0, 1), "j").want == 1


def test_visual_mode_may_reach_the_line_end() -> None:
    lines = ["abc", "de"]
    assert move(lines, Pos(0, 0), "$", visual=True).pos == Pos(0, 3)
    assert move(lines, Pos(0, 2), "l", visual=True).pos == Pos(0, 3)
    assert move(lines, Pos(0, 3), "l", visual=True) is None
    assert move(lines, Pos(0, 0), "j", want=MAXCOL, visual=True).pos == Pos(1, 2)


def test_refused_motions() -> None:
    lines = ["ab", "cd"]
    assert move(lines, Pos(0, 0), "h") is None
    assert move(lines, Pos(0, 1), "l") is None
    assert move(lines, Pos(0, 0), "k") is None
    assert move(lines, Pos(1, 0), "j") is None
    assert move(lines, Pos(0, 0), "b") is None
    assert move(lines, Pos(1, 0), "$", 2) is None


def test_h_and_l_keep_an_operator_going() -> None:
    """Vim beeps on `ch` at column 0 but still starts Insert mode: the operator runs
    on nothing. Other refused motions cancel it."""
    lines = ["ab", ""]
    at_start = move(lines, Pos(0, 0), "h", op="c")
    assert at_start == Move(Pos(0, 0), Kind.EXCLUSIVE, 0)
    on_empty = move(lines, Pos(1, 0), "l", op="d")
    assert on_empty == Move(Pos(1, 0), Kind.EXCLUSIVE, 0)
    assert move(lines, Pos(0, 0), "h", op="c", visual=True) is None
    assert move(lines, Pos(0, 0), "b", op="c") is None
    assert move(lines, Pos(1, 0), "j", op="d") is None


TAB = "\tab\nabcdefghijkl"


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    motion_rows("screen-columns"),
)
def test_screen_columns_and_clusters(
    text: str, line: int, col: int, keys: str, expected: tuple[int, int]
) -> None:
    assert go(text, line, col, keys) == expected


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    operator_rows("operator-clusters")
    + [
        ("a👨\u200d👩\u200d👧b", 1, 2, "x", "ab"),
        ("a🇺🇦b", 1, 2, "x", "ab"),
        ("a🇺🇦🇺🇦b", 1, 2, "2x", "ab"),
        ("a🇺🇦b", 1, 2, "D", "a"),
    ],
)
def test_operators_take_whole_characters(
    text: str, line: int, col: int, keys: str, expected: str
) -> None:
    assert operate(text, line, col, keys) == expected


def test_screen_col() -> None:
    assert screen_col("", 0) == 0
    assert screen_col("abc", 2) == 2
    assert screen_col("abc", 3) == 3
    assert screen_col("\tab", 0) == 7
    assert screen_col("\tab", 1) == 8
    assert screen_col("ab\tc", 2) == 7
    assert screen_col("ab\tc", 3) == 8
    assert screen_col("日本", 1) == 2
    assert screen_col(("😀", "x"), 1) == 2
    assert screen_col("\tx", 0, tabstop=4) == 3
    assert screen_col("ab\tx", 3, tabstop=4) == 4


def test_tabstop_changes_where_j_lands() -> None:
    lines = TAB.split("\n")
    assert move(lines, Pos(0, 0), "j").pos == Pos(1, 7)
    assert move(lines, Pos(0, 0), "j", tabstop=4).pos == Pos(1, 3)
