"""Motions and operator ranges on plain strings.

The expected results were checked against vim 9.1 (vim -u NONE -N, plus nojoinspaces).
Lines and columns in the tables are 1-based, as vim shows them, and columns count
characters as the user sees them (vim's charcol()).
"""

import pytest

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


WORDS = "foo bar.baz  qux\n\n  end"


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    [
        # w e W E across punctuation, blanks and an empty line
        (WORDS, 1, 1, "w", (1, 5)),
        (WORDS, 1, 1, "2w", (1, 8)),
        (WORDS, 1, 1, "3w", (1, 9)),
        (WORDS, 1, 1, "4w", (1, 14)),
        (WORDS, 1, 1, "5w", (2, 1)),
        (WORDS, 1, 1, "6w", (3, 3)),
        (WORDS, 1, 1, "7w", (3, 5)),
        (WORDS, 1, 1, "e", (1, 3)),
        (WORDS, 1, 1, "2e", (1, 7)),
        (WORDS, 1, 1, "4e", (1, 11)),
        (WORDS, 1, 1, "5e", (1, 16)),
        (WORDS, 1, 1, "W", (1, 5)),
        (WORDS, 1, 1, "2W", (1, 14)),
        (WORDS, 1, 1, "E", (1, 3)),
        # b B back over an empty line
        (WORDS, 3, 5, "b", (3, 3)),
        (WORDS, 3, 5, "2b", (2, 1)),
        (WORDS, 3, 5, "3b", (1, 14)),
        (WORDS, 3, 5, "4b", (1, 9)),
        (WORDS, 3, 5, "B", (3, 3)),
        (WORDS, 3, 5, "2B", (2, 1)),
        # end of the text
        ("one two", 1, 5, "w", (1, 7)),
        ("one two", 1, 5, "3w", (1, 7)),
        ("one two", 1, 5, "e", (1, 7)),
        ("ab cd", 1, 5, "e", (1, 5)),
        ("ab cd", 1, 5, "E", (1, 5)),
        ("ab cd", 1, 5, "b", (1, 4)),
        ("a  ", 1, 1, "w", (1, 3)),
        ("a  ", 1, 1, "e", (1, 3)),
        ("ab\n", 1, 1, "w", (2, 1)),
        ("ab\n", 1, 1, "e", (1, 2)),
        # start of the text
        ("  ab", 1, 3, "b", (1, 1)),
        ("ab\ncd", 2, 1, "b", (1, 1)),
        # empty and blank lines
        ("foo\n\nbar", 1, 2, "w", (2, 1)),
        ("foo\n\nbar", 1, 2, "2w", (3, 1)),
        ("foo\n\nbar", 1, 2, "e", (1, 3)),
        ("foo\n   \nbar", 1, 1, "w", (3, 1)),
        ("foo\n   \nbar", 1, 1, "e", (1, 3)),
        ("a\n\nb", 2, 1, "w", (3, 1)),
        ("a\n\nb", 2, 1, "e", (3, 1)),
        ("a\n\nb", 2, 1, "b", (1, 1)),
        ("a\n  \n  \nb", 1, 1, "w", (4, 1)),
        ("a\n  \n  \nb", 1, 1, "2w", (4, 1)),
        # punctuation runs and Cyrillic words
        ("a.b,,c--d", 1, 1, "w", (1, 2)),
        ("a.b,,c--d", 1, 1, "2w", (1, 3)),
        ("a.b,,c--d", 1, 1, "3w", (1, 4)),
        ("a.b,,c--d", 1, 1, "4w", (1, 6)),
        ("a.b,,c--d", 1, 1, "5w", (1, 7)),
        ("a.b,,c--d", 1, 1, "e", (1, 2)),
        ("a.b,,c--d", 1, 1, "2e", (1, 3)),
        ("a.b,,c--d", 1, 1, "W", (1, 9)),
        ("привіт світ_2 ok", 1, 1, "w", (1, 8)),
        ("привіт світ_2 ok", 1, 1, "2w", (1, 15)),
        ("привіт світ_2 ok", 1, 1, "e", (1, 6)),
        ("привіт світ_2 ok", 1, 1, "2e", (1, 13)),
    ],
)
def test_word_motions(text: str, line: int, col: int, keys: str, expected: tuple[int, int]) -> None:
    assert go(text, line, col, keys) == expected


COLS = "abcdef\nab\nabcdef\n\nxyz"


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    [
        # j and k remember the column they aim for
        (COLS, 1, 5, "j", (2, 2)),
        (COLS, 1, 5, "2j", (3, 5)),
        (COLS, 1, 5, "3j", (4, 1)),
        (COLS, 1, 5, "4j", (5, 3)),
        (COLS, 1, 5, "10j", (5, 3)),
        (COLS, 1, 5, "jk", (1, 5)),
        (COLS, 1, 5, "jj", (3, 5)),
        (COLS, 1, 5, "$j", (2, 2)),
        (COLS, 1, 5, "$jj", (3, 6)),
        ("ab\n  cd", 2, 4, "k", (1, 2)),
        ("ab\n  cd", 2, 4, "kj", (2, 4)),
        # gg and G land on the first non-blank
        ("  a\n    b\nc", 3, 1, "gg", (1, 3)),
        ("  a\n    b\nc", 1, 4, "G", (3, 1)),
        ("  a\n    b\nc", 3, 1, "2G", (2, 5)),
        ("  a\n    b\nc", 3, 1, "9G", (3, 1)),
        ("  a\n    b\nc", 3, 1, "2gg", (2, 5)),
        ("   \nx", 2, 1, "gg", (1, 3)),
        ("ab\n", 1, 1, "G", (2, 1)),
        # h and l stop at the ends of the line
        ("abc\ndef", 1, 2, "5l", (1, 3)),
        ("abc\ndef", 1, 2, "5h", (1, 1)),
        ("abc\ndef", 1, 3, "l", (1, 3)),
        ("abc\ndef", 1, 1, "h", (1, 1)),
        # $ with a count goes down
        ("abc\ndef", 1, 2, "3$", (2, 3)),
        ("abc\ndef", 1, 2, "$", (1, 3)),
        # 0 and ^
        ("   abc", 1, 6, "^", (1, 4)),
        ("   abc", 1, 6, "3^", (1, 4)),
        ("   abc", 1, 6, "0", (1, 1)),
        ("   \nx", 1, 1, "^", (1, 3)),
    ],
)
def test_line_motions(text: str, line: int, col: int, keys: str, expected: tuple[int, int]) -> None:
    assert go(text, line, col, keys) == expected


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    [
        # dw and cw at the end of a line keep the newline
        ("foo bar\nbaz qux", 1, 5, "dw", "foo \nbaz qux"),
        ("foo bar\nbaz qux", 1, 5, "cw", "foo X\nbaz qux"),
        ("foo bar\nbaz qux", 1, 5, "2dw", "foo qux"),
        ("foo bar\nbaz qux", 1, 5, "d2w", "foo qux"),
        ("foo bar\nbaz qux", 1, 5, "c2w", "foo X qux"),
        ("foo bar\nbaz qux", 1, 5, "3dw", "foo "),
        ("one two", 1, 5, "dw", "one "),
        ("one two", 1, 5, "d3w", "one "),
        ("one two", 1, 5, "de", "one "),
        ("ab cd", 1, 5, "de", "ab c"),
        ("a  ", 1, 1, "dw", ""),
        # cw on a word is ce; on blanks it's dw
        ("ab c", 1, 2, "cw", "aX c"),
        ("a b", 1, 1, "cw", "X b"),
        ("a b", 1, 1, "c3w", "X"),
        ("ab\ncd ef", 1, 1, "c2w", "X ef"),
        ("ab\ncd ef", 1, 1, "c3w", "X"),
        ("foo   bar", 1, 4, "cw", "fooXbar"),
        ("foo   bar", 1, 4, "dw", "foobar"),
        # an exclusive motion that ends in column 1 stops at the line before
        ("foo\nbar", 1, 1, "dw", "\nbar"),
        ("foo\nbar", 1, 1, "d2w", ""),
        ("foo\nbar", 1, 1, "c2w", "X"),
        ("foo\n\nbar", 1, 2, "dw", "f\n\nbar"),
        ("foo\n\nbar", 1, 2, "d2w", "f\nbar"),
        ("foo\n\nbar", 1, 1, "d2w", "bar"),
        ("  foo\n\nbar", 1, 1, "d2w", "\n\nbar"),
        ("  foo\n\nbar", 1, 3, "d2w", "bar"),
        ("  foo\n\nbar", 1, 4, "d2w", "  f\nbar"),
        ("x foo\nbar", 1, 3, "d2w", "x "),
        ("ab\ncd", 2, 1, "db", "cd"),
        # empty lines
        ("a\n\nb", 2, 1, "dw", "a\nb"),
        ("a\n\nb", 2, 1, "cw", "a\nX\nb"),
        ("a\n\nb", 2, 1, "de", "a"),
        ("a\n\nb", 2, 1, "x", "a\n\nb"),
        ("\nb", 1, 1, "d$", "\nb"),
        ("\nb", 1, 1, "x", "\nb"),
        ("\nb", 1, 1, "c0", "X\nb"),
        ("\nb", 1, 1, "d2$", ""),
        # h l 0 ^ $
        ("abc\ndef", 1, 2, "x", "ac\ndef"),
        ("abc\ndef", 1, 2, "5x", "a\ndef"),
        ("abc\ndef", 1, 2, "d5l", "a\ndef"),
        ("abc\ndef", 1, 2, "d2$", "a"),
        ("abc\ndef", 1, 2, "D", "a\ndef"),
        ("abc\ndef", 1, 2, "C", "aX\ndef"),
        ("ab\ncd", 2, 1, "dh", "ab\ncd"),
        ("   abc", 1, 6, "d^", "   c"),
        ("   abc", 1, 6, "d0", "c"),
        ("  ab", 1, 3, "db", "ab"),
        ("  ab", 1, 3, "d0", "ab"),
        # linewise motions, and counts past the end
        ("a\nb\nc", 3, 1, "dj", "a\nb\nc"),
        ("a\nb\nc", 3, 1, "dk", "a"),
        ("a\nb\nc", 2, 1, "d5j", "a"),
        ("a\nb\nc", 2, 1, "5dd", "a"),
        ("a\nb\nc", 3, 1, "2dd", "a\nb\nc"),
        ("a\nb\nc", 3, 1, "c2j", "a\nb\nc"),
        ("a\nb\nc", 3, 1, "3x", "a\nb\n"),
        ("a\nb\nc", 3, 1, "2D", "a\nb\nc"),
        ("a\nb\nc", 3, 1, "d$", "a\nb\n"),
        ("ab\n  cd", 2, 4, "dk", ""),
        ("  a\n    b\nc", 3, 1, "dG", "  a\n    b"),
        ("  a\n    b\nc", 3, 1, "dgg", ""),
        ("ab\n", 1, 1, "dG", ""),
        ("  a\n  b", 1, 3, "cc", "X\n  b"),
    ],
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
TAB_MID = "ab\tc\nabcdefghijkl"
WIDE = "日本語\nabcdef"
ACCENTS = "éé x\nabcdef"  # é written as e plus a combining accent


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    [
        # a cursor on a tab sits on its last screen cell
        (TAB, 1, 1, "j", (2, 8)),
        (TAB, 1, 1, "jk", (1, 1)),
        (TAB, 2, 5, "k", (1, 1)),
        (TAB, 2, 5, "kj", (2, 5)),
        (TAB, 2, 10, "k", (1, 3)),
        (TAB_MID, 2, 6, "k", (1, 3)),
        (TAB_MID, 2, 6, "kj", (2, 6)),
        (TAB_MID, 1, 4, "j", (2, 9)),
        # CJK takes 2 cells
        (WIDE, 1, 2, "j", (2, 3)),
        (WIDE, 1, 2, "jk", (1, 2)),
        (WIDE, 2, 4, "k", (1, 2)),
        (WIDE, 2, 4, "kj", (2, 4)),
        (WIDE, 2, 3, "k", (1, 2)),
        ("ab日本\nabcdefg", 2, 6, "k", (1, 4)),
        ("ab日本\nabcdefg", 2, 6, "$k", (1, 4)),
        # so do emoji
        ("😀😀x\nabcdef", 1, 2, "j", (2, 3)),
        ("abcdef\n😀😀x", 1, 4, "j", (2, 2)),
        ("abcdef\n😀😀x", 1, 4, "jl", (2, 3)),
        ("a😀b c", 1, 1, "w", (1, 2)),
        ("a😀b c", 1, 1, "2w", (1, 3)),
        ("a😀b c", 1, 1, "e", (1, 2)),
        # an accent belongs to its letter
        (ACCENTS, 1, 1, "w", (1, 4)),
        (ACCENTS, 1, 1, "j", (2, 1)),
    ],
)
def test_screen_columns_and_clusters(
    text: str, line: int, col: int, keys: str, expected: tuple[int, int]
) -> None:
    assert go(text, line, col, keys) == expected


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "expected"),
    [
        ("a😀b c", 1, 1, "x", "😀b c"),
        ("a😀b c", 1, 1, "dw", "😀b c"),
        ("a😀b c", 1, 2, "x", "ab c"),
        ("a👨‍👩‍👧b", 1, 2, "x", "ab"),
        ("a🇺🇦b", 1, 2, "x", "ab"),
        ("a🇺🇦🇺🇦b", 1, 2, "2x", "ab"),
        ("a🇺🇦b", 1, 2, "D", "a"),
        (ACCENTS, 1, 1, "x", "é x\nabcdef"),
        (ACCENTS, 1, 1, "dw", "x\nabcdef"),
        ("aéb", 1, 2, "x", "ab"),
        ("日本語", 1, 2, "x", "日語"),
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
