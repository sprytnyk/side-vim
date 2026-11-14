"""Qt key events as vim key tokens: "w", "G", "<Esc>", "<C-r>", "<Left>".

None means the key isn't for vim: a modifier on its own, a key with Cmd (macOS) or
Meta, or a key with no text that vim doesn't know (PageUp, F1). Those go to the editor
or the app as usual.
"""

import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QKeyEvent

ESC = "<Esc>"
IS_MAC = sys.platform == "darwin"

_K = Qt.Key
_M = Qt.KeyboardModifier

# Keys without text, by their vim name. Shift and Alt add "S-" and "A-".
NAMED = {
    _K.Key_Escape: "Esc",
    _K.Key_Left: "Left",
    _K.Key_Right: "Right",
    _K.Key_Up: "Up",
    _K.Key_Down: "Down",
    _K.Key_Home: "Home",
    _K.Key_End: "End",
    _K.Key_Return: "CR",
    _K.Key_Enter: "CR",
    _K.Key_Backspace: "BS",
    _K.Key_Delete: "Del",
    _K.Key_Tab: "Tab",
    _K.Key_Backtab: "Tab",
    _K.Key_Insert: "Insert",
}

MODIFIER_KEYS = frozenset(
    {
        _K.Key_Shift,
        _K.Key_Control,
        _K.Key_Meta,
        _K.Key_Alt,
        _K.Key_AltGr,
        _K.Key_CapsLock,
        _K.Key_NumLock,
        _K.Key_ScrollLock,
        _K.Key_Super_L,
        _K.Key_Super_R,
        _K.Key_Hyper_L,
        _K.Key_Hyper_R,
        _K.Key_Mode_switch,
    }
)


def control_modifier(mac: bool = IS_MAC) -> Qt.KeyboardModifier:
    """The modifier the physical Control key arrives as. On macOS Qt swaps Ctrl and Cmd,
    so Control arrives as Meta, unless the app turned the swap off."""
    swapped = not QCoreApplication.testAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta)
    return _M.MetaModifier if mac and swapped else _M.ControlModifier


def _name(key: int) -> str | None:
    """A key's name for a Ctrl token: the lower case character, or a NAMED name."""
    if key in NAMED:
        return NAMED[key]
    if key < 0x110000 and chr(key).isprintable():
        return chr(key).lower()
    return None


def key_token(event: QKeyEvent, mac: bool = IS_MAC) -> str | None:
    """The vim token for a key press, or None if the key isn't for vim."""
    key = event.key()
    if key in MODIFIER_KEYS:
        return None
    mods = event.modifiers() & ~(_M.KeypadModifier | _M.GroupSwitchModifier)
    ctrl = control_modifier(mac)
    # Cmd on macOS, the Meta (Super) key elsewhere: always the app's
    if mods & (_M.ControlModifier | _M.MetaModifier) & ~ctrl:
        return None
    shift = "S-" if mods & _M.ShiftModifier else ""
    alt = "A-" if mods & _M.AltModifier else ""
    text = event.text()

    if mods & ctrl:
        if (key == _K.Key_BracketLeft or text == "\x1b") and not (shift or alt):
            return ESC
        name = _name(key)
        return f"<C-{alt}{shift}{name}>" if name else None

    if key in NAMED:
        if key == _K.Key_Escape:
            return ESC
        return f"<{alt}{shift}{NAMED[key]}>"
    if text == "\x1b":
        return ESC
    if text and text.isprintable():
        # on macOS, Option is how people type characters, so its text is just text
        return f"<A-{text}>" if alt and not mac else text
    return None
