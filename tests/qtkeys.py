"""Send keys to a widget the way a user types them, written in vim notation."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QWidget

from side_vim import VimMode
from side_vim.keys import control_modifier
from side_vim.motions import Pos
from side_vim.notation import tokens
from side_vim.text import PARAGRAPH_SEPARATOR, Lines

NAMES = {
    "Esc": Qt.Key.Key_Escape,
    "CR": Qt.Key.Key_Return,
    "BS": Qt.Key.Key_Backspace,
    "Del": Qt.Key.Key_Delete,
    "Tab": Qt.Key.Key_Tab,
    "Insert": Qt.Key.Key_Insert,
    "Left": Qt.Key.Key_Left,
    "Right": Qt.Key.Key_Right,
    "Up": Qt.Key.Key_Up,
    "Down": Qt.Key.Key_Down,
    "Home": Qt.Key.Key_Home,
    "End": Qt.Key.Key_End,
    "PageDown": Qt.Key.Key_PageDown,
}
MODIFIERS = {
    "S": Qt.KeyboardModifier.ShiftModifier,
    "A": Qt.KeyboardModifier.AltModifier,
    "M": Qt.KeyboardModifier.MetaModifier,
}


def press(widget: QWidget, token: str) -> None:
    """One key: a character, or a name like <Esc>, <C-r>, <S-Left>."""
    if len(token) > 1 and token.startswith("<"):
        *mods, name = token[1:-1].split("-")
        modifiers = Qt.KeyboardModifier.NoModifier
        for m in mods:
            modifiers |= control_modifier() if m == "C" else MODIFIERS[m]
        if name in NAMES:
            QTest.keyClick(widget, NAMES[name], modifiers)
        elif name.isascii():
            QTest.keyClick(widget, Qt.Key(ord(name.upper())), modifiers)
        else:
            type_text(widget, name, modifiers)
    elif token.isascii():
        QTest.keyClick(widget, token)
    else:
        type_text(widget, token)


def type_text(
    widget: QWidget, text: str, modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier
) -> None:
    """Text QTest can't type (anything not ASCII), as one key press."""
    key = ord(text.upper()) if len(text) == 1 else Qt.Key.Key_unknown
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        event = QKeyEvent(kind, key, modifiers, text)
        QApplication.sendEvent(widget, event)


def send(widget: QWidget, keys: str) -> None:
    for token in tokens(keys):
        press(widget, token)


def plain(raw: str) -> str:
    return raw.replace(PARAGRAPH_SEPARATOR, "\n")


def text_of(editor: QPlainTextEdit) -> str:
    return plain(editor.document().toRawText())


def cursor_of(editor: QPlainTextEdit) -> Pos:
    lines = Lines(editor.document().toRawText())
    return lines.from_qt(editor.textCursor().position())


def put_cursor(editor: QPlainTextEdit, pos: Pos) -> None:
    lines = Lines(editor.document().toRawText())
    cursor = editor.textCursor()
    cursor.setPosition(lines.to_qt(pos))
    editor.setTextCursor(cursor)


def start_vim(editor: QPlainTextEdit, text: str, line: int = 0, col: int = 0) -> VimMode:
    editor.setPlainText(text)
    vim = VimMode(editor)
    put_cursor(editor, Pos(line, col))
    return vim
