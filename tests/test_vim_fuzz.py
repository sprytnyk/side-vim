"""Random keys on random texts in a real editor.

Motions must land where motions.move says (checked against vim on its own), which
tests every conversion to and from Qt's UTF-16 positions. Insert commands, operators
and paste, with emoji, flags and accents, must give the text, cursor and register a
simple model predicts. Random runs of commands must undo and redo step by step. Visual
mode must select what the model says after every key, and its operators must match it.
n, N and the scrolling keys must land where search.py and scroll.py say.
"""

import random
from collections.abc import Iterator

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QPlainTextEdit
from qtkeys import cursor_of, plain, put_cursor, send, text_of, type_text
from test_motions_fuzz import CHARS, delete, random_lines, whole

import side_vim.vim as vim_module
from side_vim import Mode, VimMode
from side_vim.edits import Register, visual_start
from side_vim.motions import (
    MOTIONS,
    Line,
    Pos,
    column_for,
    first_non_blank,
    line_range,
    move,
    operator_range,
    range_text,
    screen_col,
    visual_range,
)
from side_vim.parser import LINE
from side_vim.scroll import SCROLL_KEYS, scroll
from side_vim.search import search
from side_vim.text import Lines, split_clusters

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


def type_chars(editor: QPlainTextEdit, chars: list[str]) -> None:
    for ch in chars:
        if ch == "\t":
            send(editor, "<Tab>")
        elif ch.isascii():
            send(editor, ch)
        else:
            type_text(editor, ch)


def split(text: str) -> list[tuple[str, ...]]:
    return [split_clusters(line) for line in text.split("\n")]


def on_a_char(lines: list[tuple[str, ...]], pos: Pos) -> Pos:
    """pos kept on a character, as Normal mode keeps the cursor."""
    line = min(pos.line, len(lines) - 1)
    return Pos(line, min(pos.col, max(len(lines[line]) - 1, 0)))


def operator_model(
    lines: list[tuple[str, ...]],
    pos: Pos,
    op: str,
    motion: str,
    count: int | None,
    typed: list[str],
) -> tuple[str, Pos, Register | None] | None:
    """What vim does for one d, c or y command (c types `typed`, then Esc). None if
    the motion fails. The register is None if the command leaves it alone."""
    if motion == LINE:
        r = line_range(lines, pos, count)
        if r is None:
            return None
        start = pos if op == "y" else min(pos, Pos(r.end.line, first_non_blank(lines[r.end.line])))
    else:
        moved = move(lines, pos, motion, count, op=op, tabstop=TABSTOP)
        if moved is None:
            return None
        r = operator_range(lines, pos, moved, op)
        start = min(pos, moved.pos)
    # Recorded empty-buffer cases keep the old register for deletes and changes.
    empty = not as_text(lines) or (not r.linewise and r.start == r.end)
    register = None if empty and op != "y" else Register(range_text(lines, r), r.linewise)
    rows = ["".join(line) for line in lines]
    a, b = r.start.line, r.end.line
    if op == "y":
        return as_text(lines), on_a_char(lines, start), register
    if op == "d":
        if empty:
            return as_text(lines), pos, register
        text = delete(lines, r.start, r.end, r.linewise)
        new = split(text)
        if r.linewise:
            line = min(a, len(new) - 1)
            return text, Pos(line, first_non_blank(new[line])), register
        return text, on_a_char(new, r.start), register
    added = "".join(typed)
    if r.linewise:
        rows[a : b + 1] = [added]
        return "\n".join(rows), Pos(a, max(len(typed) - 1, 0)), register
    head = "".join(lines[a][: r.start.col])
    tail = "".join(lines[b][r.end.col :])
    rows[a : b + 1] = [head + added + tail]
    return "\n".join(rows), Pos(a, max(r.start.col + len(typed) - 1, 0)), register


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_operators_match_the_model(editor: QPlainTextEdit, seed: int) -> None:
    rng = random.Random(2000 + seed)
    motions = [*sorted(MOTIONS), LINE]
    for _ in range(25):
        lines = random_lines(rng)
        editor.setPlainText(as_text(lines))
        vim = VimMode(editor)
        pos = random_pos(rng, lines)
        put_cursor(editor, pos)
        op = rng.choice("dcy")
        motion = rng.choice(motions)
        count = None if motion == "0" else rng.choice((None, 2, 3))
        typed = [rng.choice(CHARS) for _ in range(rng.randint(0, 2))] if op == "c" else []
        vim_module._register = Register("before", linewise=False)

        keys = f"{count or ''}{op}{op if motion == LINE else motion}"
        send(editor, keys)
        expected = operator_model(lines, pos, op, motion, count, typed)
        what = (lines, pos, keys, typed)
        if expected is None:
            assert vim.mode is Mode.NORMAL, what
            assert text_of(editor) == as_text(lines), what
            vim.detach()
            continue
        if op == "c":
            assert vim.mode is Mode.INSERT, what
            type_chars(editor, typed)
            send(editor, "<Esc>")
        text, cursor, register = expected
        assert text_of(editor) == text, what
        assert whole(text_of(editor)), what
        assert cursor_of(editor) == cursor, what
        assert vim_module._register == (register or Register("before", linewise=False)), what
        assert vim.mode is Mode.NORMAL, what
        if text != as_text(lines):
            send(editor, "u")
            assert text_of(editor) == as_text(lines), what
            send(editor, "<C-r>")
            assert text_of(editor) == text, what
        vim.detach()


def random_register(rng: random.Random) -> Register:
    if rng.random() < 0.4:
        rows = ["".join(line) for line in random_lines(rng)]
        return Register("\n".join(rows) + "\n", linewise=True)
    chars = [rng.choice(CHARS) for _ in range(rng.randint(1, 4))]
    if rng.random() < 0.3:
        chars.insert(rng.randrange(len(chars) + 1), "\n")
    return Register("".join(chars), linewise=False)


def paste_model(
    lines: list[tuple[str, ...]], pos: Pos, register: Register, after: bool, count: int
) -> tuple[str, Pos]:
    rows = ["".join(line) for line in lines]
    if register.linewise:
        body = register.text.removesuffix("\n").split("\n") * count
        at = pos.line + 1 if after else pos.line
        rows[at:at] = body
        return "\n".join(rows), Pos(at, first_non_blank(split_clusters(body[0])))
    line: Line = lines[pos.line]
    col = min(pos.col + 1, len(line)) if after else pos.col
    chunk = register.text * count
    rows[pos.line] = "".join(line[:col]) + chunk + "".join(line[col:])
    text = "\n".join(rows)
    if "\n" in chunk:
        # the start of the paste, kept on a character (vim does that too)
        return text, on_a_char(split(text), Pos(pos.line, col))
    return text, Pos(pos.line, col + len(split_clusters(chunk)) - 1)


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_paste_matches_the_model(editor: QPlainTextEdit, seed: int) -> None:
    rng = random.Random(3000 + seed)
    for _ in range(15):
        lines = random_lines(rng)
        editor.setPlainText(as_text(lines))
        vim = VimMode(editor)
        pos = random_pos(rng, lines)
        put_cursor(editor, pos)
        register = random_register(rng)
        vim_module._register = register
        after = rng.random() < 0.5
        count = rng.choice((1, 1, 2, 3))
        keys = f"{count if count > 1 else ''}{'p' if after else 'P'}"
        send(editor, keys)
        text, cursor = paste_model(lines, pos, register, after, count)
        what = (lines, pos, register, keys)
        assert text_of(editor) == text, what
        assert whole(text_of(editor)), what
        assert cursor_of(editor) == cursor, what
        assert vim_module._register == register
        send(editor, "u")
        assert text_of(editor) == as_text(lines), what
        vim.detach()


def random_command(rng: random.Random) -> list[str]:
    """One command as keys to send, with typed characters as their own items."""

    def typed() -> list[str]:
        return [rng.choice(CHARS) for _ in range(rng.randint(0, 3))]

    simple = ["x", "3x", "dw", "d2w", "db", "dd", "2dd", "D", "J", "3J", "p", "P", "yyp", "ywP"]
    simple += ["vld", "vjd", "Vd", "Vjd", "vlp", "Vp", "v$y", "vey"]
    roll = rng.random()
    if roll < 0.5:
        return [rng.choice(simple)]
    start = rng.choice(
        ["i", "a", "A", "I", "o", "O", "2i", "2o", "cw", "cc", "C", "c2w", "cb", "vlc", "Vjc"]
    )
    middle = typed()
    if rng.random() < 0.4:
        middle += [rng.choice(["<CR>", "<BS>", "<Left>", "<Right>", "<Del>"]), *typed()]
    return [start, *middle, "<Esc>"]


def press_all(editor: QPlainTextEdit, keys: list[str]) -> None:
    for key in keys:
        if key in CHARS:
            type_chars(editor, [key])
        else:
            send(editor, key)


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_undo_and_redo_walk_every_step(editor: QPlainTextEdit, seed: int) -> None:
    """After random commands, u goes back one command at a time to the start, and
    Ctrl+R forward again; so does the document's own undo and redo."""
    rng = random.Random(4000 + seed)
    lines = random_lines(rng)
    editor.setPlainText(as_text(lines))
    vim = VimMode(editor)
    vim_module._register = random_register(rng)
    states = [text_of(editor)]
    done: list[list[str]] = []
    split_by_qt = False
    for _ in range(12):
        now = split(text_of(editor))
        put_cursor(editor, random_pos(rng, now))
        keys = random_command(rng)
        press_all(editor, keys)
        assert vim.mode is Mode.NORMAL
        # In Insert mode these keys are the editor's own. Qt's Backspace and Delete
        # take an accent off its letter, and its arrows can stop inside a flag that
        # follows an emoji (Qt 6.12), so typing splits it. That then stays in the text.
        split_by_qt = split_by_qt or bool({"<BS>", "<Del>", "<Left>", "<Right>"} & set(keys))
        if not split_by_qt:
            assert whole(text_of(editor)), (states[-1], keys)
        # one undo step per command that changed something; `Vp` putting back the
        # same text is a step too, as in vim
        steps = len(vim._done)
        assert steps - len(done) in (0, 1), (states[-1], keys)
        assert steps > len(done) or text_of(editor) == states[-1], (states[-1], keys)
        if steps > len(done):
            states.append(text_of(editor))
            done.append(keys)

    def cursor_ok() -> None:
        pos = cursor_of(editor)
        assert pos == on_a_char(split(text_of(editor)), pos)

    for state in reversed(states[:-1]):
        send(editor, "u")
        assert text_of(editor) == state, (states, done)
        cursor_ok()
    send(editor, "u")
    assert text_of(editor) == states[0]
    for state in states[1:]:
        send(editor, "<C-r>")
        assert text_of(editor) == state, (states, done)
        cursor_ok()

    document = editor.document()
    for state in reversed(states[:-1]):
        document.undo()
        assert text_of(editor) == state, (states, done)
    assert not document.isUndoAvailable()
    for state in states[1:]:
        document.redo()
        assert text_of(editor) == state, (states, done)
    vim.detach()


def visual_model(
    lines: list[tuple[str, ...]],
    anchor: Pos,
    end: Pos,
    linewise: bool,
    op: str,
    typed: list[str],
    register: Register,
    count: int,
) -> tuple[str, Pos, Register]:
    """What vim does for d, y, c (typing `typed`, then Esc) and p on a selection."""
    r = visual_range(lines, anchor, end, linewise)
    start = visual_start(anchor, end, linewise)
    empty = not as_text(lines) or (not r.linewise and r.start == r.end)
    taken = register if empty else Register(range_text(lines, r), r.linewise)
    rows = ["".join(line) for line in lines]
    a, b = r.start.line, r.end.line
    head = "".join(lines[a][: r.start.col])
    tail = "".join(lines[b][r.end.col :])
    if op == "y":
        return as_text(lines), on_a_char(lines, start), Register(range_text(lines, r), r.linewise)
    if op == "p" and register.text:
        body = register.text.removesuffix("\n") if register.linewise else register.text
        if r.linewise:
            new = "\n".join([body] * count).split("\n")
            rows[a : b + 1] = new
            return "\n".join(rows), Pos(a, first_non_blank(split_clusters(new[0]))), taken
        middle = body * count
        if register.linewise:
            # a new empty text has no lines to split: vim puts them below an empty one
            middle = "\n" + "\n".join([body] * count) + ("\n" if as_text(lines) else "")
        rows[a : b + 1] = (head + middle + tail).split("\n")
        text = "\n".join(rows)
        if register.linewise:
            return text, Pos(a + 1, first_non_blank(split(text)[a + 1])), taken
        if "\n" in middle:
            return text, on_a_char(split(text), r.start), taken
        return text, Pos(a, r.start.col + len(split_clusters(middle)) - 1), taken
    if op in "dp":
        if empty:
            return as_text(lines), on_a_char(lines, start), taken
        text = delete(lines, r.start, r.end, r.linewise)
        new = split(text)
        if r.linewise:
            line = min(a, len(new) - 1)
            return text, Pos(line, first_non_blank(new[line])), taken
        return text, on_a_char(new, r.start), taken
    added = "".join(typed)
    if r.linewise:
        rows[a : b + 1] = [added]
        return "\n".join(rows), Pos(a, max(len(typed) - 1, 0)), taken
    rows[a : b + 1] = [head + added + tail]
    return "\n".join(rows), Pos(a, max(r.start.col + len(typed) - 1, 0)), taken


def shown(editor: QPlainTextEdit, vim: VimMode) -> tuple[int, int, int | None]:
    """The editor's anchor and position, and where vim's cursor is drawn."""
    cursor = editor.textCursor()
    caret = vim._caret
    return cursor.anchor(), cursor.position(), caret.position if caret.isVisible() else None


def expected_shown(
    lines: list[tuple[str, ...]], anchor: Pos, end: Pos, linewise: bool
) -> tuple[int, int, int]:
    qt = Lines(["".join(line) for line in lines])
    r = visual_range(lines, anchor, end, linewise)
    if linewise:
        low = qt.to_qt(Pos(r.start.line, 0))
        high = qt.to_qt(Pos(r.end.line, len(lines[r.end.line])))
    else:
        low, high = qt.to_qt(r.start), qt.to_qt(r.end)
    anchor_qt, position_qt = (low, high) if anchor <= end else (high, low)
    return anchor_qt, position_qt, qt.to_qt(end)


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_visual_mode_matches_the_model(editor: QPlainTextEdit, seed: int) -> None:
    rng = random.Random(5000 + seed)
    motions = sorted(MOTIONS)
    for _ in range(10):
        lines = random_lines(rng)
        editor.setPlainText(as_text(lines))
        vim = VimMode(editor)
        pos = random_pos(rng, lines)
        put_cursor(editor, pos)
        linewise = rng.random() < 0.3
        send(editor, "V" if linewise else "v")
        anchor = end = pos
        want: int | None = None
        keys = ["V" if linewise else "v"]
        for _ in range(rng.randint(0, 6)):
            roll = rng.random()
            if roll < 0.1:
                key = "o"
                anchor, end = end, anchor
                want = None
            elif roll < 0.2:
                key = "v" if linewise else "V"
                linewise = not linewise
            else:
                motion = rng.choice(motions)
                count = None if motion == "0" else rng.choice((None, None, 2, 3))
                key = f"{count or ''}{motion}"
                moved = move(lines, end, motion, count, want=want, visual=True, tabstop=TABSTOP)
                if moved is not None:
                    end, want = moved.pos, moved.want
            send(editor, key)
            keys.append(key)
            assert vim.mode is (Mode.VISUAL_LINE if linewise else Mode.VISUAL), keys
            assert shown(editor, vim) == expected_shown(lines, anchor, end, linewise), (lines, keys)

        op = rng.choice(["d", "x", "y", "c", "p", "p", "<Esc>"])
        register = random_register(rng)
        vim_module._register = register
        count = rng.choice((1, 1, 2)) if op == "p" else 1
        typed = [rng.choice(CHARS) for _ in range(rng.randint(0, 2))] if op == "c" else []
        send(editor, f"{count if count > 1 else ''}{op}")
        keys.append(op)
        what = (lines, pos, keys, typed, register)
        if op == "c":
            assert vim.mode is Mode.INSERT, what
            type_chars(editor, typed)
            send(editor, "<Esc>")
        assert vim.mode is Mode.NORMAL, what
        assert shown(editor, vim)[2] is None, what
        if op == "<Esc>":
            assert text_of(editor) == as_text(lines), what
            assert cursor_of(editor) == on_a_char(lines, end), what
            vim.detach()
            continue
        model = "d" if op == "x" else op
        text, cursor, after = visual_model(
            lines, anchor, end, linewise, model, typed, register, count
        )
        assert text_of(editor) == text, what
        assert whole(text_of(editor)), what
        assert cursor_of(editor) == cursor, what
        assert vim_module._register == after, what
        if text != as_text(lines):
            send(editor, "u")
            assert text_of(editor) == as_text(lines), what
            send(editor, "<C-r>")
            assert text_of(editor) == text, what
        vim.detach()


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_a_selection_made_outside_vim_is_kept(editor: QPlainTextEdit, seed: int) -> None:
    """A selection from the mouse or the app, at any character edges: Visual mode keeps
    the same characters selected, and y yanks them."""
    rng = random.Random(6000 + seed)
    for _ in range(10):
        lines = random_lines(rng)
        editor.setPlainText(as_text(lines))
        vim = VimMode(editor)
        send(editor, "v")
        qt = Lines(["".join(line) for line in lines])
        edges = sorted(
            {qt.to_qt(Pos(i, col)) for i, line in enumerate(lines) for col in range(len(line) + 1)}
        )
        if len(edges) < 2:  # an empty text: nothing to select
            vim.detach()
            continue
        a, b = rng.sample(edges, 2)
        cursor = editor.textCursor()
        cursor.setPosition(a)
        cursor.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        what = (lines, a, b)
        assert vim.mode is Mode.VISUAL, what
        after = editor.textCursor()
        assert (after.anchor(), after.position()) == (a, b), what
        selected = plain(after.selectedText())
        send(editor, "y")
        assert vim_module._register == Register(selected, linewise=False), what
        vim.detach()


def random_pattern(rng: random.Random, lines: list[tuple[str, ...]]) -> str:
    """Mostly a piece of the text, sometimes over a line break; sometimes anything."""
    if rng.random() < 0.2:
        return "".join(rng.choice(CHARS) for _ in range(rng.randint(1, 2)))
    i = rng.randrange(len(lines))
    line = lines[i]
    start = rng.randrange(len(line) + 1)
    piece = "".join(line[start : start + rng.randint(1, 3)])
    if (start + 3 >= len(line) or not piece) and i + 1 < len(lines) and rng.random() < 0.5:
        piece += "\n" + "".join(lines[i + 1][: rng.randint(0, 2)])
    return piece or "".join(line) or "a"


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_n_and_n_match_the_model(editor: QPlainTextEdit, seed: int) -> None:
    rng = random.Random(7000 + seed)
    for _ in range(10):
        lines = random_lines(rng)
        editor.setPlainText(as_text(lines))
        vim = VimMode(editor)
        pattern = random_pattern(rng, lines)
        forward = rng.random() < 0.7
        pos = random_pos(rng, lines)
        put_cursor(editor, pos)
        found = search(lines, pos, [split_clusters(p) for p in pattern.split("\n")], forward)
        vim.set_search(pattern, forward)
        assert cursor_of(editor) == (found or pos), (lines, pattern, forward, pos)
        put_cursor(editor, random_pos(rng, lines))
        parts = [split_clusters(part) for part in pattern.split("\n")]
        for _ in range(4):
            pos = cursor_of(editor)
            key = rng.choice(["n", "N", "2n", "3N"])
            found = search(lines, pos, parts, forward == (key[-1] == "n"), int(key[:-1] or 1))
            send(editor, key)
            what = (lines, pattern, forward, pos, key)
            assert cursor_of(editor) == (found or pos), what
        assert text_of(editor) == as_text(lines)
        vim.detach()


def long_lines(rng: random.Random) -> list[tuple[str, ...]]:
    return [
        tuple(rng.choice(CHARS) for _ in range(rng.randint(0, 6)))
        for _ in range(rng.randint(1, 80))
    ]


@pytest.mark.parametrize("seed", range(SEED_COUNT))
def test_scrolling_matches_the_model(editor: QPlainTextEdit, seed: int) -> None:
    rng = random.Random(8000 + seed)
    keys = sorted(SCROLL_KEYS)
    for _ in range(4):
        lines = long_lines(rng)
        editor.setPlainText(as_text(lines))
        vim = VimMode(editor)
        put_cursor(editor, random_pos(rng, lines))
        want: int | None = None
        amount: int | None = None
        for _ in range(10):
            top, height, max_top = vim._view()
            pos = cursor_of(editor)
            key = rng.choice(keys)
            count = rng.choice((None, None, 2, 5))
            scrolled = scroll(
                key,
                count,
                top=top,
                line=pos.line,
                height=height,
                lines=len(lines),
                max_top=max_top,
                amount=amount,
            )
            send(editor, f"{count or ''}{key}")
            what = (len(lines), top, height, max_top, pos, key, count)
            if scrolled is None:
                assert cursor_of(editor) == pos, what
                assert editor.firstVisibleBlock().blockNumber() == top, what
                continue
            amount = scrolled.amount
            assert editor.firstVisibleBlock().blockNumber() == scrolled.top, what
            # lines with emoji can be taller: the cursor stays on a line fully on screen
            first, last, _ = vim._visible()
            line = min(max(scrolled.line, first), last)
            if not scrolled.keep_column:
                expected = Pos(line, first_non_blank(lines[line]))
                want = None
            elif line != pos.line:
                if want is None:
                    want = screen_col(lines[pos.line], pos.col, TABSTOP)
                expected = Pos(line, column_for(lines[line], want, False, TABSTOP))
            else:
                expected = pos
            assert cursor_of(editor) == expected, what
        vim.detach()
