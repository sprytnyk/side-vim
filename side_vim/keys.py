"""Qt key events as vim key tokens: "w", "G", "<Esc>", "<C-r>", "<Left>".

None means the key isn't for vim: a modifier on its own, a key with Cmd (macOS) or
Meta, or a key with no text that vim doesn't know (PageUp, F1). Those go to the editor
or the app as usual.
"""

import sys
import unicodedata

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QKeyEvent

ESC = "<Esc>"
IS_MAC = sys.platform == "darwin"

# Invisible characters used in emoji and Indic scripts.
JOINERS = frozenset({"\u200c", "\u200d"})

# Keys without text, by their vim name. Shift and Alt add "S-" and "A-".
NAMED = {
    Qt.Key.Key_Escape: "Esc",
    Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Up: "Up",
    Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End",
    Qt.Key.Key_Return: "CR",
    Qt.Key.Key_Enter: "CR",
    Qt.Key.Key_Backspace: "BS",
    Qt.Key.Key_Delete: "Del",
    Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Backtab: "Tab",
    Qt.Key.Key_Insert: "Insert",
}

MODIFIER_KEYS = frozenset(
    {
        Qt.Key.Key_Shift,
        Qt.Key.Key_Control,
        Qt.Key.Key_Meta,
        Qt.Key.Key_Alt,
        Qt.Key.Key_AltGr,
        Qt.Key.Key_CapsLock,
        Qt.Key.Key_NumLock,
        Qt.Key.Key_ScrollLock,
        Qt.Key.Key_Super_L,
        Qt.Key.Key_Super_R,
        Qt.Key.Key_Hyper_L,
        Qt.Key.Key_Hyper_R,
        Qt.Key.Key_Mode_switch,
    }
)


def map_layout(token: str, layout: dict[str, str] | None) -> str:
    """A key token with its letter mapped through a layout map: "к" -> "r",
    "<C-к>" -> "<C-r>", and "<C-х>" -> "<Esc>" like Ctrl+[. Tokens it doesn't know
    stay as they are."""
    if not layout:
        return token
    if token in layout:
        return layout[token]
    if token.startswith("<C-") and token.endswith(">"):
        head, _, name = token[1:-1].rpartition("-")
        mapped = layout.get(name)
        if mapped is not None and len(mapped) == 1:
            if head == "C" and mapped == "[":
                return ESC  # Ctrl+х is the key of Ctrl+[
            # Ctrl tokens use the lower case name, like key_token does
            return f"<{head}-{mapped.lower() if mapped.isalpha() else mapped}>"
    return token


def control_modifier(mac: bool = IS_MAC) -> Qt.KeyboardModifier:
    """The modifier the physical Control key arrives as. On macOS Qt swaps Ctrl and Cmd,
    so Control arrives as Meta, unless the app turned the swap off."""
    swapped = not QCoreApplication.testAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta)
    if mac and swapped:
        return Qt.KeyboardModifier.MetaModifier
    return Qt.KeyboardModifier.ControlModifier


def _name(key: int) -> str | None:
    """A key's name for a Ctrl token: the lower case character, or a NAMED name."""
    if key in NAMED:
        return NAMED[key]
    if key < 0x110000 and chr(key).isprintable():
        return chr(key).lower()
    return None


def _is_text(text: str) -> bool:
    """True if a key typed text. Not str.isprintable: that refuses the joiner in a
    family emoji, and the key would then type in Normal mode."""
    return bool(text) and all(unicodedata.category(ch)[0] != "C" or ch in JOINERS for ch in text)


def key_token(event: QKeyEvent, mac: bool = IS_MAC) -> str | None:
    """The vim token for a key press, or None if the key isn't for vim."""
    key = event.key()
    if key in MODIFIER_KEYS:
        return None
    mods = event.modifiers() & ~(
        Qt.KeyboardModifier.KeypadModifier | Qt.KeyboardModifier.GroupSwitchModifier
    )
    ctrl = control_modifier(mac)
    # Cmd on macOS, the Meta (Super) key elsewhere: always the app's
    if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier) & ~ctrl:
        return None
    shift = "S-" if mods & Qt.KeyboardModifier.ShiftModifier else ""
    alt = "A-" if mods & Qt.KeyboardModifier.AltModifier else ""
    text = event.text()

    if mods & ctrl:
        if (key == Qt.Key.Key_BracketLeft or text == "\x1b") and not (shift or alt):
            return ESC
        name = _name(key)
        return f"<C-{alt}{shift}{name}>" if name else None

    if key in NAMED:
        if key == Qt.Key.Key_Escape:
            return ESC
        return f"<{alt}{shift}{NAMED[key]}>"
    if text == "\x1b":
        return ESC
    if _is_text(text):
        # on macOS, Option is how people type characters, so its text is just text
        return f"<A-{text}>" if alt and not mac else text
    return None
