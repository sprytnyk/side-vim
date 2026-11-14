"""n and N on plain text. Every case was checked against vim 9.1 (`vim -u NONE`), with
the pattern as literal text (`\\V`) and the direction set by `v:searchforward`."""

import pytest
from PySide6.QtWidgets import QApplication

from side_vim.motions import Pos
from side_vim.search import search
from side_vim.text import split_clusters

T = "foo bar foo\nbaz foo\nfoo"


@pytest.mark.parametrize(
    ("text", "line", "col", "keys", "pattern", "forward", "expected"),
    [
        # all vim
        (T, 0, 0, "n", "foo", True, (0, 8)),
        (T, 0, 0, "2n", "foo", True, (1, 4)),
        (T, 0, 0, "3n", "foo", True, (2, 0)),
        (T, 0, 0, "4n", "foo", True, (0, 0)),
        (T, 0, 0, "N", "foo", True, (2, 0)),
        (T, 0, 4, "N", "foo", True, (0, 0)),
        (T, 2, 0, "n", "foo", True, (0, 0)),
        (T, 0, 0, "n", "foo", False, (2, 0)),
        (T, 0, 0, "N", "foo", False, (0, 8)),
        (T, 1, 5, "n", "foo", True, (2, 0)),
        (T, 1, 4, "n", "foo", True, (2, 0)),
        (T, 1, 4, "N", "foo", True, (0, 8)),
        (T, 0, 1, "9n", "foo", True, (0, 8)),
        (T, 2, 2, "3N", "foo", True, (0, 8)),
        ("aaaa", 0, 0, "n", "aa", True, (0, 2)),
        ("aaaa", 0, 0, "2n", "aa", True, (0, 0)),
        ("aaaa", 0, 3, "N", "aa", True, (0, 2)),
        ("aaa", 0, 2, "N", "aa", True, (0, 0)),
        ("aaa", 0, 1, "N", "aa", True, (0, 0)),
        ("aaaa", 0, 1, "n", "aa", True, (0, 2)),
        ("xe\u0301e", 0, 0, "n", "e", True, (0, 2)),
        ("xe\u0301e", 0, 0, "2n", "e", True, (0, 2)),
        ("xe\u0301e", 0, 0, "n", "e\u0301", True, (0, 1)),
        ("\U0001f600a\U0001f600a", 0, 1, "n", "\U0001f600", True, (0, 2)),
        ("\u65e5\u672c \u65e5", 0, 0, "n", "\u65e5", True, (0, 3)),
        (T, 0, 1, "n", "foo", True, (0, 8)),
        (T, 0, 0, "n", "foo\nbaz", True, (0, 8)),
        (T, 0, 0, "n", "o\nb", True, (0, 10)),
        (T, 1, 0, "N", "o\nb", True, (0, 10)),
        ("ab\nab", 0, 0, "n", "b\na", True, (0, 1)),
        ("ab\nab", 0, 1, "n", "b\na", True, (0, 1)),
        ("ab\nab", 1, 1, "N", "b\na", True, (0, 1)),
        ("ab\nab", 1, 0, "N", "b\na", True, (0, 1)),
        ("xab\nab\nab", 1, 1, "n", "b\na", True, (0, 2)),
        ("aXa", 0, 0, "n", "a", True, (0, 2)),
        ("ab", 0, 0, "n", "b\n", True, (0, 1)),
        ("ab\ncd", 0, 0, "n", "b\n", True, (0, 1)),
        ("ab\ncd", 0, 0, "n", "\nc", True, (0, 1)),
        ("abc\n\nabc", 0, 0, "n", "\n\n", True, (0, 2)),
        ("x\n\ny", 2, 0, "N", "\n", True, (1, 0)),
        ("ab ab", 0, 4, "n", "ab", True, (0, 0)),
        ("ab ab", 0, 3, "N", "ab", True, (0, 0)),
        ("Foo foo", 0, 0, "n", "foo", True, (0, 4)),
        ("foo Foo", 0, 1, "n", "Foo", True, (0, 4)),
        ("a.b a*b", 0, 0, "n", "a*b", True, (0, 4)),
        ("a\\b", 0, 2, "n", "a\\b", True, (0, 0)),
        ("one\n\ntwo\n", 0, 0, "n", "\n", True, (0, 2)),
        ("one\n\ntwo\n", 3, 0, "N", "o", True, (2, 2)),
        ("  x\n  x", 1, 2, "n", "  x", True, (0, 0)),
        ("ab\tc\tab", 0, 0, "n", "\t", True, (0, 2)),
        ("ab\tc\tab", 0, 0, "2n", "\t", True, (0, 4)),
    ],
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
