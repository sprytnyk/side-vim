"""The editor's text as vim lines, and positions in Qt's terms.

Uses QtCore only, never the editor. Two things make this more than str.split("\\n"):

- Qt counts positions in UTF-16 code units, so an emoji is 2 positions and a family
  emoji is 8, while Python counts code points. Every position goes through here.
- One character on screen (a grapheme cluster: a family emoji, a flag, a letter plus
  an accent) is one character for vim, so commands never cut one in half. Qt decides
  where clusters end, the same way its own cursor does.

Read the editor's text with document().toRawText(), not toPlainText(): toPlainText()
turns a line separator (U+2028, a soft line break inside a block) into "\\n", so its
lines no longer match Qt's blocks.
"""

from collections.abc import Iterator, Sequence
from typing import overload

from PySide6.QtCore import QTextBoundaryFinder

from side_vim.motions import Pos

# What separates blocks (vim's lines) in QTextDocument.toRawText().
PARAGRAPH_SEPARATOR = " "


def utf16_len(s: str) -> int:
    """Length in UTF-16 code units, the way Qt counts."""
    return len(s.encode("utf-16-le", "surrogatepass")) // 2


def split_clusters(line: str) -> tuple[str, ...]:
    """Split a line into the characters the user sees, as Qt finds them."""
    if not line:
        return ()
    finder = QTextBoundaryFinder(QTextBoundaryFinder.BoundaryType.Grapheme, line)
    # the finder speaks UTF-16; map its boundaries back to code point indexes
    ends: set[int] = set()
    while (boundary := finder.toNextBoundary()) != -1:
        ends.add(boundary)
    clusters: list[str] = []
    start = offset = 0
    for i, ch in enumerate(line):
        offset += 2 if ord(ch) > 0xFFFF else 1
        if offset in ends:
            clusters.append(line[start : i + 1])
            start = i + 1
    if start < len(line):
        clusters.append(line[start:])
    return tuple(_pair_flags(clusters))


def _is_flag_half(cluster: str) -> bool:
    return all(0x1F1E6 <= ord(ch) <= 0x1F1FF for ch in cluster)


def _pair_flags(clusters: list[str]) -> list[str]:
    """Pair regional indicators (the two halves of a flag) from the start of each run.

    Qt 6.12 gets this wrong after an emoji: it splits "😀🇺🇦" into 😀, 🇺, 🇦, and its
    own cursor does the same, so a plain QPlainTextEdit can break a flag. Unicode
    pairs them from the start of the run, so vim commands always take a flag whole.
    """
    out: list[str] = []
    run: list[str] = []
    for cluster in [*clusters, ""]:
        if cluster and _is_flag_half(cluster):
            run.extend(cluster)
            continue
        out.extend("".join(run[i : i + 2]) for i in range(0, len(run), 2))
        run = []
        if cluster:
            out.append(cluster)
    return out


class Lines(Sequence[tuple[str, ...]]):
    """The document's lines, each split into clusters when first used.

    raw: QTextDocument.toRawText(), with blocks separated by U+2029. Or the lines'
    texts as a sequence that reads them when asked, so that a long document isn't
    copied for every key. Such a sequence must not change while this is in use.
    """

    def __init__(self, raw: str | Sequence[str]) -> None:
        self._raw: Sequence[str] = raw.split(PARAGRAPH_SEPARATOR) if isinstance(raw, str) else raw
        self._split: dict[int, tuple[str, ...]] = {}

    def __len__(self) -> int:
        return len(self._raw)

    @overload
    def __getitem__(self, index: int) -> tuple[str, ...]: ...
    @overload
    def __getitem__(self, index: slice) -> list[tuple[str, ...]]: ...
    def __getitem__(self, index: int | slice) -> tuple[str, ...] | list[tuple[str, ...]]:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self._raw):
            raise IndexError(index)
        line = self._split.get(index)
        if line is None:
            line = self._split[index] = split_clusters(self._raw[index])
        return line

    def __iter__(self) -> Iterator[tuple[str, ...]]:
        return (self[i] for i in range(len(self)))

    def raw(self, index: int) -> str:
        """A line as plain text."""
        return self._raw[index]

    def offset(self, pos: Pos) -> int:
        """A column as a UTF-16 offset in its line. Past the line end means the end."""
        return utf16_len("".join(self[pos.line][: pos.col]))

    def col_at(self, line: int, offset: int) -> int:
        """The column at a UTF-16 offset in a line. Inside a cluster (which Qt's own
        cursor never does, but an app could) means the start of that cluster."""
        end = col = 0
        for cluster in self[line]:
            end += utf16_len(cluster)
            if end > offset:
                break
            col += 1
        return col

    def to_qt(self, pos: Pos) -> int:
        """A position as a Qt document position. A column past the line end means the
        line end. The editor asks the document where lines start instead, which is
        faster in long texts."""
        start = sum(utf16_len(line) + 1 for line in self._raw[: pos.line])
        return start + self.offset(pos)

    def from_qt(self, position: int) -> Pos:
        """A Qt document position as a position. Past the end of the document means its
        end."""
        for index, raw in enumerate(self._raw):
            length = utf16_len(raw)
            if position <= length:
                return Pos(index, self.col_at(index, position))
            position -= length + 1
        last = len(self._raw) - 1
        return Pos(last, len(self[last]))
