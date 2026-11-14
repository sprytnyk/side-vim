"""Qt key events as vim tokens, on Linux/Windows and on macOS."""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from side_vim.keys import ESC, control_modifier, key_token, map_layout
from side_vim.layouts import UKRAINIAN

NONE = Qt.KeyboardModifier.NoModifier
FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"


def token(
    key: int, mods: Qt.KeyboardModifier = NONE, text: str = "", mac: bool = False
) -> str | None:
    return key_token(QKeyEvent(QEvent.Type.KeyPress, key, mods, text), mac=mac)


@pytest.mark.parametrize(
    ("key", "mods", "text", "expected"),
    [
        (Qt.Key.Key_W, NONE, "w", "w"),
        (Qt.Key.Key_W, Qt.KeyboardModifier.ShiftModifier, "W", "W"),
        (Qt.Key.Key_3, NONE, "3", "3"),
        (Qt.Key.Key_3, Qt.KeyboardModifier.KeypadModifier, "3", "3"),
        (Qt.Key.Key_Dollar, Qt.KeyboardModifier.ShiftModifier, "$", "$"),
        (Qt.Key.Key_AsciiCircum, Qt.KeyboardModifier.ShiftModifier, "^", "^"),
        (Qt.Key.Key_Space, NONE, " ", " "),
        (0x41A, NONE, "к", "к"),
        (0x416, Qt.KeyboardModifier.ShiftModifier, "Ж", "Ж"),
        (Qt.Key.Key_Escape, NONE, "\x1b", ESC),
        (Qt.Key.Key_Escape, Qt.KeyboardModifier.ShiftModifier, "", ESC),
        (Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.ControlModifier, "\x1b", ESC),
        (Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.ControlModifier, "", ESC),
        (Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier, "\x12", "<C-r>"),
        (
            Qt.Key.Key_R,
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
            "\x12",
            "<C-S-r>",
        ),
        (Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier, "\x16", "<C-v>"),
        (0x41A, Qt.KeyboardModifier.ControlModifier, "", "<C-к>"),
        (Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier, "", "<C-Left>"),
        (Qt.Key.Key_Left, NONE, "", "<Left>"),
        (Qt.Key.Key_Left, Qt.KeyboardModifier.KeypadModifier, "", "<Left>"),
        (Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier, "", "<S-Left>"),
        (Qt.Key.Key_Right, NONE, "", "<Right>"),
        (Qt.Key.Key_Up, NONE, "", "<Up>"),
        (Qt.Key.Key_Down, NONE, "", "<Down>"),
        (Qt.Key.Key_Home, NONE, "", "<Home>"),
        (Qt.Key.Key_End, NONE, "", "<End>"),
        (Qt.Key.Key_Return, NONE, "\r", "<CR>"),
        (Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier, "\r", "<CR>"),
        (Qt.Key.Key_Backspace, NONE, "\x08", "<BS>"),
        (Qt.Key.Key_Delete, NONE, "\x7f", "<Del>"),
        (Qt.Key.Key_Tab, NONE, "\t", "<Tab>"),
        (Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier, "", "<S-Tab>"),
        (Qt.Key.Key_Insert, NONE, "", "<Insert>"),
        (Qt.Key.Key_X, Qt.KeyboardModifier.AltModifier, "x", "<A-x>"),
        (Qt.Key.Key_X, Qt.KeyboardModifier.MetaModifier, "x", None),  # the Super key
        (Qt.Key.Key_PageDown, NONE, "", None),
        (Qt.Key.Key_F1, NONE, "", None),
        (Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier, "", None),
        (Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier, "", None),
        (Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier, "", None),
        (Qt.Key.Key_CapsLock, NONE, "", None),
        (Qt.Key.Key_W, Qt.KeyboardModifier.GroupSwitchModifier, "w", "w"),  # AltGr
        (Qt.Key.Key_unknown, NONE, FAMILY, FAMILY),  # joined with U+200D
        (Qt.Key.Key_unknown, NONE, "\U0001f1fa\U0001f1e6", "\U0001f1fa\U0001f1e6"),
        (Qt.Key.Key_unknown, NONE, "e\u0301", "e\u0301"),
        (Qt.Key.Key_unknown, NONE, "\x00", None),
        (Qt.Key.Key_unknown, NONE, "\ue000", None),  # private use
    ],
)
def test_linux_and_windows(
    qapp: QApplication, key: int, mods: Qt.KeyboardModifier, text: str, expected: str | None
) -> None:
    assert token(key, mods, text) == expected


@pytest.mark.parametrize(
    ("key", "mods", "text", "expected"),
    [
        # Qt swaps them: the physical Control key arrives as Meta, Cmd as Control
        (Qt.Key.Key_R, Qt.KeyboardModifier.MetaModifier, "\x12", "<C-r>"),
        (Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier, "r", None),
        (Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier, "v", None),
        (Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.MetaModifier, "\x1b", ESC),
        (Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.ControlModifier, "[", None),
        (Qt.Key.Key_Escape, NONE, "\x1b", ESC),
        (Qt.Key.Key_W, NONE, "w", "w"),
        # Option types characters on macOS
        (Qt.Key.Key_D, Qt.KeyboardModifier.AltModifier, "∂", "∂"),
        (Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier, "", "<A-Left>"),
    ],
)
def test_macos(
    qapp: QApplication, key: int, mods: Qt.KeyboardModifier, text: str, expected: str | None
) -> None:
    assert token(key, mods, text, mac=True) == expected


def test_control_modifier(qapp: QApplication) -> None:
    assert control_modifier(mac=False) == Qt.KeyboardModifier.ControlModifier
    assert control_modifier(mac=True) == Qt.KeyboardModifier.MetaModifier
    swap = Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta
    QApplication.setAttribute(swap, True)
    try:
        assert control_modifier(mac=True) == Qt.KeyboardModifier.ControlModifier
        assert token(Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier, "\x12", mac=True) == "<C-r>"
    finally:
        QApplication.setAttribute(swap, False)


def test_the_ukrainian_map_matches_the_keyboard() -> None:
    rows = [
        ("йцукенгшщзхї", "qwertyuiop[]", "QWERTYUIOP{}"),
        ("фівапролджє", "asdfghjkl;'", 'ASDFGHJKL:"'),
        ("ячсмитьбю", "zxcvbnm,.", "ZXCVBNM<>"),
    ]
    for cyrillic, lower, upper in rows:
        for ch, a, b in zip(cyrillic, lower, upper, strict=True):
            assert UKRAINIAN[ch] == a
            assert UKRAINIAN[ch.upper()] == b
    assert len(UKRAINIAN) == 2 * sum(len(row[0]) for row in rows)
    assert "ґ" not in UKRAINIAN
    assert "Ґ" not in UKRAINIAN


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("к", "r"),
        ("К", "R"),
        ("х", "["),
        ("Ж", ":"),
        ("<C-к>", "<C-r>"),
        ("<C-S-к>", "<C-S-r>"),
        ("<C-A-ш>", "<C-A-i>"),
        ("<C-х>", ESC),  # the key of Ctrl+[
        ("<C-S-х>", "<C-S-[>"),
        ("<C-Left>", "<C-Left>"),
        (".", "."),
        ("w", "w"),
        ("ґ", "ґ"),
        ("<Esc>", "<Esc>"),
    ],
)
def test_map_layout(token: str, expected: str) -> None:
    assert map_layout(token, UKRAINIAN) == expected
    assert map_layout(token, None) == token
