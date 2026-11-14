"""Vim motions on plain text: where the cursor goes, and what an operator covers.

No Qt here. The text is a sequence of lines without their newlines, and each line is a
sequence of characters as the user sees them (grapheme clusters: a family emoji, a
flag or a letter plus an accent is one character). A plain str works as a line too.
Working on whole clusters means no command can ever cut one in half.

A position is (line, col), both 0-based, col counted in those characters. While a
motion runs, a position may sit on the end of a line (col == len(line)), the spot that
stands for the newline, just as vim's cursor may sit on the NUL at the end of a line.

The word motions follow vim's own step-by-step logic (fwd_word, end_word and bck_word
in vim's textobject.c), so that the odd cases, like `cw` and `dw` at the end of a line,
come out the same as in vim.

The column j and k aim for is a screen column, like vim's: a tab takes up to
`tabstop` cells, CJK characters and emoji take 2.
"""

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from side_vim.unicode import cell_width, char_class

# The column `$` wants: "stay at the end of the line" while moving with j and k.
MAXCOL = sys.maxsize

MOTIONS = frozenset({"h", "j", "k", "l", "w", "b", "e", "W", "B", "E", "0", "^", "$", "gg", "G"})

BLANKS = (" ", "\t")

# One line: a str, or a sequence of grapheme clusters.
type Line = Sequence[str]


class Kind(Enum):
    """How an operator treats the text between the cursor and where the motion went."""

    EXCLUSIVE = "exclusive"  # up to, not including, the end
    INCLUSIVE = "inclusive"  # up to and including the end
    LINEWISE = "linewise"  # whole lines


@dataclass(frozen=True, order=True)
class Pos:
    line: int
    col: int


@dataclass(frozen=True)
class Move:
    """Where a motion took the cursor."""

    pos: Pos
    kind: Kind
    want: int  # the screen column j and k aim for from now on


@dataclass(frozen=True)
class Range:
    """The text an operator acts on.

    Linewise: every line from start.line to end.line, both included; the columns don't
    matter. Otherwise: from start up to, not including, end.
    """

    start: Pos
    end: Pos
    linewise: bool


class _Cursor:
    """A position that steps through the text like vim's inc_cursor and dec_cursor."""

    def __init__(self, lines: Sequence[Line], pos: Pos, bigword: bool = False) -> None:
        self.lines: Sequence[Line] = lines
        self.line: int = pos.line
        self.col: int = pos.col
        self.bigword: bool = bigword

    @property
    def pos(self) -> Pos:
        return Pos(self.line, self.col)

    def char(self) -> str:
        text = self.lines[self.line]
        return text[self.col] if self.col < len(text) else ""

    def cls(self) -> int:
        return char_class(self.char(), self.bigword)

    def line_empty(self) -> bool:
        return not self.lines[self.line]

    def inc(self) -> int:
        """Step forward. 0: moved in the line, 2: onto the line end, 1: to the next line,
        -1: at the end of the text, didn't move."""
        text = self.lines[self.line]
        if self.col < len(text):
            self.col += 1
            return 0 if self.col < len(text) else 2
        if self.line < len(self.lines) - 1:
            self.line += 1
            self.col = 0
            return 1
        return -1

    def dec(self) -> int:
        """Step back. 0: moved in the line, 1: to the end of the line before,
        -1: at the start of the text, didn't move."""
        if self.col > 0:
            self.col -= 1
            return 0
        if self.line > 0:
            self.line -= 1
            self.col = len(self.lines[self.line])
            return 1
        return -1

    def skip_class(self, cls: int, forward: bool) -> bool:
        """Move while on characters of class cls. True if the text ran out."""
        while self.cls() == cls:
            if (self.inc() if forward else self.dec()) == -1:
                return True
        return False


def _fwd_word(cur: _Cursor, count: int, eol: bool) -> bool:
    """vim's fwd_word. eol: an operator is pending, so stop at the end of the line on the
    last word. Returns False when the cursor started on the last character of the text."""
    while count > 0:
        count -= 1
        sclass = cur.cls()
        last_line = cur.line == len(cur.lines) - 1
        i = cur.inc()
        if i == -1 or (i >= 1 and last_line):
            return False
        if i >= 1 and eol and count == 0:
            return True
        # one character past the end of the current word, if any
        if sclass != 0:
            while cur.cls() == sclass:
                i = cur.inc()
                if i == -1 or (i >= 1 and eol and count == 0):
                    return True
        # then on to the next non-blank, stopping at an empty line
        while cur.cls() == 0:
            if cur.col == 0 and cur.line_empty():
                break
            i = cur.inc()
            if i == -1 or (i >= 1 and eol and count == 0):
                return True
    return True


def _end_word(cur: _Cursor, count: int, stop: bool) -> bool:
    """vim's end_word, with empty=False. stop: if already on the end of a word, stay
    there for the first count (how `cw` works)."""
    while count > 0:
        count -= 1
        sclass = cur.cls()
        if cur.inc() == -1:
            return False
        if cur.cls() == sclass and sclass != 0:
            # in the middle of a word: go to its end
            if cur.skip_class(sclass, forward=True):
                return False
        elif not stop or sclass == 0:
            # at the end of a word: skip blanks, then go to the end of the next word
            while cur.cls() == 0:
                if cur.inc() == -1:
                    return False
            if cur.skip_class(cur.cls(), forward=True):
                return False
        _ = cur.dec()  # one step too far
        stop = False
    return True


def _bck_word(cur: _Cursor, count: int) -> bool:
    """vim's bck_word with stop=False. False when already at the start of the text."""
    while count > 0:
        count -= 1
        if cur.dec() == -1:
            return False
        # skip blanks before the word, stopping at an empty line
        empty_line = False
        while cur.cls() == 0:
            if cur.col == 0 and cur.line_empty():
                empty_line = True
                break
            if cur.dec() == -1:
                return True
        if empty_line:
            continue
        # back to the start of this word
        if cur.skip_class(cur.cls(), forward=False):
            return True
        _ = cur.inc()  # one step too far
    return True


def first_non_blank(text: Line) -> int:
    """The column of the first non-blank, or of the last character if the line is all
    blanks (vim's beginline with BL_WHITE | BL_FIX)."""
    col = 0
    while col < len(text) - 1 and text[col] in BLANKS:
        col += 1
    return col


def _width(ch: str, vcol: int, tabstop: int) -> int:
    """Screen cells a character takes when it starts at screen column vcol."""
    if ch == "\t":
        return tabstop - vcol % tabstop
    return cell_width(ch)


def screen_col(text: Line, col: int, tabstop: int = 8) -> int:
    """The screen column vim shows the cursor in: the first cell of a character, but the
    last cell of a tab."""
    vcol = 0
    for ch in text[:col]:
        vcol += _width(ch, vcol, tabstop)
    if col < len(text) and text[col] == "\t":
        vcol += _width("\t", vcol, tabstop) - 1
    return vcol


def _coladvance(text: Line, want: int, visual: bool, tabstop: int) -> int:
    """The column j and k land on for a wanted screen column (vim's coladvance). In
    Visual mode the cursor may sit on the line end."""
    if want >= MAXCOL:
        return max(len(text) - 1 + visual, 0)
    vcol = col = 0
    while vcol <= want and col < len(text):
        vcol += _width(text[col], vcol, tabstop)
        col += 1
    if vcol > want or not visual:
        col -= 1
    return max(col, 0)


def move(
    lines: Sequence[Line],
    pos: Pos,
    motion: str,
    count: int | None = None,
    *,
    want: int | None = None,
    op: str | None = None,
    visual: bool = False,
    tabstop: int = 8,
) -> Move | None:
    """Run a motion. None means vim would refuse it (beep), and a pending operator is
    cancelled.

    count: None when no count was typed (it matters for G and gg).
    want: the screen column j and k aim for; defaults to the cursor's.
    op: the pending operator ("d", "c" or "y"), or None.
    visual: Visual mode, where the cursor may sit on the line end.
    tabstop: how many screen columns a tab stop is apart.
    """
    n = count or 1
    text = lines[pos.line]

    def moved(to: Pos, kind: Kind) -> Move:
        return Move(to, kind, screen_col(lines[to.line], to.col, tabstop))

    if motion == "h":
        if pos.col == 0:
            # vim beeps, but a pending operator still runs, on nothing (`ch` inserts)
            return moved(pos, Kind.EXCLUSIVE) if op and not visual else None
        return moved(Pos(pos.line, max(pos.col - n, 0)), Kind.EXCLUSIVE)

    if motion == "l":
        last = len(text) if visual else len(text) - 1
        if pos.col >= last:
            # at the end already: an operator still takes the last character, or
            # runs on nothing on an empty line
            if op and not visual:
                return moved(pos, Kind.INCLUSIVE if text else Kind.EXCLUSIVE)
            return None
        # running out of line with an operator pending takes the last character too
        kind = Kind.INCLUSIVE if op and not visual and pos.col + n > last else Kind.EXCLUSIVE
        return moved(Pos(pos.line, min(pos.col + n, last)), kind)

    if motion in ("j", "k"):
        if motion == "j":
            if pos.line >= len(lines) - 1:
                return None
            line = min(pos.line + n, len(lines) - 1)
        else:
            if pos.line == 0:
                return None
            line = max(pos.line - n, 0)
        if want is None:
            want = screen_col(text, pos.col, tabstop)
        col = _coladvance(lines[line], want, visual, tabstop)
        return Move(Pos(line, col), Kind.LINEWISE, want)

    if motion == "0":
        return moved(Pos(pos.line, 0), Kind.EXCLUSIVE)

    if motion == "^":
        return moved(Pos(pos.line, first_non_blank(text)), Kind.EXCLUSIVE)

    if motion == "$":
        if n > 1 and pos.line >= len(lines) - 1:
            return None
        line = min(pos.line + n - 1, len(lines) - 1)
        col = _coladvance(lines[line], MAXCOL, visual, tabstop)
        return Move(Pos(line, col), Kind.INCLUSIVE, MAXCOL)

    if motion in ("gg", "G"):
        if count is None:
            line = 0 if motion == "gg" else len(lines) - 1
        else:
            line = min(max(count, 1), len(lines)) - 1
        return moved(Pos(line, first_non_blank(lines[line])), Kind.LINEWISE)

    if motion in ("w", "W", "e", "E"):
        to, kind = _word_motion(lines, pos, motion, n, op, visual)
        return moved(to, kind)

    if motion in ("b", "B"):
        cur = _Cursor(lines, pos, bigword=motion == "B")
        if not _bck_word(cur, n):
            return None
        return moved(cur.pos, Kind.EXCLUSIVE)

    raise ValueError(f"unknown motion: {motion!r}")


def _word_motion(
    lines: Sequence[Line], pos: Pos, motion: str, n: int, op: str | None, visual: bool
) -> tuple[Pos, Kind]:
    """w W e E, like vim's nv_wordcmd."""
    cur = _Cursor(lines, pos, bigword=motion in ("W", "E"))
    word_end = motion in ("e", "E")
    inclusive = word_end
    stop = False
    # "cw" on a word works like "ce": the blanks after the word stay
    if not word_end and op == "c" and cur.char() not in ("", *BLANKS):
        inclusive = word_end = stop = True
    _ = _end_word(cur, n, stop) if word_end else _fwd_word(cur, n, eol=op is not None)
    # Don't leave the cursor on the line end, unless it didn't move forward.
    if pos < cur.pos and cur.col > 0 and cur.char() == "" and not visual:
        cur.col -= 1
        inclusive = True
    return cur.pos, Kind.INCLUSIVE if inclusive else Kind.EXCLUSIVE


def _in_indent(lines: Sequence[Line], pos: Pos) -> bool:
    """True if only blanks come before pos in its line."""
    return all(ch in BLANKS for ch in lines[pos.line][: pos.col])


def operator_range(lines: Sequence[Line], start: Pos, moved: Move, op: str) -> Range:
    """What an operator covers, from the cursor at start to where the motion went.

    Follows vim's rules: an exclusive motion that ends in column 0 of a later line
    stops at the end of the line before, and turns linewise if it started in the
    indent. A multi-line delete turns linewise if it started in the indent and only
    blanks follow its end.
    """
    a, b = sorted((start, moved.pos))
    if moved.kind is Kind.LINEWISE:
        return Range(Pos(a.line, 0), Pos(b.line, 0), linewise=True)

    inclusive = moved.kind is Kind.INCLUSIVE
    if not inclusive and b.col == 0 and b.line > a.line:
        b = Pos(b.line - 1, len(lines[b.line - 1]))
        if _in_indent(lines, a):
            return Range(Pos(a.line, 0), Pos(b.line, 0), linewise=True)
        if b.col:
            b = Pos(b.line, b.col - 1)
            inclusive = True

    end_text = lines[b.line]
    if op == "d" and b.line > a.line:
        rest = end_text[b.col + (inclusive if b.col < len(end_text) else 0) :]
        if all(ch in BLANKS for ch in rest) and _in_indent(lines, a):
            return Range(Pos(a.line, 0), Pos(b.line, 0), linewise=True)

    end = Pos(b.line, min(b.col + inclusive, len(end_text)))
    return Range(a, end, linewise=False)


def line_range(lines: Sequence[Line], pos: Pos, count: int | None = None) -> Range | None:
    """The lines `dd`, `yy` and `cc` cover. None if the count asks for lines below the
    last one and the cursor is already on it."""
    n = count or 1
    if n > 1 and pos.line >= len(lines) - 1:
        return None
    last = min(pos.line + n - 1, len(lines) - 1)
    return Range(Pos(pos.line, 0), Pos(last, 0), linewise=True)


def visual_range(lines: Sequence[Line], anchor: Pos, cursor: Pos, linewise: bool) -> Range:
    """The text a Visual selection covers, both ends included (vim's 'selection' set to
    inclusive). A selection that ends on the line end takes the line break, unless it's
    the last line."""
    a, b = sorted((anchor, cursor))
    if linewise:
        return Range(Pos(a.line, 0), Pos(b.line, 0), linewise=True)
    text = lines[b.line]
    if b.col < len(text):
        end = Pos(b.line, b.col + 1)
    elif b.line < len(lines) - 1:
        end = Pos(b.line + 1, 0)
    else:
        end = Pos(b.line, len(text))
    return Range(a, end, linewise=False)


def range_text(lines: Sequence[Line], r: Range) -> str:
    """The text a range covers. Linewise text ends with a newline, like vim's register."""
    if r.linewise:
        return "".join("".join(lines[i]) + "\n" for i in range(r.start.line, r.end.line + 1))
    if r.start.line == r.end.line:
        return "".join(lines[r.start.line][r.start.col : r.end.col])
    parts = ["".join(lines[r.start.line][r.start.col :])]
    parts.extend("".join(lines[i]) for i in range(r.start.line + 1, r.end.line))
    parts.append("".join(lines[r.end.line][: r.end.col]))
    return "\n".join(parts)
