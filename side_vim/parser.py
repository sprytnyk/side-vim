"""Turn vim key tokens into commands. No Qt here.

Keys come in one token at a time: a single character ("w", "3", "G"), or a name in
angle brackets ("<C-r>", "<Left>"). Esc reaches the parser only while r waits for its
character (wants_text); otherwise the editor side handles it.
"""

from dataclasses import dataclass

from side_vim._digraphs import DIGRAPHS
from side_vim.motions import MOTIONS
from side_vim.notation import is_named
from side_vim.scroll import SCROLL_KEYS

# Keys that are other names for a motion.
ALIASES = {
    "<Left>": "h",
    "<Right>": "l",
    "<Up>": "k",
    "<Down>": "j",
    "<Home>": "0",
    "<End>": "$",
}

# The commands, other than motions, each with True if it changes the text. A read-only
# editor skips those. Every other list of keys is made from these tables.

# Operators take a motion in Normal mode (`dw`) and act on the selection in Visual mode.
OPERATORS = {"d": True, "c": True, "y": False}

# Keys vim treats as an operator with a fixed motion.
SHORTHANDS = {"x": ("d", "l"), "D": ("d", "$"), "C": ("c", "$")}

COMMON_ACTIONS = {
    "n": False,
    "N": False,
    "/": False,
    "?": False,
} | dict.fromkeys(SCROLL_KEYS, False)

# vim's window command: Ctrl+W and one more key. VimMode passes that key to window_hook.
WINDOW = "<C-w>"

# vim's r: replace characters with the one typed next. That character is text, not a
# key: layout_map leaves it as typed, and Esc or a Ctrl key can be part of it.
REPLACE = "r"

# What r puts in, other than a character: a line break (r Enter, in Normal mode), and
# the character at the same screen column on the line below (r Ctrl+E) or above.
LINE_BREAK = "\n"
BELOW = "<C-e>"
ABOVE = "<C-y>"

# vim's spelling commands. VimMode passes them to spell_hook, since the app has the
# dictionary. z= changes the text: it replaces the word.
SPELL = {"z=": True, "]s": False, "[s": False, "zg": False, "zG": False}

# Commands that take a count but no motion, in Normal mode.
NORMAL_ACTIONS = {
    "p": True,
    "P": True,
    "J": True,
    "u": True,
    "<C-r>": True,
    "i": True,
    "a": True,
    "I": True,
    "A": True,
    "o": True,
    "O": True,
    "v": False,
    "V": False,
    REPLACE: True,
    "~": True,
    WINDOW: False,
    **SPELL,
} | COMMON_ACTIONS

# Commands that act on the selection or the mode, in Visual mode. `x` is `d` here.
VISUAL_ACTIONS = (
    OPERATORS
    | {"p": True, "o": False, "v": False, "V": False, REPLACE: True, "~": True}
    | COMMON_ACTIONS
)

# The Normal mode commands that start Insert mode.
INSERT_COMMANDS = frozenset({"i", "a", "I", "A", "o", "O"})

# The Ctrl keys vim takes in Normal and Visual mode. Other Ctrl keys go to the app.
CTRL_KEYS = frozenset(key for key in NORMAL_ACTIONS | VISUAL_ACTIONS if key.startswith("<C-"))

# The motion name for `dd`, `cc` and `yy`: the current line and count-1 lines below.
LINE = "line"


@dataclass(frozen=True)
class Command:
    """One complete command.

    name: "move" for a plain motion, an operator ("d", "c", "y"), or one of the
    actions above ("p", "<C-r>", "i", ...).
    count: the count typed, or None if there was none. For an operator, the two
    counts are multiplied (`2d3w` is `d` with 6).
    motion: for "move" and for operators in Normal mode, the motion ("w", "gg", or
    LINE for `dd`). None for actions and for operators in Visual mode.
    key: for WINDOW, the key after Ctrl+W. Ctrl and the arrows read as the letter,
    as in vim: Ctrl+W Ctrl+H and Ctrl+W Left are both "h". For REPLACE, what goes in:
    a character (any, even "\x1b" or "\r"), or LINE_BREAK, BELOW or ABOVE.
    """

    name: str
    count: int | None = None
    motion: str | None = None
    key: str | None = None


def changes_text(command: Command, visual: bool) -> bool:
    """True if the command changes the text, in Visual mode or in Normal mode."""
    if command.name == "move":
        return False
    if command.name in OPERATORS:
        return OPERATORS[command.name]
    return (VISUAL_ACTIONS if visual else NORMAL_ACTIONS)[command.name]


class _Pending:
    pass


PENDING = _Pending()


class Parser:
    """Collects keys until they make a command."""

    def __init__(self) -> None:
        self._keys: list[str] = []

    @property
    def pending(self) -> str:
        """The keys typed so far for the next command, like vim's showcmd: "2d", "^W"."""
        return "".join(_shown(key) for key in self._keys)

    @property
    def wants_any_key(self) -> bool:
        """True right after Ctrl+W, and while r waits for its character. The next key is
        then vim's, even a Ctrl key that is an app shortcut."""
        return (bool(self._keys) and self._keys[-1] == WINDOW) or self.wants_text

    @property
    def wants_text(self) -> bool:
        """True while r waits for its character. Characters then go in as typed, not
        through a layout map, and Esc comes here: it cancels r, or after Ctrl+V it's the
        character."""
        _, i = _read_count(self._keys, 0)
        return i < len(self._keys) and self._keys[i] == REPLACE

    def reset(self) -> None:
        self._keys.clear()

    def feed(self, key: str, visual: bool = False) -> Command | None:
        """Add a key. Returns the command once it's complete, otherwise None. Keys that
        can't make a command are dropped, and pending becomes empty."""
        self._keys.append(key)
        result = _parse(self._keys, visual)
        if isinstance(result, _Pending):
            return None
        self._keys.clear()
        return result


def _ctrl_letter(key: str) -> str | None:
    """The character of a plain Ctrl key: "w" for <C-w>. None for other keys."""
    return key[3] if key.startswith("<C-") and len(key) == 5 else None


NUL = "\x00"
ESCAPE = "\x1b"
CTRL_C = "\x03"
CTRL_K = "\x0b"
CTRL_V = "\x16"

# The character vim reads for these keys in r's character, like a terminal sends them.
TYPED = {"<Tab>": "\t", "<CR>": "\r", "<Esc>": ESCAPE}

# The Ctrl keys that type a control character: Ctrl+@ is 0, Ctrl+A is 1, Ctrl+_ is 31.
CONTROL_LETTERS = "@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_"

# Ctrl+V and a character code: the code's base, and how many digits complete it. With
# no prefix the code is decimal, as in Ctrl+V 065. Only u and U go past 255.
CODES = {
    "": (10, 3),
    "o": (8, 3),
    "O": (8, 3),
    "x": (16, 2),
    "X": (16, 2),
    "u": (16, 4),
    "U": (16, 8),
}


def _typed(key: str) -> str | None:
    """The character a key types, as r reads it: itself, "\t" for Tab, "\r" for Enter,
    "\x16" for Ctrl+V. None for keys that type nothing, such as the arrows, BS, or a key
    with Shift or Alt and a name."""
    if not is_named(key):
        return key
    if key in TYPED:
        return TYPED[key]
    letter = _ctrl_letter(key)
    if letter is not None and letter.upper() in CONTROL_LETTERS:
        return chr(ord(letter.upper()) - 0x40)
    return None


def _literal(char: str) -> str:
    """A character put in as it is. A line feed in vim's text is a NUL, so Ctrl+V
    Ctrl+J puts in a NUL."""
    return NUL if char == "\n" else char


def _is_digit(key: str, base: int) -> bool:
    return len(key) == 1 and key.lower() in "0123456789abcdef"[:base]


def _exact_digraph(first: str, second: str) -> str:
    """vim's getexactdigraph: the digraph's character. If there's none, the second
    character, or after a space, the second one with its high bit set."""
    if first + second in DIGRAPHS:
        return DIGRAPHS[first + second]
    if first == " " and len(second) == 1:
        return chr(ord(second) | 0x80)
    return second


def _digraph(first: str, second: str) -> str:
    """vim's getdigraph: the character for Ctrl+K first second, in either order."""
    char = _exact_digraph(first, second)
    if char != second or first == second:
        return char
    char = _exact_digraph(second, first)
    return second if char == first else char


def _read_char(keys: list[str], i: int, visual: bool) -> str | _Pending | None:
    """Read r's character from keys[i:], which must end there. None if r is cancelled:
    by Esc, by a key that types nothing (an arrow, BS), or in Normal mode by Ctrl+C."""
    if i == len(keys):
        return PENDING
    char = _typed(keys[i])
    if char == CTRL_K:
        return _read_digraph(keys, i + 1, visual)
    if char is None or char == NUL or (char == CTRL_C and not visual):
        return None
    return _resolve(char, keys, i + 1, visual)


def _resolve(char: str, keys: list[str], i: int, visual: bool) -> str | _Pending | None:
    """What r does with a character, typed or made by a digraph. Ctrl+V reads one more,
    and Esc cancels. In Normal mode Enter and Ctrl+J make a line break, and Ctrl+E and
    Ctrl+Y copy from the next line. In Visual mode every character goes in as it is:
    vim's Visual r Enter puts in "\r"."""
    if char == CTRL_V:
        return _read_literal(keys, i)
    if i != len(keys) or char == ESCAPE:
        return None
    if visual:
        return _literal(char)
    if char in ("\r", "\n"):
        return LINE_BREAK
    return {"\x05": BELOW, "\x19": ABOVE}.get(char, char)


def _read_literal(keys: list[str], i: int) -> str | _Pending | None:
    """After Ctrl+V: the next key as it is, or a character code like 065, x41 or u20ac.
    A code ends with its last digit, or with a key that isn't one, which is used up. A
    prefix with no digits (Ctrl+V u q) puts in that key. A key that types nothing
    cancels r."""
    if i == len(keys):
        return PENDING
    prefix = "" if _is_digit(keys[i], 10) else keys[i]
    if prefix not in CODES:
        char = _typed(keys[i])
        return _literal(char) if char is not None and i + 1 == len(keys) else None
    base, size = CODES[prefix]
    j = i + len(prefix)
    while j < len(keys) and j - i - len(prefix) < size and _is_digit(keys[j], base):
        j += 1
    code = "".join(keys[i + len(prefix) : j])
    if len(code) < size:
        if j == len(keys):
            return PENDING
        if not code:
            char = _typed(keys[j])
            return _literal(char) if char is not None and j + 1 == len(keys) else None
        j += 1  # the key that ended the code
    if j != len(keys):
        return None
    number = int(code, base)
    if prefix not in ("u", "U"):
        number = min(number, 0xFF)
    if 0xD800 <= number <= 0xDFFF or number > 0x10FFFF:
        return None  # not a character
    return _literal(chr(number))


def _read_digraph(keys: list[str], i: int, visual: bool) -> str | _Pending | None:
    """After Ctrl+K: two characters make one, like e : for ë. Ctrl+C cancels r. Esc or
    a key that types nothing puts in the Ctrl+K itself, as vim does."""
    chars: list[str] = []
    for j in (i, i + 1):
        if j == len(keys):
            return PENDING
        char = _typed(keys[j])
        if char == CTRL_C:
            return None
        if char is None or char in (NUL, ESCAPE):
            return CTRL_K if j + 1 == len(keys) else None
        chars.append(char)
    char = _digraph(*chars)
    if char == NUL:  # Ctrl+@ after a character with no digraph
        return CTRL_K if i + 2 == len(keys) else None
    return _resolve(char, keys, i + 2, visual)


def _shown(key: str) -> str:
    """A key as showcmd writes it: Ctrl+W is ^W."""
    letter = _ctrl_letter(key)
    return "^" + letter.upper() if letter else key


def _window_key(key: str) -> str:
    """The key after Ctrl+W, with <C-h> and <Left> read as h."""
    key = ALIASES.get(key, key)
    return _ctrl_letter(key) or key


def _read_count(keys: list[str], i: int) -> tuple[int | None, int]:
    """Read a count starting at keys[i]. A count can't start with 0, since 0 is a
    motion."""
    if i >= len(keys) or keys[i] not in "123456789" or len(keys[i]) != 1:
        return None, i
    digits = ""
    while i < len(keys) and len(keys[i]) == 1 and keys[i] in "0123456789":
        digits += keys[i]
        i += 1
    return int(digits), i


def _read_motion(keys: list[str], i: int) -> str | _Pending | None:
    """Read a motion that must end the keys. None if keys[i:] isn't one."""
    if i == len(keys):
        return PENDING
    key = ALIASES.get(keys[i], keys[i])
    if key == "g":
        if i + 1 == len(keys):
            return PENDING
        return "gg" if keys[i + 1] == "g" and i + 2 == len(keys) else None
    if key in MOTIONS and i + 1 == len(keys):
        return key
    return None


def _parse(keys: list[str], visual: bool) -> Command | _Pending | None:
    count, i = _read_count(keys, 0)
    if i == len(keys):
        return PENDING
    key = keys[i]

    motion = _read_motion(keys, i)
    if motion is not None:
        return motion if isinstance(motion, _Pending) else Command("move", count, motion)

    if key == REPLACE:
        char = _read_char(keys, i + 1, visual)
        return Command(REPLACE, count, key=char) if isinstance(char, str) else char

    if visual:
        key = "d" if key == "x" else key
        if key in VISUAL_ACTIONS and i + 1 == len(keys):
            return Command(key, count)
        return None

    if key == WINDOW:
        if i + 1 == len(keys):
            return PENDING
        return Command(WINDOW, count, key=_window_key(keys[i + 1]))

    if key in SHORTHANDS and i + 1 == len(keys):
        op, fixed = SHORTHANDS[key]
        return Command(op, count, fixed)

    if key in OPERATORS:
        count2, j = _read_count(keys, i + 1)
        total = None if count is None and count2 is None else (count or 1) * (count2 or 1)
        if j < len(keys) and keys[j] == key and j + 1 == len(keys):
            return Command(key, total, LINE)
        motion = _read_motion(keys, j)
        if motion is None or isinstance(motion, _Pending):
            return motion
        return Command(key, total, motion)

    if key in NORMAL_ACTIONS and i + 1 == len(keys):
        return Command(key, count)
    name = "".join(keys[i:])
    if name in SPELL:
        return Command(name, count)
    if i + 1 == len(keys) and any(spell.startswith(key) for spell in SPELL):
        return PENDING  # z, ] or [ waits for one more key
    return None
