import pytest

from side_vim.notation import tokens
from side_vim.parser import (
    ABOVE,
    BELOW,
    CTRL_KEYS,
    LINE,
    LINE_BREAK,
    NORMAL_ACTIONS,
    REPLACE,
    SPELL,
    VISUAL_ACTIONS,
    WINDOW,
    Command,
    Parser,
    changes_text,
)


def feed(keys: list[str] | str, visual: bool = False) -> tuple[list[Command | None], str]:
    """Feed keys one by one; return what each key gave, and what's left pending."""
    parser = Parser()
    results = [parser.feed(key, visual) for key in keys]
    return results, parser.pending


def last(keys: list[str] | str, visual: bool = False) -> Command | None:
    results, _ = feed(keys, visual)
    return results[-1]


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("w", Command("move", None, "w")),
        ("3w", Command("move", 3, "w")),
        ("12j", Command("move", 12, "j")),
        ("0", Command("move", None, "0")),
        ("10l", Command("move", 10, "l")),
        ("gg", Command("move", None, "gg")),
        ("5gg", Command("move", 5, "gg")),
        ("G", Command("move", None, "G")),
        ("5G", Command("move", 5, "G")),
        ("$", Command("move", None, "$")),
        ("^", Command("move", None, "^")),
        ("dw", Command("d", None, "w")),
        ("cw", Command("c", None, "w")),
        ("y$", Command("y", None, "$")),
        ("d0", Command("d", None, "0")),
        ("dG", Command("d", None, "G")),
        ("dgg", Command("d", None, "gg")),
        ("2dw", Command("d", 2, "w")),
        ("d3w", Command("d", 3, "w")),
        ("2d3w", Command("d", 6, "w")),
        ("y3j", Command("y", 3, "j")),
        ("d10w", Command("d", 10, "w")),
        ("dd", Command("d", None, LINE)),
        ("3dd", Command("d", 3, LINE)),
        ("d3d", Command("d", 3, LINE)),
        ("yy", Command("y", None, LINE)),
        ("cc", Command("c", None, LINE)),
        ("x", Command("d", None, "l")),
        ("4x", Command("d", 4, "l")),
        ("D", Command("d", None, "$")),
        ("2C", Command("c", 2, "$")),
        ("p", Command("p")),
        ("3P", Command("P", 3)),
        ("J", Command("J")),
        ("3J", Command("J", 3)),
        ("u", Command("u")),
        ("2u", Command("u", 2)),
        ("i", Command("i")),
        ("3i", Command("i", 3)),
        ("2o", Command("o", 2)),
        ("A", Command("A")),
        ("v", Command("v")),
        ("V", Command("V")),
        ("n", Command("n")),
        ("3N", Command("N", 3)),
        ("/", Command("/")),
        ("?", Command("?")),
    ],
)
def test_normal_commands(keys: str, expected: Command) -> None:
    results, pending = feed(keys)
    assert results[-1] == expected
    assert all(r is None for r in results[:-1])
    assert pending == ""


def test_ctrl_r_and_arrow_keys() -> None:
    assert last(["<C-r>"]) == Command("<C-r>")
    assert last(["2", "<C-r>"]) == Command("<C-r>", 2)
    assert last(["<Left>"]) == Command("move", None, "h")
    assert last(["3", "<Down>"]) == Command("move", 3, "j")
    assert last(["d", "<End>"]) == Command("d", None, "$")
    assert last(["<Home>"]) == Command("move", None, "0")


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (["<C-w>", "h"], "h"),
        (["<C-w>", "<C-h>"], "h"),  # Ctrl held down, as in vim
        (["<C-w>", "<Left>"], "h"),
        (["<C-w>", "<Right>"], "l"),
        (["<C-w>", "W"], "W"),
        (["<C-w>", "<C-w>"], "w"),
    ],
)
def test_ctrl_w_takes_one_more_key(keys: list[str], expected: str) -> None:
    results, pending = feed(keys)
    assert results == [None, Command(WINDOW, None, key=expected)]
    assert pending == ""


def test_ctrl_w_shows_as_in_vim_and_takes_any_key() -> None:
    parser = Parser()
    parser.feed("2")
    assert not parser.wants_any_key
    parser.feed(WINDOW)
    assert parser.pending == "2^W"
    assert parser.wants_any_key
    assert parser.feed("l") == Command(WINDOW, 2, key="l")
    assert not parser.wants_any_key


def test_ctrl_w_is_dropped_in_visual_mode() -> None:
    assert feed(["<C-w>"], visual=True) == ([None], "")


@pytest.mark.parametrize("name", list(SPELL))
def test_spelling_commands_take_two_keys(name: str) -> None:
    first, second = name
    assert feed(["3", first, second]) == ([None, None, Command(name, 3)], "")


def test_spelling_commands_wait_for_their_second_key() -> None:
    parser = Parser()
    parser.feed("2")
    parser.feed("z")
    assert parser.pending == "2z"
    assert parser.feed("x") is None  # side-vim has no zx: dropped
    assert parser.pending == ""


def test_spelling_commands_are_dropped_in_visual_mode() -> None:
    assert feed(["z", "="], visual=True) == ([None, None], "")


@pytest.mark.parametrize(
    ("keys", "pending"),
    [("2", "2"), ("2d", "2d"), ("d3", "d3"), ("g", "g"), ("dg", "dg"), ("12", "12")],
)
def test_pending_keys(keys: str, pending: str) -> None:
    results, left = feed(keys)
    assert all(r is None for r in results)
    assert left == pending


@pytest.mark.parametrize("keys", ["q", "dx", "dp", "gx", "dgx", "2q", "dc", "zx"])
def test_bad_keys_are_dropped(keys: str) -> None:
    results, pending = feed(keys)
    assert all(r is None for r in results)
    assert pending == ""


def test_parser_starts_over_after_a_bad_key() -> None:
    parser = Parser()
    assert parser.feed("d") is None
    assert parser.feed("q") is None
    assert parser.feed("w") == Command("move", None, "w")


def test_reset_drops_pending_keys() -> None:
    parser = Parser()
    parser.feed("2")
    parser.feed("d")
    parser.reset()
    assert parser.pending == ""
    assert parser.feed("w") == Command("move", None, "w")


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("w", Command("move", None, "w")),
        ("3j", Command("move", 3, "j")),
        ("gg", Command("move", None, "gg")),
        ("d", Command("d")),
        ("x", Command("d")),
        ("c", Command("c")),
        ("y", Command("y")),
        ("p", Command("p")),
        ("o", Command("o")),
        ("v", Command("v")),
        ("V", Command("V")),
        ("n", Command("n")),
    ],
)
def test_visual_commands(keys: str, expected: Command) -> None:
    assert last(keys, visual=True) == expected


@pytest.mark.parametrize("keys", ["u", "J", "i", "a", "D", "P", "<C-r>"])
def test_visual_leaves_out_other_keys(keys: str) -> None:
    results, pending = feed([keys], visual=True)
    assert results == [None]
    assert pending == ""


@pytest.mark.parametrize("key", ["<C-e>", "<C-y>", "<C-d>", "<C-u>", "<C-f>", "<C-b>"])
def test_scrolling_keys(key: str) -> None:
    assert last([key]) == Command(key)
    assert last(["1", "2", key]) == Command(key, 12)
    assert last(["3", key], visual=True) == Command(key, 3)
    assert last(["d", key]) is None


def test_ctrl_keys() -> None:
    assert {"<C-r>", "<C-e>", "<C-y>", "<C-d>", "<C-u>", "<C-f>", "<C-b>", "<C-w>"} == CTRL_KEYS


@pytest.mark.parametrize(
    ("command", "visual", "changes"),
    [
        (Command("move", None, "w"), False, False),
        (Command("move", None, "w"), True, False),
        (Command("d", None, "w"), False, True),
        (Command("c", None, "w"), False, True),
        (Command("y", None, "w"), False, False),
        (Command("d"), True, True),
        (Command("y"), True, False),
        (Command("o"), False, True),  # opens a line
        (Command("o"), True, False),  # goes to the other end
        (Command("p"), True, True),
        (Command("u"), False, True),
        (Command("<C-r>"), False, True),
        (Command("v"), False, False),
        (Command("n"), True, False),
        (Command("<C-d>"), False, False),
        (Command("/"), True, False),
        (Command(WINDOW, key="h"), False, False),
        (Command("z="), False, True),  # replaces the word
        (Command("]s"), False, False),
        (Command("zg"), False, False),
        (Command("~"), False, True),
        (Command("~"), True, True),
    ],
)
def test_changes_text(command: Command, visual: bool, changes: bool) -> None:
    assert changes_text(command, visual) is changes


def test_every_key_in_the_tables_makes_its_command() -> None:
    for key in NORMAL_ACTIONS:
        parser = Parser()
        if key == WINDOW:  # waits for one more key
            assert parser.feed(key) is None
            assert parser.feed("h") == Command(key, key="h")
        elif key in SPELL:  # two keys
            assert parser.feed(key[0]) is None
            assert parser.feed(key[1]) == Command(key)
        elif key == REPLACE:  # waits for its character
            assert parser.feed(key) is None
            assert parser.feed("x") == Command(key, key="x")
        else:
            assert parser.feed(key) == Command(key)
    for key in VISUAL_ACTIONS:
        parser = Parser()
        if key == REPLACE:
            assert parser.feed(key, visual=True) is None
            assert parser.feed("x", visual=True) == Command(key, key="x")
        else:
            assert parser.feed(key, visual=True) == Command(key)


def replace(keys: str, visual: bool = False) -> tuple[str | None, int | None]:
    """What r and the keys after it give: the character and count, or None if r was
    cancelled. Every key but the last must wait for more."""
    parser = Parser()
    *first, last = tokens(keys)
    for key in first:
        assert parser.feed(key, visual) is None, key
    command = parser.feed(last, visual)
    assert parser.pending == ""
    if command is None:
        return None, None
    assert command.name == REPLACE
    return command.key, command.count


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("rx", "x"),
        ("r<", "<"),
        ("rц", "ц"),
        ("r🇺🇦", "🇺🇦"),
        ("r<CR>", LINE_BREAK),
        ("r<C-j>", LINE_BREAK),
        ("r<C-m>", LINE_BREAK),
        ("r<Tab>", "\t"),
        ("r<C-e>", BELOW),
        ("r<C-y>", ABOVE),
        ("r<C-a>", "\x01"),
        ("r<C-\\>", "\x1c"),
        ("r<C-]>", "\x1d"),
        ("r<C-v><CR>", "\r"),  # VimMode can't put it in
        ("r<C-v><C-j>", "\x00"),  # vim keeps NUL as a line feed
        ("r<C-v><C-e>", "\x05"),
        ("r<C-v>000", "\x00"),
        ("r<C-v>010", "\x00"),
        ("r<C-v>013", "\r"),
        ("r<C-v>0x", "\x00"),
        ("r<C-v>ud800q", None),  # half of a surrogate pair isn't a character
        ("r<C-v>U00110000", None),
        ("r<C-k>EQ", BELOW),
        ("r<C-k>e<C-e>", BELOW),
        ("r<C-k>LF", LINE_BREAK),
        ("r<C-k>e<C-c>", None),
        ("r<C-k><C-c>", None),
        ("r<C-c>", None),
        ("r<Esc>", None),
        ("r<S-Left>", None),
        ("r<A-x>", None),
        ("r<C-S-a>", None),
        ("r<Insert>", None),
    ],
)
def test_r_reads_its_character(keys: str, expected: str | None) -> None:
    assert replace(keys)[0] == expected


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("rx", "x"),
        ("r<CR>", "\r"),
        ("r<C-j>", "\x00"),
        ("r<C-e>", "\x05"),
        ("r<C-y>", "\x19"),
        ("r<C-c>", "\x03"),
        ("r<C-k>e:", "ë"),
        ("r<C-k>CR", "\r"),
        ("r<C-k>LF", "\x00"),
        ("r<C-v>065", "A"),
        ("r<Esc>", None),
        ("r<Left>", None),
    ],
)
def test_r_in_visual_mode_puts_keys_in_as_they_are(keys: str, expected: str | None) -> None:
    assert replace(keys, visual=True)[0] == expected


def test_r_takes_a_count() -> None:
    assert replace("3rx") == ("x", 3)
    assert replace("12r<C-v>u20ac") == ("€", 12)
    assert replace("3rx", visual=True) == ("x", 3)


def test_r_shows_its_pending_keys_and_wants_text() -> None:
    parser = Parser()
    shown = []
    for key in ["2", "r", "<C-v>", "u", "2", "0", "a"]:
        parser.feed(key)
        shown.append((parser.pending, parser.wants_text, parser.wants_any_key))
    assert shown == [
        ("2", False, False),
        ("2r", True, True),
        ("2r^V", True, True),
        ("2r^Vu", True, True),
        ("2r^Vu2", True, True),
        ("2r^Vu20", True, True),
        ("2r^Vu20a", True, True),
    ]
    assert parser.feed("c") == Command(REPLACE, 2, key="€")
    assert (parser.pending, parser.wants_text, parser.wants_any_key) == ("", False, False)
    parser.feed("<C-w>")
    assert (parser.wants_text, parser.wants_any_key) == (False, True)


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("3w<Esc>ix", ["3", "w", "<Esc>", "i", "x"]),
        ("<<", ["<", "<"]),
        ("a<b", ["a", "<", "b"]),
        ("<<Esc>", ["<", "<Esc>"]),
        ("e\u0301\U0001f1fa\U0001f1e6", ["e\u0301", "\U0001f1fa\U0001f1e6"]),
    ],
)
def test_tokens_split_keys_into_whole_characters(keys: str, expected: list[str]) -> None:
    assert tokens(keys) == expected
