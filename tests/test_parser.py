import pytest

from side_vim.parser import (
    CTRL_KEYS,
    LINE,
    NORMAL_ACTIONS,
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


@pytest.mark.parametrize(
    ("keys", "pending"),
    [("2", "2"), ("2d", "2d"), ("d3", "d3"), ("g", "g"), ("dg", "dg"), ("12", "12")],
)
def test_pending_keys(keys: str, pending: str) -> None:
    results, left = feed(keys)
    assert all(r is None for r in results)
    assert left == pending


@pytest.mark.parametrize("keys", ["q", "dx", "dp", "gx", "dgx", "2q", "dc", "z"])
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
        else:
            assert parser.feed(key) == Command(key)
    for key in VISUAL_ACTIONS:
        assert Parser().feed(key, visual=True) == Command(key)
