"""Check the demo's keys on a Mac with key events that go through macOS.

Run `make mac-keys` on a Mac with the English (ABC) layout active, and leave the
keyboard alone until it prints the results. The Ukrainian check also needs the
Ukrainian-PC layout installed; the script switches to it and back. The focus check
makes the app inactive for a moment and brings it back. The script saves the clipboard
first and puts it back at the end.

CGEventCreateKeyboardEvent takes the characters from the active layout. Each event
becomes an NSEvent posted to the app's own queue, so Qt reads it as a key from the
keyboard: keyDown, performKeyEquivalent and the Ctrl/Cmd swap. Posting to the app's
own queue needs no Accessibility permission. ctypes calls the system libraries, so
the script needs no extra packages.
"""

import sys
import traceback
from contextlib import contextmanager
from ctypes import (
    CDLL,
    CFUNCTYPE,
    c_bool,
    c_char_p,
    c_int32,
    c_long,
    c_uint16,
    c_uint64,
    c_ulong,
    c_void_p,
)
from ctypes.util import find_library

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import QKeyCombination, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox

from side_vim import Mode
from side_vim.__main__ import Demo, sample
from side_vim.keys import control_modifier

if sys.platform != "darwin":
    sys.exit("mac_keys.py runs only on macOS.")

FRAMEWORKS = "/System/Library/Frameworks"
objc = CDLL(find_library("objc"))
cg = CDLL(f"{FRAMEWORKS}/CoreGraphics.framework/CoreGraphics")
cf = CDLL(f"{FRAMEWORKS}/CoreFoundation.framework/CoreFoundation")
carbon = CDLL(f"{FRAMEWORKS}/Carbon.framework/Carbon")
CDLL(f"{FRAMEWORKS}/AppKit.framework/AppKit")

objc.objc_getClass.restype = c_void_p
objc.objc_getClass.argtypes = [c_char_p]
objc.sel_registerName.restype = c_void_p
objc.sel_registerName.argtypes = [c_char_p]

cg.CGEventCreateKeyboardEvent.restype = c_void_p
cg.CGEventCreateKeyboardEvent.argtypes = [c_void_p, c_uint16, c_bool]
cg.CGEventSetFlags.argtypes = [c_void_p, c_uint64]
cf.CFRelease.argtypes = [c_void_p]

SHIFT, CONTROL, COMMAND = 0x20000, 0x40000, 0x100000
# macOS marks the arrow keys as keys on the numeric pad and Fn keys
NUMERIC_PAD, SECONDARY_FN = 0x200000, 0x800000

# macOS key codes, named by what the key types on the English layout
KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28,
    "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38,
    "'": 39, "k": 40, ";": 41, "\\": 42, ",": 43, "/": 44, "n": 45, "m": 46, ".": 47,
    "Return": 36, "Tab": 48, " ": 49, "`": 50, "Delete": 51, "Esc": 53, "Left": 123,
}  # fmt: skip


def send(obj, selector: str, *args, restype: type = c_void_p, argtypes: tuple = ()):
    """Calls an Objective-C method."""
    method = CFUNCTYPE(restype, c_void_p, c_void_p, *argtypes)(("objc_msgSend", objc))
    return method(obj, objc.sel_registerName(selector.encode()), *args)


def objc_class(name: str):
    return objc.objc_getClass(name.encode())


def from_nsstring(ns) -> str:
    if not ns:
        return ""
    chars = send(ns, "UTF8String", restype=c_char_p)
    return chars.decode() if chars else ""


def nsapp():
    return send(objc_class("NSApplication"), "sharedApplication")


def make_event(keycode: int, down: bool, flags: int):
    event = cg.CGEventCreateKeyboardEvent(None, keycode, down)
    cg.CGEventSetFlags(event, flags)
    ns = send(objc_class("NSEvent"), "eventWithCGEvent:", event, argtypes=(c_void_p,))
    send(ns, "retain")
    cf.CFRelease(event)
    return ns


def post(keycode: int, flags: int = 0) -> list[str]:
    """Posts a key down and up. Returns the characters macOS gave the key down."""
    app = nsapp()
    chars = []
    for down in (True, False):
        ns = make_event(keycode, down, flags)
        if down:
            chars.append(from_nsstring(send(ns, "characters")))
        send(app, "postEvent:atStart:", ns, False, argtypes=(c_void_p, c_bool))
        send(ns, "release")
    return chars


def activate() -> None:
    send(nsapp(), "activateIgnoringOtherApps:", True, argtypes=(c_bool,))


carbon.TISCopyCurrentKeyboardInputSource.restype = c_void_p
carbon.TISCreateInputSourceList.restype = c_void_p
carbon.TISCreateInputSourceList.argtypes = [c_void_p, c_bool]
carbon.TISSelectInputSource.argtypes = [c_void_p]
carbon.TISSelectInputSource.restype = c_int32
carbon.TISGetInputSourceProperty.restype = c_void_p
carbon.TISGetInputSourceProperty.argtypes = [c_void_p, c_void_p]
cf.CFArrayGetCount.argtypes = [c_void_p]
cf.CFArrayGetCount.restype = c_long
cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_long]
cf.CFArrayGetValueAtIndex.restype = c_void_p
cf.CFRetain.argtypes = [c_void_p]
cf.CFRetain.restype = c_void_p

SOURCE_ID = c_void_p.in_dll(carbon, "kTISPropertyInputSourceID")


def source_id(source) -> str:
    return from_nsstring(carbon.TISGetInputSourceProperty(source, SOURCE_ID))


def current_source():
    return carbon.TISCopyCurrentKeyboardInputSource()


def find_source(wanted: str):
    sources = carbon.TISCreateInputSourceList(None, False)
    try:
        for i in range(cf.CFArrayGetCount(sources)):
            source = cf.CFArrayGetValueAtIndex(sources, i)
            if source_id(source) == wanted:
                return cf.CFRetain(source)
    finally:
        cf.CFRelease(sources)
    return None


def save_pasteboard():
    """Copies every item on the clipboard, with each type it has."""
    board = send(objc_class("NSPasteboard"), "generalPasteboard")
    items = send(board, "pasteboardItems")
    saved = []
    for i in range(send(items, "count", restype=c_ulong)):
        item = send(items, "objectAtIndex:", i, argtypes=(c_ulong,))
        types = send(item, "types")
        entry = []
        for j in range(send(types, "count", restype=c_ulong)):
            kind = send(types, "objectAtIndex:", j, argtypes=(c_ulong,))
            data = send(item, "dataForType:", kind, argtypes=(c_void_p,))
            if data:
                send(kind, "retain")
                send(data, "retain")
                entry.append((kind, data))
        saved.append(entry)
    return saved


def restore_pasteboard(saved) -> None:
    board = send(objc_class("NSPasteboard"), "generalPasteboard")
    send(board, "clearContents", restype=c_long)
    items = send(objc_class("NSMutableArray"), "array")
    for entry in saved:
        item = send(send(objc_class("NSPasteboardItem"), "alloc"), "init")
        for kind, data in entry:
            send(
                item, "setData:forType:", data, kind, restype=c_bool, argtypes=(c_void_p, c_void_p)
            )
        send(items, "addObject:", item, argtypes=(c_void_p,))
    if saved:
        send(board, "writeObjects:", items, restype=c_bool, argtypes=(c_void_p,))


app = QApplication([])
demo = Demo()
editor = demo.editor
boxes = {box.text(): box for box in demo.findChildren(QCheckBox)}
results: list[tuple[str, bool, str]] = []
CHECKS = []

SHIFTED = {"?": "/", ":": ";", "_": "-", "$": "4", "^": "6", "*": "8", "~": "`"}
NAMED = {
    "<Esc>": "Esc",
    "<CR>": "Return",
    "<Tab>": "Tab",
    "<BS>": "Delete",
    "<Left>": "Left",
}


def press(name: str, flags: int = 0) -> list[str]:
    if name == "Left":
        flags |= NUMERIC_PAD | SECONDARY_FN
    chars = post(KEYCODES[name], flags)
    QTest.qWait(40)
    return chars


def press_keys(keys: str) -> None:
    """Types keys: letters, digits, the symbols in SHIFTED, capitals, the keys in NAMED,
    and Ctrl with one key, such as <C-e>."""
    i = 0
    while i < len(keys):
        if keys.startswith("<C-", i) and keys[i + 4 : i + 5] == ">":
            ctrl(keys[i + 3])
            i += 5
            continue
        for token, name in NAMED.items():
            if keys.startswith(token, i):
                press(name)
                i += len(token)
                break
        else:
            char = keys[i]
            if char in SHIFTED:
                press(SHIFTED[char], SHIFT)
            elif char.isupper():
                press(char.lower(), SHIFT)
            else:
                press(char)
            i += 1


def ctrl(name: str) -> list[str]:
    return press(name, CONTROL)


def cmd(name: str) -> list[str]:
    return press(name, COMMAND)


def text() -> str:
    return editor.toPlainText()


def pos() -> tuple[int, int]:
    """The line and column. Qt counts columns in UTF-16 units."""
    cursor = editor.textCursor()
    return cursor.blockNumber(), cursor.positionInBlock()


def top() -> int:
    return editor.firstVisibleBlock().blockNumber()


def height() -> int:
    """The lines fully on the screen. Emoji and CJK make some lines taller."""
    offset, bottom, count = editor.contentOffset(), editor.viewport().height(), 0
    block = editor.firstVisibleBlock()
    while (
        block.isValid()
        and editor.blockBoundingGeometry(block).translated(offset).bottom() <= bottom + 0.5
    ):
        count += 1
        block = block.next()
    return count


def changed(line: int, col: int, new: str, length: int = 1) -> str:
    """The sample with `length` characters at line and col replaced by `new`."""
    lines = sample().split("\n")
    lines[line] = lines[line][:col] + new + lines[line][col + length :]
    return "\n".join(lines)


def try_keys(cases: list[tuple[str, str, tuple[int, int]]]) -> tuple[bool, str]:
    """Types each case's keys on a fresh sample. Checks the text, the cursor and that
    the editor is back in Normal mode with nothing pending."""
    ok, out, pending = True, [], []

    def note(keys_text: str) -> None:
        pending.append(keys_text)

    for keys, want_text, want_pos in cases:
        reset()
        pending.clear()
        demo.vim.pending_changed.connect(note)
        try:
            press_keys(keys)
        finally:
            demo.vim.pending_changed.disconnect(note)
        good_text = text() == want_text
        good_pos = pos() == want_pos
        normal = demo.vim.mode is Mode.NORMAL
        done = not pending or pending[-1] == ""
        good = good_text and good_pos and normal and done
        ok &= good
        line = editor.document().findBlockByNumber(pos()[0]).text()
        out.append(
            f"{keys} {'ok' if good else 'WRONG'}: text={good_text} at {pos()} "
            f"(want {want_pos}) line {line[:12]!r} normal={normal} done={done}"
        )
    return ok, "; ".join(out)


def first_non_blank(line: int) -> int:
    line_text = editor.document().findBlockByNumber(line).text()
    return len(line_text) - len(line_text.lstrip(" \t"))


def reset() -> None:
    """Starts each check from a fresh text in Normal mode at the top."""
    for _ in range(2):
        press("Esc")
    editor.setPlainText(sample())
    editor.moveCursor(QTextCursor.MoveOperation.Start)
    editor.setFocus()
    QTest.qWait(50)


def check(name: str):
    """Adds the function to CHECKS. It returns whether it passed and what it saw."""

    def add(fn):
        def run():
            reset()
            try:
                ok, detail = fn()
            except Exception:
                ok, detail = False, traceback.format_exc(limit=3)
            results.append((name, ok, detail))

        CHECKS.append(run)
        return fn

    return add


@check("x, u, Ctrl+R")
def check_undo_redo():
    t0 = text()
    press_keys("x")
    t1 = text()
    press_keys("u")
    t2 = text()
    chars = ctrl("r")
    t3 = text()
    ok = t1 == t0[1:] and t2 == t0 and t3 == t1
    return ok, (
        f"x deleted={t1 == t0[1:]} u restored={t2 == t0} Ctrl+R redid={t3 == t1} "
        f"(Ctrl+R chars {chars!r})"
    )


@check("Ctrl+E/Y, D/U, F/B")
def check_scrolling():
    press_keys("150G")
    out, ok = [], True
    for name, sign in (("e", 1), ("y", -1), ("d", 1), ("u", -1), ("f", 1), ("b", -1)):
        start = top()
        lines = height()
        size = {"e": 1, "y": 1, "d": lines // 2, "u": lines // 2}.get(name, lines - 2)
        ctrl(name)
        moved = top() - start
        line, col = pos()
        on_first = col == first_non_blank(line)
        good = moved == sign * size and (name not in "fb" or on_first)
        ok &= good
        note = f" first-non-blank={on_first}" if name in "fb" else ""
        out.append(f"C-{name} (h {lines}): top {moved:+d} (want {sign * size:+d}){note}")
    return ok, f"height {lines}; " + "; ".join(out)


def visual_scroll(start: str, want: Mode):
    press_keys("150G")
    press_keys(start)
    mode_ok = demo.vim.mode is want
    sizes = []
    for name in "eydufb":
        ctrl(name)
        cursor = editor.textCursor()
        sizes.append(abs(cursor.selectionEnd() - cursor.selectionStart()))
    still = demo.vim.mode is want
    ctrl("d")
    cursor = editor.textCursor()
    grown = cursor.hasSelection() and cursor.selectionEnd() - cursor.selectionStart() > 0
    chars = ctrl("[")
    back = demo.vim.mode is Mode.NORMAL
    ok = mode_ok and still and grown and back and max(sizes) > 0
    return ok, (
        f"{start} entered={mode_ok}, stayed through scrolls={still}, "
        f"selection sizes {sizes}, Ctrl+[ ({chars!r}) -> Normal={back}"
    )


@check("v + scrolling + Ctrl+[")
def check_visual_scroll():
    return visual_scroll("v", Mode.VISUAL)


@check("V + scrolling + Ctrl+[")
def check_visual_line_scroll():
    return visual_scroll("V", Mode.VISUAL_LINE)


@check("i, type, Ctrl+[ / Esc")
def check_leave_insert():
    out, ok = [], True
    for leave, how in ((lambda: ctrl("["), "Ctrl+["), (lambda: press("Esc"), "Esc")):
        t0 = text()
        press_keys("i")
        insert = demo.vim.mode is Mode.INSERT
        press_keys("hey")
        typed = text() == "hey" + t0
        leave()
        normal = demo.vim.mode is Mode.NORMAL
        ok &= insert and typed and normal
        out.append(f"{how}: insert={insert} typed={typed} normal={normal}")
        press_keys("u")
        editor.moveCursor(QTextCursor.MoveOperation.Start)
    return ok, "; ".join(out)


@check("Insert: Cmd+A, Cmd+C, Cmd+V, Cmd+Z")
def check_insert_cmd_keys():
    t0 = text()
    press_keys("i")
    cmd("a")
    cursor = editor.textCursor()
    utf16_length = len(t0.encode("utf-16-le")) // 2
    all_selected = cursor.selectionStart() == 0 and cursor.selectionEnd() == utf16_length
    cmd("c")
    copied = QGuiApplication.clipboard().text() == t0
    editor.moveCursor(QTextCursor.MoveOperation.End)
    cmd("v")
    pasted = text() == t0 + t0
    cmd("z")
    undone = text() == t0
    still = demo.vim.mode is Mode.INSERT
    ok = all_selected and copied and pasted and undone and still
    return ok, (
        f"Cmd+A all={all_selected} Cmd+C clipboard={copied} Cmd+V pasted={pasted} "
        f"Cmd+Z undid={undone} insert kept={still}"
    )


@check("Normal/Visual: Cmd+C copies, Cmd+V/X don't edit")
def check_normal_cmd_keys():
    QGuiApplication.clipboard().setText("CLIP")
    QTest.qWait(30)
    t0 = text()
    cmd("v")
    cmd("x")
    normal_ok = text() == t0
    press_keys("ve")
    visual = demo.vim.mode is Mode.VISUAL
    word = editor.textCursor().selectedText()
    cmd("c")
    copied = QGuiApplication.clipboard().text()
    cmd("v")
    cmd("x")
    visual_ok = text() == t0
    ok = normal_ok and visual and copied == word and visual_ok
    return ok, (
        f"Normal Cmd+V/X unchanged={normal_ok}; Visual sel {word!r}, "
        f"Cmd+C copied {copied!r}, Cmd+V/X unchanged={visual_ok}"
    )


@check("Cmd+R isn't redo, Ctrl+R is")
def check_cmd_r():
    t0 = text()
    press_keys("xu")
    cmd("r")
    no_redo = text() == t0
    ctrl("r")
    redo = text() == t0[1:]
    return no_redo and redo, f"Cmd+R left it undone={no_redo}, Ctrl+R redid={redo}"


def search_rent(search_key: str):
    press_keys("150G")
    start = pos()
    press_keys(search_key)
    opened = demo.find.isVisible() and demo.find.hasFocus()
    press_keys("rent<CR>")
    first = pos()
    found = editor.document().findBlockByNumber(first[0]).text()[first[1] : first[1] + 4]
    press_keys("n")
    second = pos()
    press_keys("N")
    third = pos()
    return start, opened, first, found, second, third


@check("/rent, n, N")
def check_search_forward():
    start, opened, a, found, b, c = search_rent("/")
    ok = opened and found == "rent" and a > start and b > a and c == a
    return ok, f"bar opened={opened}; from {start} Enter->{a} on {found!r}, n->{b}, N->{c}"


@check("?rent, n, N")
def check_search_backward():
    start, opened, a, found, b, c = search_rent("?")
    ok = opened and found == "rent" and a < start and b < a and c == a
    return ok, f"bar opened={opened}; from {start} Enter->{a} on {found!r}, n->{b}, N->{c}"


@check("/ then Esc closes the find bar")
def check_find_bar_esc():
    press_keys("/")
    opened = demo.find.isVisible()
    press("Esc")
    closed = not demo.find.isVisible()
    focus = editor.hasFocus()
    normal = demo.vim.mode is Mode.NORMAL
    ok = opened and closed and focus and normal
    return ok, f"opened={opened} closed={closed} editor focus={focus} normal={normal}"


@check("read-only: scroll, v, o, y, x, i")
def check_read_only():
    boxes["read-only"].click()
    QTest.qWait(30)
    try:
        t0 = text()
        press_keys("150G")
        start = top()
        ctrl("e")
        scrolled = top() == start + 1
        press_keys("wv")
        visual = demo.vim.mode is Mode.VISUAL
        press_keys("e")
        before = editor.textCursor().position()
        selected = editor.textCursor().selectedText()
        press_keys("o")
        swapped = editor.textCursor().position() != before
        press_keys("y")
        yanked = demo.vim.mode is Mode.NORMAL
        press_keys("x")
        x_kept = text() == t0
        press_keys("i")
        no_insert = demo.vim.mode is Mode.NORMAL
        still = text() == t0
    finally:
        boxes["read-only"].click()
        QTest.qWait(30)
    # with editing back on, P pastes what y saved
    press_keys("P")
    pasted = text() != t0 and len(text()) == len(t0) + len(selected)
    ok = scrolled and visual and swapped and yanked and x_kept and no_insert and still and pasted
    return ok, (
        f"Ctrl+E scrolled={scrolled} v={visual} o swapped={swapped} y->Normal={yanked} "
        f"x kept text={x_kept} i stayed Normal={no_insert} typing kept text={still} "
        f"yank of {selected!r} pastes after={pasted}"
    )


@check("r, 3r, Visual r, r Esc")
def check_replace():
    return try_keys(
        [
            ("rx", changed(0, 0, "x"), (0, 0)),
            ("3rx", changed(0, 0, "xxx", 3), (0, 2)),
            ("vllrx", changed(0, 0, "xxx", 3), (0, 0)),
            ("r<Esc>l", sample(), (0, 1)),
        ]
    )


@check("r then Enter, Ctrl+E, Ctrl+Y")
def check_replace_from_lines():
    return try_keys(
        [
            ("r<CR>", changed(0, 0, "\n"), (1, 0)),
            ("r<C-e>", changed(0, 0, "T"), (0, 0)),
            ("jr<C-y>", changed(1, 0, "s"), (1, 0)),
        ]
    )


@check("r then Ctrl+V and a code, Ctrl+K and a digraph")
def check_replace_codes():
    return try_keys(
        [
            ("r<C-v>065", changed(0, 0, "A"), (0, 0)),
            ("r<C-v>u20ac", changed(0, 0, "\u20ac"), (0, 0)),
            ("r<C-v>q", changed(0, 0, "q"), (0, 0)),
            ("r<C-k>e:", changed(0, 0, "\u00eb"), (0, 0)),
            ("2r<C-k>a*", changed(0, 0, "\u03b1\u03b1", 2), (0, 1)),
        ]
    )


@check("~, 3~, Visual ~")
def check_switch_case():
    return try_keys(
        [
            ("~", changed(0, 0, "S"), (0, 1)),
            ("3~", changed(0, 0, "SID", 3), (0, 3)),
            ("ve~", changed(0, 0, "SIDE", 4), (0, 0)),
        ]
    )


@check("Ctrl+W h, Ctrl+W Ctrl+H, Ctrl+W Left")
def check_window_keys():
    calls, pending = [], []

    def note(keys_text: str) -> None:
        pending.append(keys_text)

    demo.vim.window_hook = calls.append
    demo.vim.pending_changed.connect(note)
    try:
        press_keys("<C-w>h<C-w><C-h><C-w><Left><C-w>l")
    finally:
        demo.vim.window_hook = None
        demo.vim.pending_changed.disconnect(note)
    kept = text() == sample() and pos() == (0, 0)
    ok = calls == ["h", "h", "h", "l"] and pending == ["^W", ""] * 4 and kept
    return ok, f"hook got {calls}, pending {pending}, text and cursor kept={kept}"


@check("Ctrl+W Ctrl+L wins over an app's Ctrl+L")
def check_window_key_over_shortcut():
    calls, fired = [], []
    shortcut = QShortcut(QKeySequence(QKeyCombination(control_modifier(), Qt.Key.Key_L)), demo)
    shortcut.activated.connect(lambda: fired.append("Ctrl+L"))
    demo.vim.window_hook = calls.append
    try:
        press_keys("<C-w><C-l>")
        after_w = (list(calls), list(fired))
        chars = ctrl("l")
    finally:
        demo.vim.window_hook = None
        shortcut.setEnabled(False)
        shortcut.deleteLater()
    ok = after_w == (["l"], []) and fired == ["Ctrl+L"]
    return ok, (
        f"after Ctrl+W Ctrl+L: hook {after_w[0]}, shortcut {after_w[1]}; "
        f"Ctrl+L alone ({chars!r}) fired the shortcut={fired == ['Ctrl+L']}"
    )


@check("z=, ]s, [s, zg, zG")
def check_spelling_keys():
    calls = []
    demo.vim.spell_hook = lambda name, count: calls.append((name, count))
    try:
        press_keys("z=2]s[szgzG")
    finally:
        demo.vim.spell_hook = None
    want = [("z=", None), ("]s", 2), ("[s", None), ("zg", None), ("zG", None)]
    kept = text() == sample() and pos() == (0, 0)
    return calls == want and kept, f"hook got {calls}, text and cursor kept={kept}"


@contextmanager
def ukrainian_layout():
    """Switches to the Ukrainian-PC layout and back. Yields its ID, or None without it."""
    old = current_source()
    ukrainian = find_source("com.apple.keylayout.Ukrainian-PC")
    if not ukrainian:
        yield None
        return
    carbon.TISSelectInputSource(ukrainian)
    QTest.qWait(300)
    try:
        yield source_id(current_source())
    finally:
        carbon.TISSelectInputSource(old)
        QTest.qWait(300)


@check("Ukrainian: ц, ш, Esc, г, Ctrl+к")
def check_ukrainian():
    with ukrainian_layout() as layout:
        if layout is None:
            return False, "Ukrainian-PC input source not found"
        t0 = text()
        p0 = pos()
        chars_w = press("w")  # ц
        moved = pos()
        moved_ok = moved == (0, 4)  # w from the start of "side-vim" goes to "-"
        chars_i = press("i")  # ш
        insert = demo.vim.mode is Mode.INSERT
        typed = [press("j")[0], press("q")[0]]  # о, й
        typed_ok = text().startswith(t0[:4] + "ой")
        press("Esc")
        normal = demo.vim.mode is Mode.NORMAL
        chars_u = press("u")  # г
        undone = text() == t0
        chars_r = ctrl("r")  # Ctrl+к
        redone = text() != t0 and "ой" in text()
    back = source_id(current_source())
    ok = moved_ok and insert and typed_ok and normal and undone and redone
    return ok, (
        f"layout {layout} (restored to {back}); ц {chars_w!r} {p0}->{moved}; "
        f"ш {chars_i!r} insert={insert}; typed {typed} in text={typed_ok}; "
        f"Esc normal={normal}; г {chars_u!r} undid={undone}; Ctrl+к {chars_r!r} redid={redone}"
    )


@check("Ukrainian: к then ц puts in ц")
def check_ukrainian_replace():
    with ukrainian_layout() as layout:
        if layout is None:
            return False, "Ukrainian-PC input source not found"
        chars = press("r") + press("w")  # к, ц
        replaced = text() == changed(0, 0, "ц") and pos() == (0, 0)
    return replaced, f"layout {layout}; typed {chars}, put in ц={replaced}"


@check("vim checkbox off/on")
def check_vim_checkbox():
    t0 = text()
    boxes["vim"].click()
    QTest.qWait(30)
    off = not demo.vim.enabled
    press_keys("zq")
    typed = text() == "zq" + t0
    boxes["vim"].click()
    QTest.qWait(30)
    on = demo.vim.enabled and demo.vim.mode is Mode.NORMAL
    before = text()
    press_keys("x")
    col = pos()[1]
    x_works = text() == before[:col] + before[col + 1 :] and text() != before
    ok = off and typed and on and x_works
    return ok, f"disabled={off} plain typing={typed} enabled Normal={on} x works again={x_works}"


@check("focus: another widget drops r, another app keeps it")
def check_focus():
    # the find bar takes the focus as a click on it would, then gives it back
    press_keys("r")
    demo.find.show()
    demo.find.setFocus(Qt.FocusReason.MouseFocusReason)
    QTest.qWait(50)
    demo.find.hide()
    editor.setFocus()
    QTest.qWait(50)
    press_keys("l")
    dropped = text() == sample() and pos() == (0, 1)
    # another app comes to the front, then this one again
    press_keys("0r")
    send(nsapp(), "deactivate")
    QTest.qWait(500)
    inactive = app.activeWindow() is None
    activate()
    back = QTest.qWaitForWindowActive(demo, 3000)
    QTest.qWait(100)
    press_keys("l")
    kept = text() == changed(0, 0, "l") and pos() == (0, 0)
    # macOS may not let the app bring itself back to the front, so that's only shown
    ok = dropped and inactive and kept
    return ok, (
        f"find bar dropped r={dropped}; app went inactive={inactive}, r kept={kept} "
        f"(came back to the front={back})"
    )


def run_checks() -> bool:
    """Runs every check and prints the results. True if they all passed."""
    saved = save_pasteboard()
    try:
        demo.show()
        demo.raise_()
        demo.activateWindow()
        activate()
        editor.setFocus()
        QTest.qWait(600)
        print(
            f"macOS layout {source_id(current_source())}, PySide6 {pyside_version}, "
            f"Python {sys.version.split()[0]}, window active={app.activeWindow() is demo}"
        )
        for run in CHECKS:
            run()
    finally:
        restore_pasteboard(saved)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}\n      {detail}")
    passed = sum(ok for _, ok, _ in results)
    print(f"{passed}/{len(results)} passed")
    return passed == len(results)


def main() -> None:
    all_passed = False
    try:
        all_passed = run_checks()
    finally:
        # Quit even when something outside the checks fails, so make doesn't wait forever.
        app.exit(0 if all_passed else 1)


QTimer.singleShot(0, main)
sys.exit(app.exec())
