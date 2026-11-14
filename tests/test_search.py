"""n and N on plain text. Every case was checked against vim 9.1 (`vim -u NONE`), with
the pattern as literal text (`\\V`) and the direction set by `v:searchforward`."""

import pytest
from casefiles import search_rows
from PySide6.QtWidgets import QApplication

from side_vim.motions import Pos
from side_vim.search import search
from side_vim.text import split_clusters


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "pattern", "forward", "expected"),
    search_rows(),
)
def test_vim(
    qapp: QApplication,
    text: str,
    line: int,
    col: int,
    keys: str,
    pattern: str,
    forward: bool,
    expected: tuple[int, int],
) -> None:
    lines = [split_clusters(row) for row in text.split("\n")]
    count = int(keys[:-1]) if len(keys) > 1 else None
    found = search(
        lines,
        Pos(line, col),
        [split_clusters(part) for part in pattern.split("\n")],
        forward=forward == (keys[-1] == "n"),
        count=count,
    )
    assert (found or Pos(line, col)) == Pos(*expected)


def test_no_match_and_no_pattern() -> None:
    assert search(["abc"], Pos(0, 0), ["x"]) is None
    assert search(["abc"], Pos(0, 0), [""]) is None
    assert search(["abc"], Pos(0, 0), []) is None
