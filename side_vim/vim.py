"""VimMode: vim keys for a QPlainTextEdit. The only module that talks to the editor.

It sits on the editor as an event filter. In Normal mode it takes the keys, turns them
into commands with the parser, and moves the editor's cursor with the motions. In
Insert mode the editor types as usual, and only Esc (or Ctrl+[) is taken.

Every position goes through text.Lines, which works in whole characters (a family
emoji is one) and converts to Qt's UTF-16 positions.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
from typing import overload

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QKeyEvent, QTextDocument
from PySide6.QtWidgets import QPlainTextEdit

from side_vim.keys import ESC, key_token
from side_vim.mode import Mode
from side_vim.motions import BLANKS, Pos, move
from side_vim.parser import Command, Parser
from side_vim.text import PARAGRAPH_SEPARATOR, Lines, split_clusters, utf16_len

# The Ctrl keys vim takes in Normal and Visual mode. Other Ctrl keys go to the app.
VIM_CTRL_KEYS = frozenset({"<C-r>"})

INSERT_COMMANDS = frozenset({"i", "a", "I", "A", "o", "O"})


@dataclass
class _Insert:
    """What the insert session started with, to repeat the typed text for a count."""

    count: int
    open_line: bool  # o and O open a new line for every repeat
    start: int  # the Qt position where typing started
    before: bytes  # the document as UTF-16 then


class VimMode(QObject):
    """Vim keys for one QPlainTextEdit. Starts in Normal mode."""

    mode_changed = Signal(Mode)
    pending_changed = Signal(str)

    # When a window closes, Python may clear this object while Qt still sends its
    # editor's last events. This default makes the filter let them all through.
    _enabled = False

    def __init__(self, editor: QPlainTextEdit) -> None:
        super().__init__(editor)
        self._editor = editor
        self._parser = Parser()
        self._pending = ""
        self._mode = Mode.NORMAL
        self._enabled = True
        self._attached = True
        self._insert: _Insert | None = None
        # the screen column j and k aim for, valid while the cursor stays where we put it
        self._want: int | None = None
        self._want_at: tuple[int, int] | None = None
        self._block_on = False
        self._plain_width = editor.cursorWidth()
        editor.installEventFilter(self)
        editor.viewport().installEventFilter(self)
        editor.cursorPositionChanged.connect(self._on_cursor_moved)
        self._on_cursor_moved()

    # --- the app's side ---

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """False: a plain editor again, with its own cursor. True: back in Normal mode."""
        if not self._attached:
            return
        self._insert = None
        self._parser.reset()
        self._emit_pending()
        self._enabled = enabled
        if enabled:
            self._set_mode(Mode.NORMAL)
            self._on_cursor_moved()
        else:
            self._update_cursor_width()

    def detach(self) -> None:
        """Take vim off the editor for good."""
        if not self._attached:
            return
        self.set_enabled(False)
        self._attached = False
        self._editor.removeEventFilter(self)
        self._editor.viewport().removeEventFilter(self)
        self._editor.cursorPositionChanged.disconnect(self._on_cursor_moved)

    # --- events ---

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self._enabled:
            return False
        kind = event.type()
        if watched is not self._editor:
            if kind == QEvent.Type.MouseButtonPress:
                # a click forgets the column j and k aim for, even on the same spot
                self._want_at = None
            return False
        if kind == QEvent.Type.ShortcutOverride:
            assert isinstance(event, QKeyEvent)
            if self._takes(key_token(event)):
                event.accept()
                return True
            return False
        if kind == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            return self._key_press(event)
        if kind == QEvent.Type.InputMethod:
            # an input method must not type text outside Insert mode
            return self._mode is not Mode.INSERT
        if kind == QEvent.Type.FontChange:
            # the editor lays out the text again first
            QTimer.singleShot(0, self._update_cursor_width)
        return False

    def _takes(self, token: str | None) -> bool:
        """True if vim handles this key now, instead of the editor or the app."""
        if token is None:
            return False
        if self._mode is Mode.INSERT:
            return token == ESC
        if token == ESC:
            # Esc with nothing pending goes on to the app, to close a dialog say
            return bool(self._parser.pending)
        if token.startswith("<C-"):
            return token in VIM_CTRL_KEYS
        # every other key is vim's, so Normal mode never types text
        return True

    def _key_press(self, event: QKeyEvent) -> bool:
        token = key_token(event)
        if not self._takes(token):
            return False
        assert token is not None
        if token == ESC:
            self._escape()
            return True
        command = self._parser.feed(token)
        self._emit_pending()
        if command is not None:
            self._run(command)
        return True

    def _escape(self) -> None:
        if self._mode is Mode.INSERT:
            self._leave_insert()
        else:
            self._parser.reset()
            self._emit_pending()

    def _run(self, command: Command) -> None:
        if command.name == "move":
            self._move(command)
        elif command.name in INSERT_COMMANDS:
            self._start_insert(command)
        # the other commands come in later steps

    # --- the cursor ---

    def _lines(self) -> Lines:
        """The text as it is now. Make a new one after changing the text."""
        return Lines(_Blocks(self._editor.document()))

    def _to_qt(self, lines: Lines, pos: Pos) -> int:
        """Like Lines.to_qt, but the document knows where each line starts."""
        start = self._editor.document().findBlockByNumber(pos.line).position()
        return start + lines.offset(pos)

    def _from_qt(self, lines: Lines, position: int) -> Pos:
        """Like Lines.from_qt, but the document finds the line."""
        document = self._editor.document()
        block = document.findBlock(position)
        if not block.isValid():
            block = document.lastBlock()
        line = block.blockNumber()
        return Pos(line, lines.col_at(line, position - block.position()))

    def _pos(self, lines: Lines) -> Pos:
        return self._from_qt(lines, self._editor.textCursor().position())

    def _go(self, lines: Lines, pos: Pos) -> None:
        cursor = self._editor.textCursor()
        cursor.setPosition(self._to_qt(lines, pos))
        self._editor.setTextCursor(cursor)
        self._update_cursor_width()

    def _where(self) -> tuple[int, int]:
        return self._editor.textCursor().position(), self._editor.document().revision()

    def _tabstop(self) -> int:
        """The editor's tab width in spaces."""
        space = self._editor.fontMetrics().horizontalAdvance(" ")
        if space <= 0:
            return 8
        return max(1, round(self._editor.tabStopDistance() / space))

    def _move(self, command: Command) -> None:
        assert command.motion is not None
        lines = self._lines()
        want = self._want if self._want_at == self._where() else None
        moved = move(
            lines,
            self._pos(lines),
            command.motion,
            command.count,
            want=want,
            tabstop=self._tabstop(),
        )
        if moved is None:
            return
        self._go(lines, moved.pos)
        self._want = moved.want
        self._want_at = self._where()

    def _on_cursor_moved(self) -> None:
        """Outside Insert mode, keep the cursor on a character, never after the last
        one, and never inside one (an app or Qt's flag bug can put it there)."""
        if not self._enabled or self._mode is Mode.INSERT:
            return
        cursor = self._editor.textCursor()
        if cursor.hasSelection():
            self._update_cursor_width()
            return
        lines = self._lines()
        pos = self._from_qt(lines, cursor.position())
        fixed = Pos(pos.line, min(pos.col, max(len(lines[pos.line]) - 1, 0)))
        if self._to_qt(lines, fixed) != cursor.position():
            self._go(lines, fixed)
        else:
            self._update_cursor_width()

    def _update_cursor_width(self) -> None:
        """A block cursor outside Insert mode, the editor's own cursor in it."""
        block = self._enabled and self._mode is not Mode.INSERT
        if block:
            if not self._block_on:
                self._plain_width = self._editor.cursorWidth()
                self._block_on = True
            width = self._block_width()
            if self._editor.cursorWidth() != width:
                self._editor.setCursorWidth(width)
        elif self._block_on:
            self._block_on = False
            self._editor.setCursorWidth(self._plain_width)

    def _block_width(self) -> int:
        """The width of the character under the cursor, as the editor draws it."""
        cursor = self._editor.textCursor()
        block = cursor.block()
        offset = cursor.positionInBlock()
        metrics = self._editor.fontMetrics()
        cluster = _cluster_at(block.text(), offset)
        if not cluster:
            return max(metrics.horizontalAdvance("x"), 1)
        line = block.layout().lineForTextPosition(offset)
        end = offset + utf16_len(cluster)
        if line.isValid() and end <= line.textStart() + line.textLength():
            width = line.cursorToX(end)[0] - line.cursorToX(offset)[0]
            if width >= 1:
                return ceil(width)
        return max(metrics.horizontalAdvance(cluster), metrics.horizontalAdvance("x"), 1)

    # --- Insert mode ---

    def _start_insert(self, command: Command) -> None:
        lines = self._lines()
        pos = self._pos(lines)
        text = lines[pos.line]
        name = command.name
        self._set_mode(Mode.INSERT)
        cursor = self._editor.textCursor()
        cursor.clearSelection()
        if name in ("o", "O"):
            at = self._to_qt(lines, Pos(pos.line, len(text) if name == "o" else 0))
            cursor.setPosition(at)
            cursor.insertText("\n")
            if name == "O":
                cursor.setPosition(at)
        else:
            if name == "i":
                col = pos.col
            elif name == "a":
                col = min(pos.col + 1, len(text))
            elif name == "I":
                # the first non-blank, or the line end if it's all blanks
                col = next((i for i, ch in enumerate(text) if ch not in BLANKS), len(text))
            else:
                col = len(text)
            cursor.setPosition(self._to_qt(lines, Pos(pos.line, col)))
        self._editor.setTextCursor(cursor)
        self._insert = _Insert(
            count=command.count or 1,
            open_line=name in ("o", "O"),
            start=cursor.position(),
            before=self._utf16(),
        )

    def _leave_insert(self) -> None:
        insert, self._insert = self._insert, None
        if insert is not None and insert.count > 1:
            self._repeat(insert)
        self._set_mode(Mode.NORMAL)
        # like vim, the cursor steps back onto the last character typed
        lines = self._lines()
        pos = self._pos(lines)
        self._go(lines, Pos(pos.line, max(pos.col - 1, 0)))

    def _repeat(self, insert: _Insert) -> None:
        """Type the text again, count - 1 more times, like vim's `3ix<Esc>`."""
        cursor = self._editor.textCursor()
        typed = self._typed(insert, cursor.position())
        if typed is None or not (typed or insert.open_line):
            return
        chunk = "\n" + typed if insert.open_line else typed
        cursor.clearSelection()
        cursor.insertText(chunk * (insert.count - 1))
        self._editor.setTextCursor(cursor)

    def _typed(self, insert: _Insert, position: int) -> str | None:
        """The text typed in this session, or None if more happened than typing at one
        spot: the cursor moved away, or text before the start changed. Vim drops the
        repeat then too."""
        after = self._utf16()
        start = insert.start * 2
        grown = len(after) - len(insert.before)
        if grown < 0 or position * 2 != start + grown:
            return None
        if (
            after[:start] != insert.before[:start]
            or after[start + grown :] != insert.before[start:]
        ):
            return None
        return after[start : start + grown].decode("utf-16-le").replace(PARAGRAPH_SEPARATOR, "\n")

    def _utf16(self) -> bytes:
        return self._editor.document().toRawText().encode("utf-16-le", "surrogatepass")

    # --- signals ---

    def _set_mode(self, mode: Mode) -> None:
        changed = mode is not self._mode
        self._mode = mode
        self._update_cursor_width()
        if changed:
            self.mode_changed.emit(mode)

    def _emit_pending(self) -> None:
        pending = self._parser.pending
        if pending != self._pending:
            self._pending = pending
            self.pending_changed.emit(pending)


class _Blocks(Sequence[str]):
    """The texts of a document's blocks (vim's lines), read when asked."""

    def __init__(self, document: QTextDocument) -> None:
        self._document = document

    def __len__(self) -> int:
        return self._document.blockCount()

    @overload
    def __getitem__(self, index: int) -> str: ...
    @overload
    def __getitem__(self, index: slice) -> list[str]: ...
    def __getitem__(self, index: int | slice) -> str | list[str]:
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if not 0 <= index < len(self):
            raise IndexError(index)
        return self._document.findBlockByNumber(index).text()


def _cluster_at(text: str, offset: int) -> str:
    """The character starting at a UTF-16 offset in a block's text, or "" at its end."""
    end = 0
    for cluster in split_clusters(text):
        end += utf16_len(cluster)
        if end > offset:
            return cluster
    return ""
