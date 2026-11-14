"""Turn vim key tokens into commands. No Qt here.

Keys come in one token at a time: a single character ("w", "3", "G"), or a name in
angle brackets ("<C-r>", "<Left>"). Esc never reaches the parser; the editor side
handles it.
"""

from dataclasses import dataclass

from side_vim.motions import MOTIONS

# Keys that are other names for a motion.
ALIASES = {
    "<Left>": "h",
    "<Right>": "l",
    "<Up>": "k",
    "<Down>": "j",
    "<Home>": "0",
    "<End>": "$",
}

OPERATORS = frozenset({"d", "c", "y"})

# Keys vim treats as an operator with a fixed motion.
SHORTHANDS = {"x": ("d", "l"), "D": ("d", "$"), "C": ("c", "$")}

# Commands that take a count but no motion, in Normal mode.
NORMAL_ACTIONS = frozenset(
    {"p", "P", "J", "u", "<C-r>", "i", "a", "I", "A", "o", "O", "v", "V", "n", "N", "/", "?"}
)

# Commands that act on the selection or the mode, in Visual mode.
VISUAL_ACTIONS = frozenset({"d", "c", "y", "p", "o", "v", "V", "n", "N", "/", "?"})

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
    """

    name: str
    count: int | None = None
    motion: str | None = None


class _Pending:
    pass


_PENDING = _Pending()


class Parser:
    """Collects keys until they make a command."""

    def __init__(self) -> None:
        self._keys: list[str] = []

    @property
    def pending(self) -> str:
        """The keys typed so far for the next command, like vim's showcmd."""
        return "".join(self._keys)

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
        return _PENDING
    key = ALIASES.get(keys[i], keys[i])
    if key == "g":
        if i + 1 == len(keys):
            return _PENDING
        return "gg" if keys[i + 1] == "g" and i + 2 == len(keys) else None
    if key in MOTIONS and i + 1 == len(keys):
        return key
    return None


def _parse(keys: list[str], visual: bool) -> Command | _Pending | None:
    count, i = _read_count(keys, 0)
    if i == len(keys):
        return _PENDING
    key = keys[i]

    motion = _read_motion(keys, i)
    if motion is not None:
        return motion if isinstance(motion, _Pending) else Command("move", count, motion)

    if visual:
        key = "d" if key == "x" else key
        if key in VISUAL_ACTIONS and i + 1 == len(keys):
            return Command(key, count)
        return None

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
    return None
