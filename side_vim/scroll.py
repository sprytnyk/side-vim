"""Ctrl+E, Ctrl+Y, Ctrl+D, Ctrl+U, Ctrl+F and Ctrl+B, worked out on line numbers, like
vim 9.1 with its defaults ('scrolloff' 0, 'startofline' on). No Qt here.

The screen is the lines from `top`, `height` of them. vim can scroll until only the
last line is left on the screen. An editor can stop earlier, with the last line at its
bottom: `max_top` is the highest top it allows. The cursor still goes to vim's line.
"""

from dataclasses import dataclass

SCROLL_KEYS = frozenset({"<C-e>", "<C-y>", "<C-d>", "<C-u>", "<C-f>", "<C-b>"})


@dataclass(frozen=True)
class Scrolled:
    top: int  # the new first line on the screen
    line: int  # the cursor's new line
    keep_column: bool  # True: the column j and k aim for; False: the first non-blank
    amount: int | None  # what Ctrl+D and Ctrl+U scroll from now on (vim's 'scroll')


def scroll(
    key: str,
    count: int | None,
    *,
    top: int,
    line: int,
    height: int,
    lines: int,
    max_top: int,
    amount: int | None = None,
) -> Scrolled | None:
    """One scrolling command. None where vim beeps and does nothing.

    top, line: the first line on the screen and the cursor's line. height: how many
    lines fit on the screen. lines: how many lines the text has. amount: what Ctrl+D and
    Ctrl+U scroll, if a count set it before; half the screen otherwise.
    """
    last = lines - 1
    height = max(height, 1)
    n = count or 1
    if key in ("<C-d>", "<C-u>"):
        if count:
            amount = min(count, height)
        step = amount or max(height // 2, 1)
        if key == "<C-d>":
            if line >= last:
                return None
            # unlike Ctrl+E and Ctrl+F, it stops with the last line at the bottom
            new_top = max(min(top + step, max_top, lines - height), top)
            return Scrolled(new_top, min(line + step, last), False, amount)
        if line <= 0:
            return None
        return Scrolled(max(top - step, 0), max(line - step, 0), False, amount)

    if key == "<C-e>":
        if top >= max_top:
            return None
        new_top = min(top + n, max_top)
        return Scrolled(new_top, max(line, new_top), True, amount)
    if key == "<C-y>":
        if top <= 0:
            return None
        new_top = max(top - n, 0)
        return Scrolled(new_top, min(line, new_top + height - 1), True, amount)

    # When a count asks for more pages than there are, vim beeps on the last one and
    # leaves the column alone.
    page = max(height - 2, 1)  # two lines stay on the screen
    beeped = False
    if key == "<C-f>":
        new_top = top
        for _ in range(n):
            if new_top + height - 1 >= last:  # the end is on the screen
                if new_top >= last:
                    beeped = True
                    break
                new_top = last
            else:
                new_top += page
        if new_top == top and top >= last:
            return None
        return Scrolled(min(new_top, max_top), min(new_top, last), beeped, amount)
    if key == "<C-b>":
        if top <= 0:
            return None
        new_top = before = top
        for _ in range(n):
            if new_top <= 0:
                beeped = True
                break
            before = new_top
            new_top -= page
            if new_top < 2:  # vim goes all the way up from one line short of the start
                new_top = 0
        line = min(before + 1, new_top + height - 1, last)
        return Scrolled(new_top, line, beeped, amount)
    raise ValueError(f"not a scrolling key: {key!r}")
