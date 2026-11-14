"""Splitting text into characters, and positions in Qt's UTF-16 counting."""

import pytest
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from side_vim.motions import Pos
from side_vim.text import Lines, split_clusters, utf16_len

FAMILY = "\U0001f468‍\U0001f469‍\U0001f467"
UA = "\U0001f1fa\U0001f1e6"
SMILE = "\U0001f600"
KEYCAP = "1️⃣"


def test_utf16_len() -> None:
    assert utf16_len("") == 0
    assert utf16_len("abc") == 3
    assert utf16_len("ї日") == 2
    assert utf16_len(SMILE) == 2
    assert utf16_len(FAMILY) == 8
    assert utf16_len(UA) == 4


@pytest.mark.parametrize(
    ("line", "clusters"),
    [
        ("", ()),
        ("abc", ("a", "b", "c")),
        ("éx", ("é", "x")),
        (f"a{FAMILY}b", ("a", FAMILY, "b")),
        (f"a{UA}b", ("a", UA, "b")),
        (f"{UA}{UA}", (UA, UA)),
        # Qt 6.12 splits a flag after an emoji; we pair it back
        (f"{SMILE}{UA}", (SMILE, UA)),
        (f"{SMILE}{UA}{UA}x", (SMILE, UA, UA, "x")),
        (f"{FAMILY}{UA}", (FAMILY, UA)),
        # an odd run: the last half stays alone
        (f"{UA}\U0001f1fa", (UA, "\U0001f1fa")),
        (KEYCAP + "x", (KEYCAP, "x")),
        ("日本", ("日", "本")),
        ("a\tb", ("a", "\t", "b")),
        ("x y", ("x", " ", "y")),
    ],
)
def test_split_clusters(line: str, clusters: tuple[str, ...]) -> None:
    assert split_clusters(line) == clusters
    assert "".join(clusters) == line


def test_lines_behave_like_a_sequence() -> None:
    lines = Lines(f"ab  {SMILE}x")
    assert len(lines) == 3
    assert lines[0] == ("a", "b")
    assert lines[1] == ()
    assert lines[2] == (SMILE, "x")
    assert lines[-1] == (SMILE, "x")
    assert lines[0:2] == [("a", "b"), ()]
    assert list(lines) == [("a", "b"), (), (SMILE, "x")]
    assert lines.raw(2) == f"{SMILE}x"
    with pytest.raises(IndexError):
        lines[3]
    with pytest.raises(IndexError):
        lines[-4]


DOC = f"a{SMILE}b\n\n{FAMILY}{UA}é\nx\ty{KEYCAP}"


def boundaries(lines: Lines) -> list[Pos]:
    """Every position between characters, line ends included."""
    return [Pos(i, col) for i in range(len(lines)) for col in range(len(lines[i]) + 1)]


def test_positions_match_qt_document(qapp: QApplication) -> None:
    doc = QTextDocument()
    doc.setPlainText(DOC)
    lines = Lines(doc.toRawText())
    assert len(lines) == doc.blockCount()
    for pos in boundaries(lines):
        position = lines.to_qt(pos)
        block = doc.findBlockByNumber(pos.line)
        offset = utf16_len("".join(lines[pos.line][: pos.col]))
        assert position == block.position() + offset
        cursor = QTextCursor(doc)
        cursor.setPosition(position)
        assert cursor.blockNumber() == pos.line
        assert cursor.positionInBlock() == offset
        assert lines.from_qt(position) == pos


def test_qt_cursor_steps_land_on_our_characters(qapp: QApplication) -> None:
    """Every place Qt's own cursor stops is a character boundary for us too, except
    inside a flag after an emoji (Qt's bug), which we read as the flag's start."""
    doc = QTextDocument()
    doc.setPlainText(DOC)
    lines = Lines(doc.toRawText())
    ours = {lines.to_qt(pos) for pos in boundaries(lines)}
    cursor = QTextCursor(doc)
    stops = [0]
    while cursor.movePosition(QTextCursor.MoveOperation.NextCharacter):
        stops.append(cursor.position())
    flag_start = lines.to_qt(Pos(2, 1))
    for stop in stops:
        if stop == flag_start + 2:
            assert lines.from_qt(stop) == Pos(2, 1)
        else:
            assert stop in ours


def test_inside_a_character_means_its_start() -> None:
    lines = Lines(f"a{FAMILY}b")
    start = lines.to_qt(Pos(0, 1))
    for inside in range(start + 1, start + utf16_len(FAMILY)):
        assert lines.from_qt(inside) == Pos(0, 1)
    assert lines.from_qt(start + utf16_len(FAMILY)) == Pos(0, 2)


def test_past_the_end_means_the_end() -> None:
    lines = Lines(f"ab {SMILE}")
    assert lines.from_qt(999) == Pos(1, 1)
    assert lines.to_qt(Pos(1, 1)) == 5


def test_soft_line_breaks_stay_inside_their_line(qapp: QApplication) -> None:
    editor = QPlainTextEdit()
    editor.setPlainText("x")
    cursor = editor.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" y\nz")
    doc = editor.document()
    # toPlainText() shows three lines, but there are two blocks
    assert editor.toPlainText().split("\n") == ["x", "y", "z"]
    assert doc.blockCount() == 2
    lines = Lines(doc.toRawText())
    assert len(lines) == 2
    assert lines[0] == ("x", " ", "y")
    assert lines.to_qt(Pos(1, 0)) == doc.findBlockByNumber(1).position()


def test_no_break_space_stays(qapp: QApplication) -> None:
    doc = QTextDocument()
    doc.setPlainText("a\xa0b")
    assert Lines(doc.toRawText())[0] == ("a", "\xa0", "b")


def test_lines_from_a_sequence_of_line_texts() -> None:
    lines = Lines([f"a{SMILE}", "", FAMILY])
    assert len(lines) == 3
    assert lines[0] == ("a", SMILE)
    assert lines[-1] == (FAMILY,)
    assert lines.raw(0) == f"a{SMILE}"
    assert lines.to_qt(Pos(2, 1)) == 3 + 1 + 1 + 8
    assert lines.from_qt(5) == Pos(2, 0)


def test_offset_and_col_at() -> None:
    lines = Lines(f"a{SMILE}{FAMILY}b")
    assert [lines.offset(Pos(0, c)) for c in range(5)] == [0, 1, 3, 11, 12]
    assert [lines.col_at(0, o) for o in range(13)] == [0, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 3, 4]
