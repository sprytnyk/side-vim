"""Random keys on random texts in a real editor.

Motions must land where motions.move says (checked against vim on its own), which
tests every conversion to and from Qt's UTF-16 positions. Insert commands with typed
emoji, flags and accents must give the text and cursor a simple model predicts.
"""

import random
from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from qtkeys import cursor_of, put_cursor, send, text_of, type_text
from test_motions_fuzz import CHARS, random_lines

from side_vim import Mode, VimMode
from side_vim.motions import MOTIONS, Pos, move
from side_vim.text import split_clusters

SEED_COUNT = 30
SAMPLES = 60
TABSTOP = 8


@pytest.fixture
def editor(qapp: QApplication) -> Iterator[QPlainTextEdit]:
    e = QPlainTextEdit()
    e.setTabStopDistance(e.fontMetrics().horizontalAdvance(" ") * TABSTOP)
    e.resize(500, 300)
    e.show()
    yield e
    e.close()
    e.deleteLater()


def random_pos(rng: random.Random, lines: list[tuple[str, ...]]) -> Pos:
    line = rng.randrange(len(lines))
    return Pos(line, rng.randrange(max(len(lines[line]), 1)))


def as_text(lines: list[tuple[str, ...]]) -> str:
    return "\n".join("".join(line) for line in lines)


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_motions_match_the_model(editor: QPlainTextEdit, seed: int) -> None:
    rng = random.Random(seed)
    lines = random_lines(rng)
    editor.setPlainText(as_text(lines))
    vim = VimMode(editor)
    motions = sorted(MOTIONS)
    # the column j and k aim for stays while the cursor stays where vim put it
    want: int | None = None
    at = cursor_of(editor)
    for _ in range(SAMPLES):
        pos = at if rng.random() < 0.5 else random_pos(rng, lines)
        if pos != at:
            want = None
        put_cursor(editor, pos)
        assert cursor_of(editor) == pos
        motion = rng.choice(motions)
        # a 0 after a count is part of the count, as in vim
        count = None if motion == "0" else rng.choice((None, 2, 5))
        moved = move(lines, pos, motion, count, want=want, tabstop=TABSTOP)
        send(editor, f"{count or ''}{motion}")
        if moved is not None:
            want = moved.want
        at = pos if moved is None else moved.pos
        assert cursor_of(editor) == at, (lines, pos, motion, count, want)
        assert vim.mode is Mode.NORMAL
    assert text_of(editor) == as_text(lines)
    vim.detach()


def insert_model(
    lines: list[tuple[str, ...]], pos: Pos, command: str, typed: list[str], count: int
) -> tuple[str, Pos]:
    """What vim does for a count, an insert command, typing and Esc."""
    rows = [list(line) for line in lines]
    text = rows[pos.line]
    if command in "oO":
        new = [list(typed) for _ in range(count)]
        at = pos.line + 1 if command == "o" else pos.line
        rows[at:at] = new
        cursor = Pos(at + count - 1, max(len(typed) - 1, 0))
        return "\n".join("".join(r) for r in rows), cursor
    if command == "i":
        col = pos.col
    elif command == "a":
        col = min(pos.col + 1, len(text))
    elif command == "I":
        col = next((i for i, ch in enumerate(text) if ch not in " \t"), len(text))
    else:
        col = len(text)
    added = typed * count
    rows[pos.line] = text[:col] + added + text[col:]
    return "\n".join("".join(r) for r in rows), Pos(pos.line, max(col + len(added) - 1, 0))


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_insert_commands_match_the_model(editor: QPlainTextEdit, seed: int) -> None:
    rng = random.Random(1000 + seed)
    for _ in range(8):
        lines = random_lines(rng)
        editor.setPlainText(as_text(lines))
        vim = VimMode(editor)
        pos = random_pos(rng, lines)
        put_cursor(editor, pos)
        command = rng.choice("iaIAoO")
        count = rng.choice((1, 1, 2, 3))
        typed = [rng.choice(CHARS) for _ in range(rng.randint(0, 3))]

        send(editor, f"{count if count > 1 else ''}{command}")
        assert vim.mode is Mode.INSERT
        for ch in typed:
            if ch == "\t":
                send(editor, "<Tab>")
            elif ch.isascii():
                send(editor, ch)
            else:
                type_text(editor, ch)
        send(editor, "<Esc>")

        text, cursor = insert_model(lines, pos, command, typed, count)
        # the typed characters must stay whole (a typed flag after an emoji, say)
        assert [split_clusters(line) for line in text_of(editor).split("\n")] == [
            split_clusters(line) for line in text.split("\n")
        ]
        assert text_of(editor) == text, (lines, pos, command, typed, count)
        assert cursor_of(editor) == cursor, (lines, pos, command, typed, count)
        assert vim.mode is Mode.NORMAL
        vim.detach()
