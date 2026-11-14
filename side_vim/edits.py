"""Edits vim makes that are worked out on plain text: joining lines, and where the
cursor goes after undo, redo and Visual mode operators. No Qt here.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from side_vim.motions import BLANKS, Line, Pos, first_non_blank


@dataclass(frozen=True)
class Register:
    """What yank, delete and change saved. linewise: whole lines (`yy`, `dd`), and the
    text ends with a newline. Otherwise part of a line (`yw`, `x`)."""

    text: str = ""
    linewise: bool = False


def join_parts(lines: Sequence[str]) -> list[tuple[int, str]]:
    """How vim's J (with 'nojoinspaces') joins lines: for each line after the first,
    how many leading blanks it loses, and what goes before it ("" or one space).

    No space goes in when the line so far is empty or ends in a blank, or when the
    next line is empty (or all blanks) or starts with ")".
    """
    parts: list[tuple[int, str]] = []
    empty = not lines[0]
    previous = lines[0]
    for line in lines[1:]:
        rest = line.lstrip("".join(BLANKS))
        space = bool(rest) and not rest.startswith(")") and not empty
        space = space and not previous.endswith(BLANKS)
        parts.append((len(line) - len(rest), " " if space else ""))
        empty = empty and not rest
        previous = rest
    return parts


def join(lines: Sequence[str]) -> tuple[str, int]:
    """The line vim's J makes of these lines, and the index in it (in code points)
    where the cursor goes: where the last join happened."""
    out = lines[0]
    cursor = 0
    for line, (blanks, space) in zip(lines[1:], join_parts(lines), strict=True):
        cursor = len(out)
        out += space + line[blanks:]
    return out, cursor


def undo_cursor(lines: Sequence[Line], saved: Pos | None, first: int, last: int) -> Pos:
    """Where vim puts the cursor after an undo or redo (u_undoredo in vim's undo.c).

    saved: the cursor when the change was made, or None if unknown. first and last:
    the lines the undo or redo changed, as they are now. If the saved cursor is in or
    next to those lines, it goes back there. Otherwise it goes to the first changed
    line, on its first non-blank.
    """
    last_line = len(lines) - 1
    if saved is not None and first - 1 <= saved.line <= last + 1:
        line = saved.line
    else:
        line = first
        if saved is not None and saved.line + 1 == line and line > 0:
            # off by one line: back where the change was made (undoing an `o`)
            line = saved.line
    line = min(max(line, 0), last_line)
    text = lines[line]
    col = saved.col if saved is not None and saved.line == line else first_non_blank(text)
    return Pos(line, min(col, max(len(text) - 1, 0)))


def visual_start(anchor: Pos, cursor: Pos, linewise: bool) -> Pos:
    """Where an operator on a Visual selection starts: the cursor goes there after `y`,
    and `u` puts it back there.

    Part of a line: the start of the selection. Whole lines: the cursor if it's on a
    line above the other end, otherwise column 0 of the first line, like vim.
    """
    if not linewise:
        return min(anchor, cursor)
    if cursor.line < anchor.line:
        return cursor
    return Pos(anchor.line, 0)
