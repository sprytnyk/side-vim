"""Every motion and operator from every position of many random texts.

The texts mix the characters most likely to break things: emoji, a family emoji, a
flag, a letter plus a combining accent, CJK, tabs, blanks, punctuation and empty lines.
Nothing may crash, the cursor must stay in the text, and no operator may cut a
character in half.
"""

import functools
import random

import pytest

from side_vim.motions import MOTIONS, Kind, Pos, line_range, move, operator_range, range_text
from side_vim.text import split_clusters

CHARS = (
    "a", "b", "_", " ", " ", "\t", ".", "-",
    "\U0001f600",  # emoji
    "\U0001f468\u200d\U0001f469\u200d\U0001f467",  # family: three emoji joined
    "\U0001f1fa\U0001f1e6",  # the Ukrainian flag: two halves
    "e\u0301",  # e plus a combining accent
    "\u65e5",  # CJK, 2 cells wide
    "\u0457",  # Ukrainian ї
)  # fmt: skip
SEED_COUNT = 40


def random_lines(rng: random.Random) -> list[tuple[str, ...]]:
    return [
        tuple(rng.choice(CHARS) for _ in range(rng.randint(0, 6))) for _ in range(rng.randint(1, 4))
    ]


def whole(text: str) -> bool:
    """True if Qt splits the text into characters that are all from CHARS."""
    return all(whole_line(line) for line in text.split("\n"))


@functools.cache
def whole_line(line: str) -> bool:
    """whole() for one line. The fuzz tests check the same short lines over and over,
    and splitting them again each time was most of their run time."""
    return set(split_clusters(line)) <= set(CHARS)


def delete(lines: list[tuple[str, ...]], start: Pos, end: Pos, linewise: bool) -> str:
    rows = ["".join(line) for line in lines]
    if linewise:
        return "\n".join(rows[: start.line] + rows[end.line + 1 :])
    head = "".join(lines[start.line][: start.col])
    tail = "".join(lines[end.line][end.col :])
    return "\n".join(rows[: start.line] + [head + tail] + rows[end.line + 1 :])


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_motions_stay_in_the_text_and_keep_characters_whole(seed: int) -> None:
    rng = random.Random(seed)
    for _ in range(3):
        lines = random_lines(rng)
        # the texts must survive a round trip through Qt's splitting
        assert [split_clusters("".join(line)) for line in lines] == lines
        for line_no, line in enumerate(lines):
            for col in range(max(len(line), 1)):
                start = Pos(line_no, col)
                for motion in sorted(MOTIONS):
                    for count in (None, 2, 7):
                        check_one(lines, start, motion, count)


def check_one(lines: list[tuple[str, ...]], start: Pos, motion: str, count: int | None) -> None:
    for visual in (False, True):
        moved = move(lines, start, motion, count, visual=visual, tabstop=rng_tabstop(start))
        if moved is None:
            continue
        pos = moved.pos
        assert 0 <= pos.line < len(lines)
        last = len(lines[pos.line]) if visual else max(len(lines[pos.line]) - 1, 0)
        assert 0 <= pos.col <= last, (motion, count, visual, lines, start, pos)

    for op in ("d", "c", "y"):
        moved = move(lines, start, motion, count, op=op)
        if moved is None:
            continue
        assert 0 <= moved.pos.line < len(lines)
        assert 0 <= moved.pos.col <= len(lines[moved.pos.line])
        r = operator_range(lines, start, moved, op)
        assert r.start <= r.end
        if not r.linewise:
            assert r.end.col <= len(lines[r.end.line])
        else:
            assert moved.kind is Kind.LINEWISE or r.start.col == 0
        assert whole(range_text(lines, r).rstrip("\n"))
        assert whole(delete(lines, r.start, r.end, r.linewise))

    r = line_range(lines, start, count)
    if r is not None:
        assert 0 <= r.start.line <= r.end.line < len(lines)


def rng_tabstop(start: Pos) -> int:
    """Vary the tab stop a little, so it isn't always 8."""
    return (4, 8, 3)[(start.line + start.col) % 3]
