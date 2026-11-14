"""Qt key events as vim tokens, on Linux/Windows and on macOS."""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from side_vim.keys import ESC, control_modifier, key_token, map_layout
from side_vim.layouts import UKRAINIAN

K = Qt.Key
M = Qt.KeyboardModifier
NONE = M.NoModifier
FAMILY = "\U0001f468\u200d\U0001f469\u200d\U0001f467"


def token(
    key: int, mods: Qt.KeyboardModifier = NONE, text: str = "", mac: bool = False
) -> str | None:
    return key_token(QKeyEvent(QEvent.Type.KeyPress, key, mods, text), mac=mac)


@pytest.mark.parametrize(
    ("key", "mods", "text", "expected"),
    [
        (K.Key_W, NONE, "w", "w"),
        (K.Key_W, M.ShiftModifier, "W", "W"),
        (K.Key_3, NONE, "3", "3"),
        (K.Key_3, M.KeypadModifier, "3", "3"),
        (K.Key_Dollar, M.ShiftModifier, "$", "$"),
        (K.Key_AsciiCircum, M.ShiftModifier, "^", "^"),
        (K.Key_Space, NONE, " ", " "),
        (0x41A, NONE, "к", "к"),
        (0x416, M.ShiftModifier, "Ж", "Ж"),
        (K.Key_Escape, NONE, "\x1b", ESC),
        (K.Key_Escape, M.ShiftModifier, "", ESC),
        (K.Key_BracketLeft, M.ControlModifier, "\x1b", ESC),
        (K.Key_BracketLeft, M.ControlModifier, "", ESC),
        (K.Key_R, M.ControlModifier, "\x12", "<C-r>"),
        (K.Key_R, M.ControlModifier | M.ShiftModifier, "\x12", "<C-S-r>"),
        (K.Key_V, M.ControlModifier, "\x16", "<C-v>"),
        (0x41A, M.ControlModifier, "", "<C-к>"),
        (K.Key_Left, M.ControlModifier, "", "<C-Left>"),
        (K.Key_Left, NONE, "", "<Left>"),
        (K.Key_Left, M.KeypadModifier, "", "<Left>"),
        (K.Key_Left, M.ShiftModifier, "", "<S-Left>"),
        (K.Key_Right, NONE, "", "<Right>"),
        (K.Key_Up, NONE, "", "<Up>"),
        (K.Key_Down, NONE, "", "<Down>"),
        (K.Key_Home, NONE, "", "<Home>"),
        (K.Key_End, NONE, "", "<End>"),
        (K.Key_Return, NONE, "\r", "<CR>"),
        (K.Key_Enter, M.KeypadModifier, "\r", "<CR>"),
        (K.Key_Backspace, NONE, "\x08", "<BS>"),
        (K.Key_Delete, NONE, "\x7f", "<Del>"),
        (K.Key_Tab, NONE, "\t", "<Tab>"),
        (K.Key_Backtab, M.ShiftModifier, "", "<S-Tab>"),
        (K.Key_Insert, NONE, "", "<Insert>"),
        (K.Key_X, M.AltModifier, "x", "<A-x>"),
        (K.Key_X, M.MetaModifier, "x", None),  # the Super key
        (K.Key_PageDown, NONE, "", None),
        (K.Key_F1, NONE, "", None),
        (K.Key_Shift, M.ShiftModifier, "", None),
        (K.Key_Control, M.ControlModifier, "", None),
        (K.Key_Alt, M.AltModifier, "", None),
        (K.Key_CapsLock, NONE, "", None),
        (K.Key_W, M.GroupSwitchModifier, "w", "w"),  # AltGr
        (K.Key_unknown, NONE, FAMILY, FAMILY),  # joined with U+200D
        (K.Key_unknown, NONE, "\U0001f1fa\U0001f1e6", "\U0001f1fa\U0001f1e6"),
        (K.Key_unknown, NONE, "e\u0301", "e\u0301"),
        (K.Key_unknown, NONE, "\x00", None),
        (K.Key_unknown, NONE, "\ue000", None),  # private use
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
        (K.Key_R, M.MetaModifier, "\x12", "<C-r>"),
        (K.Key_R, M.ControlModifier, "r", None),
        (K.Key_V, M.ControlModifier, "v", None),
        (K.Key_BracketLeft, M.MetaModifier, "\x1b", ESC),
        (K.Key_BracketLeft, M.ControlModifier, "[", None),
        (K.Key_Escape, NONE, "\x1b", ESC),
        (K.Key_W, NONE, "w", "w"),
        # Option types characters on macOS
        (K.Key_D, M.AltModifier, "∂", "∂"),
        (K.Key_Left, M.AltModifier, "", "<A-Left>"),
    ],
)
def test_macos(
    qapp: QApplication, key: int, mods: Qt.KeyboardModifier, text: str, expected: str | None
) -> None:
    assert token(key, mods, text, mac=True) == expected


def test_control_modifier(qapp: QApplication) -> None:
    assert control_modifier(mac=False) == M.ControlModifier
    assert control_modifier(mac=True) == M.MetaModifier
    swap = Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta
    QApplication.setAttribute(swap, True)
    try:
        assert control_modifier(mac=True) == M.ControlModifier
        assert token(K.Key_R, M.ControlModifier, "\x12", mac=True) == "<C-r>"
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
