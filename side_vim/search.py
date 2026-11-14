"""n and N: find the next match of a plain text, like vim. No Qt here.

The text and the pattern are lines of characters (grapheme clusters), as in motions.py,
so "e" doesn't match the "e" in "e" plus an accent, just as in vim. A newline in the
pattern matches a line break. vim treats every line as ending in one, the last line
too, and so does this.

vim's defaults decide which match comes next: 'wrapscan', so the search goes on from
the other end, and 'cpoptions' with "c", so the matches in a line are found one after
the other from its start, each one after the end of the one before. In "aaaa", `n` for
"aa" goes from column 0 to column 2, not 1.
"""

from bisect import bisect_right
from collections.abc import Iterator, Sequence

from side_vim.motions import Line, Pos

NEWLINE = "\n"


class _Text:
    """The lines as one list of characters, with a NEWLINE after each line."""

    def __init__(self, lines: Sequence[Line]) -> None:
        self.lines: Sequence[Line] = lines
        self.chars: list[str] = []
        self.starts: list[int] = []
        for line in lines:
            self.starts.append(len(self.chars))
            self.chars.extend(line)
            self.chars.append(NEWLINE)

    def index(self, pos: Pos) -> int:
        return self.starts[pos.line] + pos.col

    def line_of(self, index: int) -> int:
        return bisect_right(self.starts, index) - 1

    def matches(self, line: int, pattern: list[str]) -> Iterator[tuple[int, bool]]:
        """The matches that start in a line, one after the other from its start: the
        index of each, and whether it goes on past the line's end."""
        end = self.starts[line] + len(self.lines[line])  # the line's NEWLINE
        i = self.starts[line]
        size = len(pattern)
        while i <= end:
            if self.chars[i : i + size] == pattern:
                more = i + size > end
                yield i, more
                if more:
                    return
                i += size
            else:
                i += 1


def search(
    lines: Sequence[Line],
    pos: Pos,
    pattern: Sequence[Line],
    forward: bool = True,
    count: int | None = None,
) -> Pos | None:
    """Where `n` (forward) or `N` goes from pos for a pattern given as lines of
    characters. None if the pattern is empty or not in the text."""
    chars = [ch for i, part in enumerate(pattern) for ch in ([NEWLINE] if i else []) + list(part)]
    if not chars:
        return None
    text = _Text(lines)
    at = text.index(pos)
    for _ in range(count or 1):
        found = _forward(text, at, chars) if forward else _backward(text, at, chars)
        if found is None:
            return None
        at = found
    line = text.line_of(at)
    col = at - text.starts[line]
    # a match that starts on the line break puts the cursor on the last character
    if col == len(lines[line]) and col > 0:
        col -= 1
    return Pos(line, col)


def _forward(text: _Text, at: int, pattern: list[str]) -> int | None:
    line = text.line_of(at)
    end = text.starts[line] + len(text.lines[line])
    for i, more in text.matches(line, pattern):
        # on the line break, a match counts as on the character before it
        if i - (i == end) > at:
            return i
        if more:
            break
    count = len(text.lines)
    for step in range(1, count + 1):
        first = next(text.matches((line + step) % count, pattern), None)
        if first is not None:
            return first[0]
    return None


def _backward(text: _Text, at: int, pattern: list[str]) -> int | None:
    line = text.line_of(at)
    found = None
    if at > text.starts[line]:
        for i, _ in text.matches(line, pattern):
            if i >= at:
                break
            found = i
    if found is not None:
        return found
    count = len(text.lines)
    for step in range(1, count + 1):
        last = None
        for i, _ in text.matches((line - step) % count, pattern):
            last = i
        if last is not None:
            return last
    return None
