"""Character classes and cell widths, as vim sees them. No Qt here.

A "character" here is one character as the user sees it: a grapheme cluster, which may
be several code points (a family emoji, a flag, a letter plus an accent). Its first
code point decides its class and width, as in vim, where accents belong to the
letter before them.
"""

from bisect import bisect_right

from side_vim._unicode_data import CLASS_STARTS, CLASS_VALUES, WIDTH_STARTS, WIDTH_VALUES


def char_class(ch: str, bigword: bool = False) -> int:
    """Vim's character class: 0 blank, 1 punctuation, 2 word character, 3 emoji, and
    more for some scripts (Hiragana, CJK ideographs, ...). "" stands for the end of a
    line, which vim counts as blank. With bigword (W, B, E) every non-blank is 1."""
    if not ch:
        return 0
    cls = CLASS_VALUES[bisect_right(CLASS_STARTS, ord(ch[0])) - 1]
    if bigword and cls:
        return 1
    return cls


def cell_width(ch: str) -> int:
    """How many screen cells vim gives a character: 2 for CJK and emoji, 1 for most.
    A tab's width depends on where it sits, so the caller handles tabs."""
    if not ch:
        return 0
    return WIDTH_VALUES[bisect_right(WIDTH_STARTS, ord(ch[0])) - 1]
