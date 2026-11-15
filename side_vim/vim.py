"""VimMode: vim keys for a QPlainTextEdit. The only module that talks to the editor.

It sits on the editor as an event filter. In Normal mode it takes the keys, turns them
into commands with the parser, and moves the cursor or edits the text. In Insert mode
the editor types as usual, and only Esc (or Ctrl+[) is taken.

In Visual mode the selection is the editor's own, set to exactly what vim selects, and
caret.Caret draws vim's cursor over it. A mouse drag in Normal mode starts Visual mode.
The Caret also draws the cursor in a read-only editor, where Qt draws none.

Outside Insert mode, keys typed on the Ukrainian layout work as the Latin keys in the
same place (layout_map), so `к` is `r` and Ctrl+к is Ctrl+R.

Every position goes through text.Lines, which works in whole characters (a family
emoji is one) and converts to Qt's UTF-16 positions.

Undo uses the document's own undo stack, so the app's undo (Ctrl+Z in Insert mode, an
Edit menu) and vim's `u` see the same steps. Each Normal mode command is one edit
block, so one step. An insert session (from `i`, `o` or `cw` to Esc) is one step too:
Qt splits typing into several steps, or adds it to the step before, so at Esc the
session's steps are undone and its whole change is made again as one block. An app
that watches textChanged sees the text change a few times then, ending as it was.
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from typing import overload

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import (
    QGuiApplication,
    QInputMethodEvent,
    QKeyEvent,
    QKeySequence,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import QPlainTextEdit

from side_vim.caret import Caret, char_width
from side_vim.edits import Register, join, join_parts, undo_cursor, visual_start
from side_vim.keys import ESC, key_token, map_layout
from side_vim.layouts import UKRAINIAN
from side_vim.mode import Mode
from side_vim.motions import (
    BLANKS,
    Pos,
    Range,
    column_for,
    first_non_blank,
    line_range,
    move,
    operator_range,
    range_text,
    screen_col,
    visual_range,
)
from side_vim.parser import (
    CTRL_KEYS,
    INSERT_COMMANDS,
    LINE,
    OPERATORS,
    Command,
    Parser,
    changes_text,
)
from side_vim.scroll import SCROLL_KEYS, scroll
from side_vim.search import search
from side_vim.text import PARAGRAPH_SEPARATOR, Lines, split_clusters, utf16_len

VISUAL_MODES = frozenset({Mode.VISUAL, Mode.VISUAL_LINE})

KEEP_ANCHOR = QTextCursor.MoveMode.KeepAnchor

# Qt's own keys that change the text, like Ctrl+V. Outside Insert mode they do nothing,
# so only vim's commands edit there.
QT_EDIT_KEYS = (
    QKeySequence.StandardKey.Paste,
    QKeySequence.StandardKey.Cut,
    QKeySequence.StandardKey.DeleteStartOfWord,
    QKeySequence.StandardKey.DeleteEndOfWord,
    QKeySequence.StandardKey.DeleteEndOfLine,
    QKeySequence.StandardKey.DeleteCompleteLine,
)

# The editor draws its cursor only if one of these is on.
DRAWS_CURSOR = Qt.TextInteractionFlag.TextEditable | Qt.TextInteractionFlag.TextSelectableByKeyboard


# The unnamed register is shared by all editors, so yanks paste between them.
_register = Register()


def takes_nothing(r: Range, no_lines: bool) -> bool:
    """True if a delete or change over r has nothing to take: an empty part of a line,
    or a text with no lines at all (see VimMode._no_lines). A line that x emptied is
    still a line, and dd takes its line break."""
    return no_lines or (not r.linewise and r.start == r.end)


type Version = tuple[QTextDocument, int]  # a document and its revision


@dataclass
class UndoStep:
    """An undo step vim knows. cursor: where `u` puts the cursor (None: unknown).
    no_lines: whether the text on the other side of the step has no lines. vim keeps
    that with each step too, so `u` and Ctrl+R bring it back. in_qt: False for a step
    Qt doesn't have, since the text stayed the same: dd on the only line, once x
    emptied it, goes from one empty line to no lines."""

    cursor: Pos | None
    no_lines: bool
    in_qt: bool = True


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
    no_lines: bool = False  # VimMode._no_lines when the session started
    edited: bool = False  # the text changed during the session, even if back as it was


class VimMode(QObject):
    """Vim keys for one QPlainTextEdit. Starts in Normal mode.

    clipboard: False keeps yanked and deleted text in vim's own register. True puts
    it on the system clipboard, and p pastes from there.
    escape_hook: called first on every Esc that reaches the editor. If it returns True
    (it closed a popup, say), vim does nothing else with that Esc.
    search_hook: `/` calls it with True, `?` with False. The app shows its search, and
    passes the text to set_search.
    layout_map: keys outside Insert mode go through it, so a Cyrillic letter works as
    the Latin key in the same place. UKRAINIAN by default; None turns it off.
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
        self.escape_hook: Callable[[], bool] | None = None
        self.search_hook: Callable[[bool], None] | None = None
        self.layout_map: dict[str, str] | None = UKRAINIAN
        self._search: tuple[str, bool] | None = None
        # what Ctrl+D and Ctrl+U scroll, once a count set it (vim's 'scroll')
        self._scroll_amount: int | None = None
        self._editor = editor
        self._parser = Parser()
        self._pending = ""
        self._mode = Mode.NORMAL
        self._enabled = True
        self._attached = True
        self._insert = None
        # the screen column j and k aim for, valid while the cursor stays where we put it
        self._want: int | None = None
        self._want_at: tuple[int, Version] | None = None
        self._block_on = False
        self._plain_width = editor.cursorWidth()
        # The undo steps vim knows, newest last: Qt's steps from the top of the
        # document's stack, and the few only vim has. Valid while _version() is still
        # _synced.
        self._done: list[UndoStep] = []
        self._undone: list[UndoStep] = []
        self._synced = self._version()
        # vim's empty buffer: no lines at all, as in a new text or after dd deleted every
        # line. Any edit gives it a line again, even one that leaves it empty.
        self._no_lines = not editor.document().toRawText()
        # set while vim edits, so the signals that fires don't count as the user's
        self._busy = False
        # Visual mode: the two ends of the selection, as positions Qt moves along when
        # the text changes. None outside Visual mode.
        self._anchor: QTextCursor | None = None
        self._end: QTextCursor | None = None
        self._mouse_down = False
        self._caret = Caret(editor)
        # the editor's interaction flags while Visual mode has turned DRAWS_CURSOR off
        self._saved_flags: Qt.TextInteractionFlag | None = None
        editor.installEventFilter(self)
        editor.viewport().installEventFilter(self)
        editor.cursorPositionChanged.connect(self._on_cursor_moved)
        # the app can move the anchor alone, which doesn't move the cursor
        editor.selectionChanged.connect(self._on_cursor_moved)
        self._on_cursor_moved()
        self._normal_handlers, self._visual_handlers = self._handlers()

    def _handlers(
        self,
    ) -> tuple[dict[str, Callable[[Command], None]], dict[str, Callable[[Command], None]]]:
        """What runs each command, in Normal mode and in Visual mode. They cover every
        name in the parser's tables, and the tests check that."""
        both: dict[str, Callable[[Command], None]] = {
            "move": self._move,
            "n": self._search_next,
            "N": self._search_next,
            "/": self._open_search,
            "?": self._open_search,
        }
        both |= dict.fromkeys(SCROLL_KEYS, self._scroll)
        normal = both | dict.fromkeys(OPERATORS, self._operate)
        normal |= dict.fromkeys(INSERT_COMMANDS, self._start_insert)
        normal |= {
            "p": self._paste,
            "P": self._paste,
            "J": self._join,
            "u": self._undo_command,
            "<C-r>": self._undo_command,
            "v": self._start_visual_command,
            "V": self._start_visual_command,
        }
        visual = both | dict.fromkeys(OPERATORS, self._visual_operate)
        visual |= {
            "p": self._visual_paste,
            "o": self._swap_ends,
            "v": self._switch_visual,
            "V": self._switch_visual,
        }
        return normal, visual

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_search(self, text: str, forward: bool = True) -> None:
        """Search for plain text, like typing it after `/` (forward) or `?` in vim and
        pressing Enter: the cursor goes to the next match, if there is one. After that n
        looks for the text the same way, and N the other way."""
        text = text.replace("\r\n", "\n").replace(PARAGRAPH_SEPARATOR, "\n")
        self._search = (text, forward) if text else None
        if self._enabled and self._mode is not Mode.INSERT:
            self._search_next(Command("n"))

    def normal(self) -> None:
        """Go to Normal mode as Esc does: what was typed since `i` is one undo step,
        and Visual mode drops its selection. For an app that takes the user back to
        the text, from its search bar say."""
        if self._enabled:
            self._escape()

    def set_enabled(self, enabled: bool) -> None:
        """False: a plain editor again, with its own cursor. True: back in Normal mode."""
        if not self._attached:
            return
        self._drop_insert()
        self._drop_visual()
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
        self._editor.selectionChanged.disconnect(self._on_cursor_moved)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not self._enabled:
            return False
        kind = event.type()
        if watched is not self._editor:
            if kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
                # a click forgets the column j and k aim for, even on the same spot
                self._want_at = None
                self._mouse_down = True
            elif kind == QEvent.Type.MouseButtonRelease:
                self._mouse_down = False
            elif kind == QEvent.Type.Resize:
                # Qt skips the call if the caret is deleted before the timer fires
                QTimer.singleShot(0, self._caret, self._caret.place)
            return False
        if kind == QEvent.Type.ShortcutOverride:
            assert isinstance(event, QKeyEvent)
            if self._takes(self._token(event)) or self._blocks(event):
                event.accept()
                return True
            return False
        if kind == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            return self._key_press(event)
        if kind == QEvent.Type.InputMethod:
            if self._mode is Mode.INSERT:
                return False
            # Outside Insert mode an input method's text never goes in: it's keys. On
            # Linux, letters typed on a layout like Ukrainian often come this way.
            assert isinstance(event, QInputMethodEvent)
            self._input_keys(event.commitString())
            return True
        if kind == QEvent.Type.ReadOnlyChange:
            if self._saved_flags is not None:
                # the app's setReadOnly: its flags are the ones to put back after Visual
                self._saved_flags = None
            if self._mode is Mode.INSERT and self._read_only():
                self._leave_insert()
            self._update_cursor_width()
        if kind in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self._caret.restart_blink()
        if kind == QEvent.Type.FontChange:
            # the editor lays out the text again first
            QTimer.singleShot(0, self, self._update_cursor_width)
        return False

    def _token(self, event: QKeyEvent) -> str | None:
        """The key as vim reads it now: through layout_map, outside Insert mode. In
        Insert mode only Ctrl+х maps, to Esc, since it's the key of Ctrl+[."""
        token = key_token(event)
        if token is None:
            return None
        mapped = map_layout(token, self.layout_map)
        if self._mode is Mode.INSERT:
            return ESC if mapped == ESC else token
        return mapped

    def _read_only(self) -> bool:
        """The app made the editor read-only (Visual mode's own change doesn't count)."""
        flags = self._saved_flags
        if flags is None:
            flags = self._editor.textInteractionFlags()
        return not flags & Qt.TextInteractionFlag.TextEditable

    def _takes(self, token: str | None) -> bool:
        """True if vim handles this key now, instead of the editor or the app."""
        if token is None:
            return False
        if self._mode is Mode.INSERT:
            return token == ESC
        if token == ESC:
            # Esc with nothing pending goes on to the app, to close a dialog say
            return bool(self._parser.pending) or self._mode in VISUAL_MODES
        if token.startswith("<C-"):
            return token in CTRL_KEYS
        # every other key is vim's, so Normal mode never types text
        return True

    def _blocks(self, event: QKeyEvent) -> bool:
        """True for a key of Qt's that would change the text outside Insert mode. Vim's
        keys come first: on Linux, Ctrl+U deletes a line in Qt but scrolls in vim."""
        return self._mode is not Mode.INSERT and any(event.matches(key) for key in QT_EDIT_KEYS)

    def _key_press(self, event: QKeyEvent) -> bool:
        token = self._token(event)
        if token == ESC and self.escape_hook is not None and self.escape_hook():
            return True
        if not self._takes(token):
            return self._blocks(event)
        assert token is not None
        if token == ESC:
            self._escape()
            return True
        self._feed(token)
        return True

    def _feed(self, token: str) -> None:
        command = self._parser.feed(token, visual=self._mode in VISUAL_MODES)
        self._emit_pending()
        if command is not None:
            self._run(command)

    def _input_keys(self, text: str) -> None:
        """Text from an input method outside Insert mode, as keys one by one. If one of
        them starts Insert mode (like `i`), the rest is typed."""
        chars = split_clusters(text)
        for i, ch in enumerate(chars):
            if self._mode is Mode.INSERT:
                cursor = self._editor.textCursor()
                cursor.insertText("".join(chars[i:]))
                self._editor.setTextCursor(cursor)
                return
            self._feed(map_layout(ch, self.layout_map))

    def _escape(self) -> None:
        if self._mode is Mode.INSERT:
            self._leave_insert()
            return
        self._parser.reset()
        self._emit_pending()
        if self._mode in VISUAL_MODES:
            self._leave_visual()

    def _run(self, command: Command) -> None:
        visual = self._mode in VISUAL_MODES
        if changes_text(command, visual) and self._read_only():
            return
        handlers = self._visual_handlers if visual else self._normal_handlers
        handlers[command.name](command)

    def _open_search(self, command: Command) -> None:
        if self.search_hook is not None:
            self.search_hook(command.name == "/")

    def _lines(self) -> Lines:
        """The text as it is now. Make a new one after changing the text."""
        return Lines(_Blocks(self._editor.document()))

    def _to_qt(self, lines: Lines, pos: Pos) -> int:
        """Like Lines.to_qt, but the document knows where each line starts."""
        start = self._editor.document().findBlockByNumber(pos.line).position()
        return start + lines.offset(pos)

    def _from_qt(self, lines: Lines, position: int) -> Pos:
        """A Qt position in the editor's document as vim's line and column."""
        return _from_qt(self._editor.document(), lines, position)

    def _position(self) -> int:
        """vim's cursor as a Qt position. In Visual mode it's one end of the selection,
        not always where the editor's cursor is."""
        if self._end is not None:
            return self._end.position()
        return self._editor.textCursor().position()

    def _pos(self, lines: Lines) -> Pos:
        return self._from_qt(lines, self._position())

    def _go(self, lines: Lines, pos: Pos) -> None:
        if self._end is not None:
            self._end.setPosition(self._to_qt(lines, pos))
            self._show_visual()
            return
        cursor = self._editor.textCursor()
        cursor.setPosition(self._to_qt(lines, pos))
        self._editor.setTextCursor(cursor)
        self._update_cursor_width()

    def _put(self, lines: Lines, pos: Pos) -> None:
        """Go to pos, kept on a character of a line that exists, as Normal mode wants."""
        line = min(max(pos.line, 0), len(lines) - 1)
        self._go(lines, Pos(line, min(max(pos.col, 0), max(len(lines[line]) - 1, 0))))

    def _version(self) -> Version:
        """Which text the editor shows now. The revision alone can't tell: an app with
        tabs swaps in another document, and its revision can be the same."""
        document = self._editor.document()
        return document, document.revision()

    def _where(self) -> tuple[int, Version]:
        return self._position(), self._version()

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
            visual=self._mode in VISUAL_MODES,
            tabstop=self._tabstop(),
        )
        if moved is None:
            return
        self._go(lines, moved.pos)
        self._want = moved.want
        self._want_at = self._where()

    def _search_next(self, command: Command) -> None:
        if self._search is None:
            return
        text, forward = self._search
        lines = self._lines()
        pattern = [split_clusters(part) for part in text.split("\n")]
        found = search(
            lines, self._pos(lines), pattern, forward == (command.name == "n"), command.count
        )
        if found is None:
            return
        self._go(lines, found)
        self._want_at = None

    def _view(self) -> tuple[int, int, int]:
        """The first line on the screen, how many lines fit on it, and the highest
        first line the editor scrolls to (the last line at the bottom)."""
        first, _, height = self._visible()
        rows = self._editor.verticalScrollBar().maximum()
        block = self._editor.document().firstBlock()
        while block.isValid() and rows >= block.lineCount() and block.next().isValid():
            rows -= block.lineCount()
            block = block.next()
        return first, height, block.blockNumber()

    def _visible(self) -> tuple[int, int, int]:
        """The first and last lines fully on the screen, and how many lines fit on it
        (vim's window height). Lines can differ in height: emoji often make a line
        taller. Past the end of the text, lines as high as the last one would fit."""
        editor = self._editor
        offset = editor.contentOffset()
        bottom = editor.viewport().height()
        block = editor.firstVisibleBlock()
        first = last = block.blockNumber()
        count = 0
        while block.isValid():
            geometry = editor.blockBoundingGeometry(block).translated(offset)
            if geometry.bottom() > bottom + 0.5 and count:
                break
            last = block.blockNumber()
            count += 1
            if not block.next().isValid():
                row = geometry.height() / max(block.lineCount(), 1)
                if row > 0:
                    count += max(int((bottom - geometry.bottom()) // row), 0)
            block = block.next()
        return first, last, max(count, 1)

    def _scroll_to(self, line: int) -> None:
        """Scroll so that a line is the first on the screen, as far as the editor goes."""
        rows = 0
        block = self._editor.document().firstBlock()
        while block.isValid() and block.blockNumber() < line:
            rows += block.lineCount()
            block = block.next()
        self._editor.verticalScrollBar().setValue(rows)

    def _scroll(self, command: Command) -> None:
        lines = self._lines()
        pos = self._pos(lines)
        top, height, max_top = self._view()
        scrolled = scroll(
            command.name,
            command.count,
            top=top,
            line=pos.line,
            height=height,
            lines=len(lines),
            max_top=max_top,
            amount=self._scroll_amount,
        )
        if scrolled is None:
            return
        self._scroll_amount = scrolled.amount
        want = self._wanted()
        self._scroll_to(scrolled.top)
        # keep the cursor on a line that's fully on the screen, like vim
        first, last, _ = self._visible()
        line = min(max(scrolled.line, first), last)
        visual = self._mode in VISUAL_MODES
        text = lines[line]
        if not scrolled.keep_column:
            self._go(lines, Pos(line, first_non_blank(text)))
            self._want_at = None
        elif line != pos.line:
            if want is None:
                want = screen_col(lines[pos.line], pos.col, self._tabstop())
            col = column_for(text, want, visual, self._tabstop())
            self._go(lines, Pos(line, col))
            self._want = want
            self._want_at = self._where()

    def _on_cursor_moved(self) -> None:
        """Outside Insert mode, keep the cursor on a character, never after the last
        one, and never inside one (an app or Qt's flag bug can put it there)."""
        if not self._enabled or self._busy or self._mode is Mode.INSERT:
            return
        cursor = self._editor.textCursor()
        if self._mode in VISUAL_MODES:
            self._visual_cursor_moved(cursor)
            return
        if cursor.hasSelection():
            if self._mouse_down:
                self._adopt_selection(cursor)
            else:
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
        """A block cursor in Normal mode, the editor's own cursor in Insert mode. In
        Visual mode the editor's cursor is hidden and the Caret draws vim's."""
        visual = self._enabled and self._mode in VISUAL_MODES and self._end is not None
        if self._enabled and self._mode is not Mode.INSERT:
            if not self._block_on:
                self._plain_width = self._editor.cursorWidth()
                self._block_on = True
            self._set_cursor_width(0 if visual else char_width(self._editor, self._position()))
        elif self._block_on:
            self._block_on = False
            self._set_cursor_width(self._plain_width)
        self._hide_editor_cursor(visual)
        # a read-only editor draws no cursor of its own
        no_cursor = not self._editor.textInteractionFlags() & DRAWS_CURSOR
        normal = self._enabled and self._mode is Mode.NORMAL and no_cursor
        self._caret.show_at(self._position() if visual or normal else None)

    def _set_cursor_width(self, width: int) -> None:
        """Qt repaints only the cursor's new area when its width changes, so the block
        turning into Insert mode's line left the rest of the block on screen."""
        if self._editor.cursorWidth() != width:
            self._editor.viewport().update(self._editor.cursorRect())
            self._editor.setCursorWidth(width)

    def _hide_editor_cursor(self, hide: bool) -> None:
        """Width 0 doesn't hide the editor's cursor everywhere: on a screen scaled by a
        fraction (125%, 150%) Qt still draws a thin blinking line. So in Visual mode the
        editor stops taking keys to edit (vim takes them anyway), and then Qt draws no
        cursor. Meanwhile isReadOnly() is True. If the app changes the flags meanwhile
        (setReadOnly, or other flags), its change stays."""
        flags = self._editor.textInteractionFlags()
        if hide:
            if self._saved_flags is None and flags & DRAWS_CURSOR:
                self._saved_flags = flags
                self._editor.setTextInteractionFlags(flags & ~DRAWS_CURSOR)
        elif self._saved_flags is not None:
            if flags == self._saved_flags & ~DRAWS_CURSOR:
                self._editor.setTextInteractionFlags(self._saved_flags)
            self._saved_flags = None

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
        empty = takes_nothing(r, self._has_no_lines(lines))
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
        every_line = r.linewise and r.start.line == 0 and r.end.line == len(lines) - 1
        document = self._editor.document()
        steps = document.availableUndoSteps()
        with self._change(start) as edit:
            edit.setPosition(begin)
            edit.setPosition(end, KEEP_ANCHOR)
            edit.removeSelectedText()
        if every_line:
            if document.availableUndoSteps() == steps:
                self._done.append(UndoStep(start, self._no_lines, in_qt=False))
                self._undone.clear()
            self._no_lines = True
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
        if r.linewise and r.end.line > r.start.line:
            # vim deletes the lines below the first one with the cursor a line down, so
            # that's where its undo puts it back
            start = Pos(start.line + 1, start.col)
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

    def _start_visual_command(self, command: Command) -> None:
        self._start_visual(Mode.VISUAL if command.name == "v" else Mode.VISUAL_LINE)

    def _start_visual(self, mode: Mode) -> None:
        document = self._editor.document()
        position = self._editor.textCursor().position()
        self._anchor = QTextCursor(document)
        self._anchor.setPosition(position)
        self._end = QTextCursor(document)
        self._end.setPosition(position)
        self._set_mode(mode)
        self._show_visual()

    def _switch_visual(self, command: Command) -> None:
        """v or V in Visual mode: the other kind of Visual mode, or back to Normal."""
        mode = Mode.VISUAL if command.name == "v" else Mode.VISUAL_LINE
        if mode is self._mode:
            self._leave_visual()
        else:
            self._set_mode(mode)
            self._show_visual()

    def _swap_ends(self, command: Command) -> None:
        """o in Visual mode: the cursor goes to the other end of the selection."""
        self._anchor, self._end = self._end, self._anchor
        self._want_at = None
        self._show_visual()

    def _selection(self, lines: Lines) -> tuple[Pos, Pos]:
        """The two ends of the Visual selection: where it started, and the cursor."""
        assert self._anchor is not None and self._end is not None
        return (
            self._from_qt(lines, self._anchor.position()),
            self._from_qt(lines, self._end.position()),
        )

    def _qt_selection(self, lines: Lines) -> tuple[int, int]:
        """The editor's anchor and position that show the Visual selection."""
        anchor, end = self._selection(lines)
        r = visual_range(lines, anchor, end, self._mode is Mode.VISUAL_LINE)
        if r.linewise:
            document = self._editor.document()
            low = document.findBlockByNumber(r.start.line).position()
            last = document.findBlockByNumber(r.end.line)
            high = last.position() + last.length() - 1
        else:
            low, high = self._to_qt(lines, r.start), self._to_qt(lines, r.end)
        return (low, high) if anchor <= end else (high, low)

    def _show_visual(self) -> None:
        """Set the editor's selection to the Visual one, and draw the cursor."""
        anchor, position = self._qt_selection(self._lines())
        cursor = self._editor.textCursor()
        if (cursor.anchor(), cursor.position()) != (anchor, position):
            cursor.setPosition(anchor)
            cursor.setPosition(position, KEEP_ANCHOR)
            self._busy = True
            try:
                self._editor.setTextCursor(cursor)
            finally:
                self._busy = False
        self._update_cursor_width()

    def _adopt_selection(self, cursor: QTextCursor) -> None:
        """Visual mode for a selection the mouse or the app made: the same characters,
        with vim's cursor on the last one at the editor's cursor end."""
        lines = self._lines()
        low = min(cursor.anchor(), cursor.position())
        high = max(cursor.anchor(), cursor.position())
        first = self._from_qt(lines, low)
        last = self._from_qt(lines, high)
        if last.col > 0:
            last = Pos(last.line, last.col - 1)
        elif last.line > first.line:
            last = Pos(last.line - 1, len(lines[last.line - 1]))
        anchor, end = (first, last) if cursor.position() == high else (last, first)
        document = self._editor.document()
        self._anchor = QTextCursor(document)
        self._anchor.setPosition(self._to_qt(lines, anchor))
        self._end = QTextCursor(document)
        self._end.setPosition(self._to_qt(lines, end))
        self._want_at = None
        self._set_mode(Mode.VISUAL)

    def _visual_cursor_moved(self, cursor: QTextCursor) -> None:
        """The editor's cursor moved in Visual mode, and not by vim: a click, a drag, or
        the app. Text changes move both ends along, which shows nothing new."""
        valid = (
            self._anchor is not None
            and self._anchor.document() is self._editor.document()
            and not self._mouse_down
        )
        if valid and self._qt_selection(self._lines()) == (cursor.anchor(), cursor.position()):
            self._update_cursor_width()
        elif cursor.hasSelection():
            self._adopt_selection(cursor)
        else:
            # a click, or the app put the cursor somewhere: back to Normal mode there
            self._drop_visual()
            self._set_mode(Mode.NORMAL)
            self._on_cursor_moved()

    def _drop_visual(self) -> None:
        """Forget the Visual selection; the editor's selection stays as it is."""
        self._anchor = self._end = None
        self._caret.show_at(None)

    def _leave_visual(self) -> Lines:
        """Back to Normal mode with the cursor at vim's cursor, kept on a character."""
        lines = self._lines()
        _, end = self._selection(lines)
        self._drop_visual()
        self._set_mode(Mode.NORMAL)
        self._busy = True
        try:
            self._put(lines, end)
        finally:
            self._busy = False
        return lines

    def _visual_range(self) -> tuple[Lines, Range, Pos]:
        """End Visual mode for an operator: the text, the range it acts on, and where
        it starts (see visual_start)."""
        lines = self._lines()
        anchor, end = self._selection(lines)
        linewise = self._mode is Mode.VISUAL_LINE
        r = visual_range(lines, anchor, end, linewise)
        start = visual_start(anchor, end, linewise)
        self._leave_visual()
        return lines, r, start

    def _visual_operate(self, command: Command) -> None:
        name = command.name
        lines, r, start = self._visual_range()
        empty = takes_nothing(r, self._has_no_lines(lines))
        if not empty or name == "y":
            self._store(range_text(lines, r), r.linewise)
        if name == "y":
            self._put(lines, start)
            self._want_at = None
        elif name == "d":
            if empty:
                self._put(lines, start)
            else:
                self._delete(lines, r, start)
        else:
            self._change_text(lines, r, start, empty)

    def _visual_paste(self, command: Command) -> None:
        """p in Visual mode: the register's text takes the selection's place, and the
        selection goes into the register. Whole lines put in part of a line go on lines
        of their own; part of a line put over whole lines becomes a line."""
        count = command.count or 1
        register = self._read_register()
        lines, r, start = self._visual_range()
        no_lines = self._has_no_lines(lines)
        empty = takes_nothing(r, no_lines)
        deleted = range_text(lines, r)
        if not register.text:
            if not empty:
                self._store(deleted, r.linewise)
                self._delete(lines, r, start)
            return
        body = register.text.removesuffix("\n") if register.linewise else register.text
        document = self._editor.document()
        with self._change(start) as edit:
            if r.linewise:
                first = document.findBlockByNumber(r.start.line)
                last = document.findBlockByNumber(r.end.line)
                begin = first.position()
                edit.setPosition(begin)
                edit.setPosition(last.position() + last.length() - 1, KEEP_ANCHOR)
                chunk = "\n".join([body] * count)
            else:
                begin, end = self._span(lines, r)
                edit.setPosition(begin)
                edit.setPosition(end, KEEP_ANCHOR)
                if register.linewise:
                    # with no lines there's no line to split: they go below one, like p
                    chunk = "\n" + "\n".join([body] * count) + ("" if no_lines else "\n")
                else:
                    chunk = body * count
            edit.insertText(chunk)
        if not empty:
            self._store(deleted, r.linewise)
        lines = self._lines()
        if r.linewise or register.linewise:
            line = r.start.line + (not r.linewise)
            self._put(lines, Pos(line, first_non_blank(lines[line])))
        elif "\n" in chunk:
            self._put(lines, self._from_qt(lines, begin))
        else:
            self._put(lines, self._from_qt(lines, begin + utf16_len(chunk) - 1))

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

    def _store(self, text: str, linewise: bool) -> None:
        global _register
        _register = Register(text, linewise)
        if self.clipboard:
            QGuiApplication.clipboard().setText(text)

    def _read_register(self) -> Register:
        """What p pastes. From the clipboard: if it still holds our last yank, that
        yank's kind; otherwise whole lines if the text ends in a newline."""
        if not self.clipboard:
            return _register
        text = QGuiApplication.clipboard().text().replace("\r\n", "\n")
        if text == _register.text:
            return _register
        return Register(text, linewise=text.endswith("\n"))

    def _check_synced(self) -> None:
        """Forget where `u` goes if the document changed without vim, since its undo
        steps no longer match the ones vim knows."""
        version = self._version()
        if version != self._synced:
            self._done.clear()
            self._undone.clear()
            self._synced = version
            # like vim reading a file: an empty one has no lines
            self._no_lines = not self._editor.document().toRawText()

    def _has_no_lines(self, lines: Lines) -> bool:
        self._check_synced()
        return self._no_lines and len(lines) == 1 and not lines[0]

    @contextmanager
    def _change(self, saved: Pos) -> Iterator[QTextCursor]:
        """One Normal mode command's edits, as one undo step. saved: where `u` puts
        the cursor back."""
        document = self._editor.document()
        self._check_synced()
        no_lines = self._no_lines
        steps: list[None] = []

        def on_step() -> None:
            steps.append(None)

        # the revision isn't enough: an edit that changes nothing (`dd` on an empty
        # text) counts as a revision but adds no undo step
        document.undoCommandAdded.connect(on_step)
        edit = QTextCursor(document)
        self._busy = True
        edit.beginEditBlock()
        try:
            yield edit
        finally:
            edit.endEditBlock()
            self._busy = False
            document.undoCommandAdded.disconnect(on_step)
        if steps:
            self._done.append(UndoStep(saved, no_lines))
            self._undone.clear()
            self._no_lines = False
        self._synced = self._version()

    def _undo_command(self, command: Command) -> None:
        self._undo(command.count or 1, redo=command.name == "<C-r>")

    def _undo(self, count: int, redo: bool) -> None:
        document = self._editor.document()
        self._check_synced()
        source, target = (self._undone, self._done) if redo else (self._done, self._undone)
        changed: list[tuple[int, int]] = []
        saved: Pos | None = None

        def on_change(position: int, removed: int, added: int) -> None:
            changed.append((position, position + added))

        for _ in range(count):
            if source and not source[-1].in_qt:
                step = source.pop()
                saved = step.cursor
                target.append(UndoStep(saved, self._no_lines, in_qt=False))
                self._no_lines = step.no_lines
                continue
            if not (document.isRedoAvailable() if redo else document.isUndoAvailable()):
                break
            step = source.pop() if source else None
            saved = step.cursor if step else None
            target.append(UndoStep(saved, self._no_lines))
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
            self._no_lines = step.no_lines if step else not document.toRawText()
        self._synced = self._version()
        lines = self._lines()
        if changed:
            first = self._from_qt(lines, min(start for start, _ in changed)).line
            last = self._from_qt(lines, max(end for _, end in changed)).line
            self._put(lines, undo_cursor(lines, saved, first, last))
        else:
            self._put(lines, self._pos(lines))

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
            no_lines=self._no_lines,
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
        insert.edited = True
        if insert.saved is None:
            # the session's own document: the editor may show another one by now, or be
            # half gone, as when the app quits in Insert mode
            document = insert.document
            insert.saved = _from_qt(document, Lines(_Blocks(document)), position)

    def _on_redo_available(self, available: bool) -> None:
        if available and self._insert is not None and not self._busy:
            self._insert.messy = True

    def _leave_insert(self) -> None:
        insert = self._insert
        if insert is not None and insert.document is self._editor.document():
            if insert.count > 1:
                self._repeat(insert)
            self._end_insert(insert)
        else:
            # A tab switch may have deleted the old document. Drop its session
            # before reading it again or repeating its text in the new one.
            self._drop_insert()
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
        """End a session without making it one undo step."""
        insert = self._insert
        if insert is not None:
            self._disconnect(insert)
            self._done.clear()
            self._undone.clear()
            self._synced = self._version()
            if insert.document is not self._editor.document():
                self._no_lines = not self._editor.document().toRawText()
            elif insert.edited:
                self._no_lines = False

    def _end_insert(self, insert: _Insert) -> None:
        self._disconnect(insert)
        document = insert.document
        final = document.toRawText()
        changed = final != insert.origin
        if insert.messy:
            # the app's own undo ran: leave its steps as they are
            self._done.clear()
            self._undone.clear()
        elif insert.levels >= 2 or insert.merged_outside or (insert.levels and not changed):
            if not self._regroup(insert, final):
                self._done.clear()
                self._undone.clear()
            elif changed:
                self._done.append(UndoStep(insert.saved, insert.no_lines))
                self._undone.clear()
        elif changed:
            self._done.append(UndoStep(insert.saved, insert.no_lines))
            self._undone.clear()
        if insert.edited and insert.no_lines and not changed:
            # typed and deleted again: Qt has no step, but vim's goes back to no lines
            self._done.append(UndoStep(insert.saved, True, in_qt=False))
            self._undone.clear()
        if insert.edited:
            self._no_lines = False
        self._synced = self._version()

    def _regroup(self, insert: _Insert, final: str) -> bool:
        """Make the session one undo step: undo its steps, then make its whole change
        again in one edit block. False if the steps didn't lead back to where the
        session started; then everything is put back as it was."""
        document = insert.document
        modified = document.isModified()
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
            # The app may have saved during Insert mode. Regrouping undo steps
            # leaves the text as it was, so it must keep that saved state too.
            document.setModified(modified)
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


def _from_qt(document: QTextDocument, lines: Lines, position: int) -> Pos:
    """Like Lines.from_qt, but the document finds the line."""
    block = document.findBlock(position)
    if not block.isValid():
        block = document.lastBlock()
    line = block.blockNumber()
    return Pos(line, lines.col_at(line, position - block.position()))


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
