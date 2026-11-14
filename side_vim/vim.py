"""VimMode: vim keys for a QPlainTextEdit. The only module that talks to the editor.

It sits on the editor as an event filter. In Normal mode it takes the keys, turns them
into commands with the parser, and moves the cursor or edits the text. In Insert mode
the editor types as usual, and only Esc (or Ctrl+[) is taken.

Every position goes through text.Lines, which works in whole characters (a family
emoji is one) and converts to Qt's UTF-16 positions.

Undo uses the document's own undo stack, so the app's undo (Ctrl+Z in Insert mode, an
Edit menu) and vim's `u` see the same steps. Each Normal mode command is one edit
block, so one step. An insert session (from `i`, `o` or `cw` to Esc) is one step too:
Qt splits typing into several steps, or adds it to the step before, so at Esc the
session's steps are undone and its whole change is made again as one block. An app
that watches textChanged sees the text change a few times then, ending as it was.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from math import ceil
from typing import overload

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent, QTextCursor, QTextDocument
from PySide6.QtWidgets import QPlainTextEdit

from side_vim.edits import Register, join, join_parts, undo_cursor
from side_vim.keys import ESC, key_token
from side_vim.mode import Mode
from side_vim.motions import (
    BLANKS,
    Pos,
    Range,
    first_non_blank,
    line_range,
    move,
    operator_range,
    range_text,
)
from side_vim.parser import LINE, OPERATORS, Command, Parser
from side_vim.text import PARAGRAPH_SEPARATOR, Lines, split_clusters, utf16_len

# The Ctrl keys vim takes in Normal and Visual mode. Other Ctrl keys go to the app.
VIM_CTRL_KEYS = frozenset({"<C-r>"})

INSERT_COMMANDS = frozenset({"i", "a", "I", "A", "o", "O"})

KEEP_ANCHOR = QTextCursor.MoveMode.KeepAnchor


class _Shared:
    """The one unnamed register, shared by every VimMode in the process, so text
    yanked in one editor pastes in another."""

    register: Register = Register()


@dataclass
class _Insert:
    """An insert session, from `i` (or `o`, `cw`, ...) to Esc."""

    count: int  # how many times the typed text goes in, like `3ix<Esc>`
    open_line: bool  # o and O open a new line for every repeat
    document: QTextDocument
    origin: str  # the document's text before the session changed anything
    saved: Pos | None  # where `u` puts the cursor back; None: where typing starts
    start: int = 0  # the Qt position where typing started
    before: bytes = b""  # the document as UTF-16 then
    levels: int = 0  # undo steps Qt added during the session
    seen: int = 0  # levels at the last change
    merged_outside: bool = False  # Qt added the first change to the step before
    messy: bool = False  # the app undid or redid something during the session


class VimMode(QObject):
    """Vim keys for one QPlainTextEdit. Starts in Normal mode.

    clipboard: False keeps yanked and deleted text in vim's own register. True puts
    it on the system clipboard, and p pastes from there.
    """

    mode_changed = Signal(Mode)
    pending_changed = Signal(str)

    # When a window closes, Python may clear this object while Qt still sends its
    # editor's last events. These defaults make the filter let them all through.
    _enabled = False
    _busy = False
    _insert: _Insert | None = None

    def __init__(self, editor: QPlainTextEdit) -> None:
        super().__init__(editor)
        self.clipboard = False
        self._editor = editor
        self._parser = Parser()
        self._pending = ""
        self._mode = Mode.NORMAL
        self._enabled = True
        self._attached = True
        self._insert = None
        # the screen column j and k aim for, valid while the cursor stays where we put it
        self._want: int | None = None
        self._want_at: tuple[int, int] | None = None
        self._block_on = False
        self._plain_width = editor.cursorWidth()
        # For each undo step from the top of the document's stack, where `u` puts the
        # cursor (None: unknown). Valid while the document's revision is _synced.
        self._done: list[Pos | None] = []
        self._undone: list[Pos | None] = []
        self._synced = editor.document().revision()
        # set while vim edits, so the signals that fires don't count as the user's
        self._busy = False
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
        self._drop_insert()
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
        name = command.name
        if name == "move":
            self._move(command)
        elif name in INSERT_COMMANDS:
            self._start_insert(command)
        elif name in OPERATORS:
            self._operate(command)
        elif name in ("p", "P"):
            self._paste(command)
        elif name == "J":
            self._join(command)
        elif name in ("u", "<C-r>"):
            self._undo(command.count or 1, redo=name == "<C-r>")
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

    def _put(self, lines: Lines, pos: Pos) -> None:
        """Go to pos, kept on a character of a line that exists, as Normal mode wants."""
        line = min(max(pos.line, 0), len(lines) - 1)
        self._go(lines, Pos(line, min(max(pos.col, 0), max(len(lines[line]) - 1, 0))))

    def _where(self) -> tuple[int, int]:
        return self._editor.textCursor().position(), self._editor.document().revision()

    def _tabstop(self) -> int:
        """The editor's tab width in spaces."""
        space = self._editor.fontMetrics().horizontalAdvance(" ")
        if space <= 0:
            return 8
        return max(1, round(self._editor.tabStopDistance() / space))

    def _wanted(self) -> int | None:
        """The screen column j and k aim for, if the cursor is still where vim put it."""
        return self._want if self._want_at == self._where() else None

    def _move(self, command: Command) -> None:
        assert command.motion is not None
        lines = self._lines()
        moved = move(
            lines,
            self._pos(lines),
            command.motion,
            command.count,
            want=self._wanted(),
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
        if not self._enabled or self._busy or self._mode is Mode.INSERT:
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

    # --- operators: d, c, y ---

    def _operate(self, command: Command) -> None:
        assert command.motion is not None
        name = command.name
        lines = self._lines()
        pos = self._pos(lines)
        if command.motion == LINE:
            r = line_range(lines, pos, command.count)
            if r is None:
                return
            # dd and cc go to the first non-blank of the last line first; vim's undo
            # remembers whichever of the two comes first
            end = Pos(r.end.line, first_non_blank(lines[r.end.line]))
            start = pos if name == "y" else min(pos, end)
        else:
            moved = move(
                lines,
                pos,
                command.motion,
                command.count,
                want=self._wanted(),
                op=name,
                tabstop=self._tabstop(),
            )
            if moved is None:
                return
            r = operator_range(lines, pos, moved, name)
            start = min(pos, moved.pos)
        empty = not r.linewise and r.start == r.end
        # vim's empty yank empties the register, an empty delete leaves it alone
        if not empty or name == "y":
            self._store(range_text(lines, r), r.linewise)
        if name == "y":
            self._put(lines, start)
            self._want_at = None  # j and k aim for the cursor's column again
        elif name == "d":
            if not empty:
                self._delete(lines, r, start)
        else:
            self._change_text(lines, r, start, empty)

    def _span(self, lines: Lines, r: Range) -> tuple[int, int]:
        """The Qt positions a range covers. Whole lines take one line break with them,
        the one after them, or before them at the end of the document."""
        if not r.linewise:
            return self._to_qt(lines, r.start), self._to_qt(lines, r.end)
        document = self._editor.document()
        first = document.findBlockByNumber(r.start.line)
        last = document.findBlockByNumber(r.end.line)
        after = last.next()
        if after.isValid():
            return first.position(), after.position()
        end = last.position() + last.length() - 1
        return max(first.position() - 1, 0), end

    def _delete(self, lines: Lines, r: Range, start: Pos) -> None:
        begin, end = self._span(lines, r)
        with self._change(start) as edit:
            edit.setPosition(begin)
            edit.setPosition(end, KEEP_ANCHOR)
            edit.removeSelectedText()
        lines = self._lines()
        if r.linewise:
            line = min(r.start.line, len(lines) - 1)
            self._put(lines, Pos(line, first_non_blank(lines[line])))
        else:
            self._put(lines, r.start)

    def _change_text(self, lines: Lines, r: Range, start: Pos, empty: bool) -> None:
        """c: delete the range and type in its place. Whole lines leave one empty line
        (no autoindent). The delete and the typing are one undo step."""
        document = self._editor.document()
        self._begin_insert(start, count=1, open_line=False)
        if r.linewise:
            begin = document.findBlockByNumber(r.start.line).position()
            last = document.findBlockByNumber(r.end.line)
            end = last.position() + last.length() - 1
        else:
            begin, end = self._span(lines, r)
        if not empty and end > begin:
            edit = QTextCursor(document)
            edit.beginEditBlock()
            edit.setPosition(begin)
            edit.setPosition(end, KEEP_ANCHOR)
            edit.removeSelectedText()
            edit.endEditBlock()
        cursor = self._editor.textCursor()
        cursor.setPosition(begin)
        self._typing_starts(cursor)

    # --- p, P, J ---

    def _paste(self, command: Command) -> None:
        register = self._read_register()
        if not register.text:
            return
        count = command.count or 1
        lines = self._lines()
        pos = self._pos(lines)
        after = command.name == "p"
        document = self._editor.document()
        if register.linewise:
            body = register.text.removesuffix("\n")
            block = document.findBlockByNumber(pos.line)
            if after:
                at, chunk = block.position() + block.length() - 1, ("\n" + body) * count
            else:
                at, chunk = block.position(), (body + "\n") * count
            with self._change(pos) as edit:
                edit.setPosition(at)
                edit.insertText(chunk)
            lines = self._lines()
            line = pos.line + 1 if after else pos.line
            self._put(lines, Pos(line, first_non_blank(lines[line])))
            return
        text = lines[pos.line]
        at = self._to_qt(lines, Pos(pos.line, min(pos.col + 1, len(text)) if after else pos.col))
        chunk = register.text * count
        with self._change(pos) as edit:
            edit.setPosition(at)
            edit.insertText(chunk)
        lines = self._lines()
        # on the last character pasted, or on the first if it was more than one line
        if "\n" in chunk:
            self._put(lines, self._from_qt(lines, at))
        else:
            self._put(lines, self._from_qt(lines, at + utf16_len(chunk) - 1))

    def _join(self, command: Command) -> None:
        lines = self._lines()
        pos = self._pos(lines)
        count = max(command.count or 2, 2)
        if pos.line + count > len(lines):
            if count == 2:
                return  # on the last line: nothing to join
            count = len(lines) - pos.line
            if count < 2:
                # vim "joins" the one line, which only moves the cursor
                self._put(lines, Pos(pos.line, 0))
                return
        raws = [lines.raw(i) for i in range(pos.line, pos.line + count)]
        joined, at = join(raws)
        document = self._editor.document()
        start = document.findBlockByNumber(pos.line).position()
        with self._change(pos) as edit:
            # from the last line up, so the lines above keep their positions
            for i, (blanks, space) in reversed(list(enumerate(join_parts(raws), 1))):
                block = document.findBlockByNumber(pos.line + i)
                edit.setPosition(block.position() - 1)
                edit.setPosition(block.position() + blanks, KEEP_ANCHOR)
                edit.removeSelectedText()
                if space:
                    edit.insertText(space)
        lines = self._lines()
        self._put(lines, self._from_qt(lines, start + utf16_len(joined[:at])))

    # --- the register ---

    def _store(self, text: str, linewise: bool) -> None:
        _Shared.register = Register(text, linewise)
        if self.clipboard:
            QGuiApplication.clipboard().setText(text)

    def _read_register(self) -> Register:
        """What p pastes. From the clipboard: if it still holds our last yank, that
        yank's kind; otherwise whole lines if the text ends in a newline."""
        if not self.clipboard:
            return _Shared.register
        text = QGuiApplication.clipboard().text().replace("\r\n", "\n")
        if text == _Shared.register.text:
            return _Shared.register
        return Register(text, linewise=text.endswith("\n"))

    # --- undo ---

    def _check_synced(self) -> None:
        """Forget where `u` goes if the document changed without vim, since its undo
        steps no longer match the ones vim knows."""
        revision = self._editor.document().revision()
        if revision != self._synced:
            self._done.clear()
            self._undone.clear()
            self._synced = revision

    @contextmanager
    def _change(self, saved: Pos) -> Iterator[QTextCursor]:
        """One Normal mode command's edits, as one undo step. saved: where `u` puts
        the cursor back."""
        document = self._editor.document()
        self._check_synced()
        revision = document.revision()
        edit = QTextCursor(document)
        self._busy = True
        edit.beginEditBlock()
        try:
            yield edit
        finally:
            edit.endEditBlock()
            self._busy = False
        if document.revision() != revision:
            self._done.append(saved)
            self._undone.clear()
        self._synced = document.revision()

    def _undo(self, count: int, redo: bool) -> None:
        document = self._editor.document()
        self._check_synced()
        source, target = (self._undone, self._done) if redo else (self._done, self._undone)
        changed: list[tuple[int, int]] = []
        saved: Pos | None = None

        def on_change(position: int, removed: int, added: int) -> None:
            changed.append((position, position + added))

        for _ in range(count):
            if not (document.isRedoAvailable() if redo else document.isUndoAvailable()):
                break
            saved = source.pop() if source else None
            target.append(saved)
            changed.clear()
            document.contentsChange.connect(on_change)
            self._busy = True
            try:
                if redo:
                    document.redo()
                else:
                    document.undo()
            finally:
                self._busy = False
                document.contentsChange.disconnect(on_change)
        self._synced = document.revision()
        lines = self._lines()
        if changed:
            first = self._from_qt(lines, min(start for start, _ in changed)).line
            last = self._from_qt(lines, max(end for _, end in changed)).line
            self._put(lines, undo_cursor(lines, saved, first, last))
        else:
            self._put(lines, self._pos(lines))

    # --- Insert mode ---

    def _start_insert(self, command: Command) -> None:
        lines = self._lines()
        pos = self._pos(lines)
        text = lines[pos.line]
        name = command.name
        open_line = name in ("o", "O")
        self._begin_insert(pos if open_line else None, command.count or 1, open_line)
        cursor = self._editor.textCursor()
        cursor.clearSelection()
        if open_line:
            at = self._to_qt(lines, Pos(pos.line, len(text) if name == "o" else 0))
            # in an edit block, so Qt can't add it to the undo step before
            edit = QTextCursor(self._editor.document())
            edit.beginEditBlock()
            edit.setPosition(at)
            edit.insertText("\n")
            edit.endEditBlock()
            cursor.setPosition(at + 1 if name == "o" else at)
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
        self._typing_starts(cursor)

    def _begin_insert(self, saved: Pos | None, count: int, open_line: bool) -> None:
        """Start an insert session, before anything in it changes the text."""
        self._check_synced()
        document = self._editor.document()
        self._set_mode(Mode.INSERT)
        self._insert = _Insert(
            count=count,
            open_line=open_line,
            document=document,
            origin=document.toRawText(),
            saved=saved,
        )
        document.undoCommandAdded.connect(self._on_undo_step)
        document.contentsChange.connect(self._on_insert_change)
        document.redoAvailable.connect(self._on_redo_available)

    def _typing_starts(self, cursor: QTextCursor) -> None:
        self._editor.setTextCursor(cursor)
        assert self._insert is not None
        self._insert.start = cursor.position()
        self._insert.before = self._utf16()

    def _on_undo_step(self) -> None:
        if self._insert is not None and not self._busy:
            self._insert.levels += 1

    def _on_insert_change(self, position: int, removed: int, added: int) -> None:
        insert = self._insert
        if insert is None or self._busy:
            return
        if insert.levels == insert.seen and insert.levels == 0:
            # no new undo step for this change: Qt added it to the one before
            insert.merged_outside = True
        insert.seen = insert.levels
        if insert.saved is None:
            insert.saved = self._from_qt(self._lines(), position)

    def _on_redo_available(self, available: bool) -> None:
        if available and self._insert is not None and not self._busy:
            self._insert.messy = True

    def _leave_insert(self) -> None:
        insert = self._insert
        if insert is not None:
            if insert.count > 1:
                self._repeat(insert)
            self._end_insert(insert)
        self._set_mode(Mode.NORMAL)
        # like vim, the cursor steps back onto the last character typed
        lines = self._lines()
        pos = self._pos(lines)
        self._go(lines, Pos(pos.line, max(pos.col - 1, 0)))

    def _disconnect(self, insert: _Insert) -> None:
        self._insert = None
        document = insert.document
        with suppress(RuntimeError, TypeError):
            document.undoCommandAdded.disconnect(self._on_undo_step)
            document.contentsChange.disconnect(self._on_insert_change)
            document.redoAvailable.disconnect(self._on_redo_available)

    def _drop_insert(self) -> None:
        """End a session without making it one undo step (vim turned off mid-way)."""
        if self._insert is not None:
            self._disconnect(self._insert)
            self._done.clear()
            self._undone.clear()
            self._synced = self._editor.document().revision()

    def _end_insert(self, insert: _Insert) -> None:
        self._disconnect(insert)
        document = insert.document
        final = document.toRawText()
        changed = final != insert.origin
        if insert.messy or document is not self._editor.document():
            # the app's own undo ran: leave its steps as they are
            self._done.clear()
            self._undone.clear()
        elif insert.levels >= 2 or insert.merged_outside or (insert.levels and not changed):
            if not self._regroup(insert, final):
                self._done.clear()
                self._undone.clear()
            elif changed:
                self._done.append(insert.saved)
                self._undone.clear()
        elif changed:
            self._done.append(insert.saved)
            self._undone.clear()
        self._synced = self._editor.document().revision()

    def _regroup(self, insert: _Insert, final: str) -> bool:
        """Make the session one undo step: undo its steps, then make its whole change
        again in one edit block. False if the steps didn't lead back to where the
        session started; then everything is put back as it was."""
        document = insert.document
        position = self._editor.textCursor().position()
        steps = insert.levels + insert.merged_outside
        self._busy = True
        try:
            undone = 0
            while undone < steps and document.isUndoAvailable():
                document.undo()
                undone += 1
            now = document.toRawText()
            if now != insert.origin and not insert.merged_outside:
                for _ in range(undone):
                    document.redo()
                return False
            if now != insert.origin:
                # the step before took the session's first change: make it again alone
                _replace(document, now, insert.origin)
            if final != insert.origin:
                _replace(document, insert.origin, final)
            else:
                document.clearUndoRedoStacks(QTextDocument.Stacks.RedoStack)
        finally:
            self._busy = False
            cursor = self._editor.textCursor()
            cursor.setPosition(min(position, document.characterCount() - 1))
            self._editor.setTextCursor(cursor)
        return True

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


def _replace(document: QTextDocument, old: str, new: str) -> None:
    """Turn the document's text from old into new with one edit block, changing only
    the part between what they share at the start and at the end."""
    head = _shared_head(old, new)
    tail = _shared_head(old[head:][::-1], new[head:][::-1])
    edit = QTextCursor(document)
    edit.beginEditBlock()
    edit.setPosition(utf16_len(old[:head]))
    edit.setPosition(utf16_len(old[: len(old) - tail]), KEEP_ANCHOR)
    edit.removeSelectedText()
    text = new[head : len(new) - tail]
    if text:
        edit.insertText(text.replace(PARAGRAPH_SEPARATOR, "\n"))
    edit.endEditBlock()


def _shared_head(a: str, b: str) -> int:
    """How many code points a and b share at the start."""
    low, high = 0, min(len(a), len(b))
    while low < high:
        mid = (low + high + 1) // 2
        if a[:mid] == b[:mid]:
            low = mid
        else:
            high = mid - 1
    return low


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
