"""Character classes, widths and case. Expected values are vim 9.1's charclass(),
strdisplaywidth() and ~."""

import pytest

from side_vim._unicode_data import (
    CLASS_STARTS,
    CLASS_VALUES,
    SWITCH_CASE,
    WIDTH_STARTS,
    WIDTH_VALUES,
)
from side_vim.unicode import cell_width, char_class, switch_case


@pytest.mark.parametrize(
    ("ch", "cls", "width"),
    [
        (" ", 0, 1),
        ("\xa0", 0, 1),  # no-break space is blank too
        ("\t", 0, None),  # a tab's width depends on where it is
        ("A", 2, 1),
        ("_", 2, 1),
        ("7", 2, 1),
        (".", 1, 1),
        ("\xd7", 2, 1),  # vim's 'iskeyword' takes 192-255 whole, × included
        ("и", 2, 1),  # Cyrillic и
        ("ї", 2, 1),  # Ukrainian ї
        ("—", 1, 1),  # em dash
        ("«", 1, 1),  # «
        ("あ", 0x3040, 2),  # Hiragana
        ("一", 0x4E00, 2),  # CJK ideograph
        ("Ａ", 2, 2),  # fullwidth A
        ("\U0001f600", 3, 2),  # emoji
        ("\U0001f1fa", 3, 2),  # regional indicator, half a flag
        ("\x01", 1, 2),  # control characters show as ^A
    ],
)
def test_matches_vim(ch: str, cls: int, width: int | None) -> None:
    assert char_class(ch) == cls
    if width is not None:
        assert cell_width(ch) == width


def test_line_end_is_blank_and_takes_no_room() -> None:
    assert char_class("") == 0
    assert cell_width("") == 0


def test_bigword_lumps_every_non_blank_together() -> None:
    assert char_class("a", bigword=True) == 1
    assert char_class(".", bigword=True) == 1
    assert char_class("\U0001f600", bigword=True) == 1
    assert char_class(" ", bigword=True) == 0


def test_a_cluster_counts_as_its_first_code_point() -> None:
    assert char_class("é") == 2
    assert char_class("\U0001f468‍\U0001f469‍\U0001f467") == 3
    assert cell_width("\U0001f468‍\U0001f469‍\U0001f467") == 2
    assert cell_width("\U0001f1fa\U0001f1e6") == 2
    assert cell_width("é") == 1


@pytest.mark.parametrize(
    ("starts", "values"), [(CLASS_STARTS, CLASS_VALUES), (WIDTH_STARTS, WIDTH_VALUES)]
)
def test_tables_are_well_formed(starts: tuple[int, ...], values: tuple[int, ...]) -> None:
    assert len(starts) == len(values) > 100
    assert starts[0] == 0
    assert list(starts) == sorted(set(starts))
    assert starts[-1] <= 0x10FFFF
    # neighbouring runs differ, or they would be one run
    assert all(a != b for a, b in zip(values, values[1:], strict=False))


def test_lookup_finds_every_run_edge() -> None:
    for i, start in enumerate(CLASS_STARTS[1:], 1):
        if 0xD800 <= start <= 0xDFFF:
            continue
        assert char_class(chr(start)) == CLASS_VALUES[i]
        if start - 1 >= 1 and not 0xD800 <= start - 1 <= 0xDFFF:
            assert char_class(chr(start - 1)) == CLASS_VALUES[i - 1]
    for i, start in enumerate(WIDTH_STARTS[1:], 1):
        if 0xD800 <= start <= 0xDFFF:
            continue
        assert cell_width(chr(start)) == WIDTH_VALUES[i]


@pytest.mark.parametrize(
    ("ch", "switched"),
    [
        ("a", "A"),
        ("A", "a"),
        ("7", "7"),
        ("ї", "Ї"),
        ("Ґ", "ґ"),
        ("ß", "ß"),  # Python makes SS
        ("ﬁ", "ﬁ"),  # Python makes FI
        ("ǅ", "Ǆ"),  # Python leaves it
        ("İ", "i"),  # Python adds a dot above
        ("ſ", "S"),  # but S becomes s
        ("e\u0301", "E\u0301"),  # only the letter, the accent stays
        ("\U0001f1fa\U0001f1e6", "\U0001f1fa\U0001f1e6"),
        ("", ""),  # the end of a line
    ],
)
def test_switch_case_matches_vim(ch: str, switched: str) -> None:
    assert switch_case(ch) == switched


def test_switch_case_keeps_the_utf16_length() -> None:
    """Qt positions count UTF-16 units, so ~ must not change a character's length."""
    for before, after in SWITCH_CASE.items():
        assert (before > 0xFFFF) == (after > 0xFFFF)
