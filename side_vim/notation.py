"""Read vim key notation, shared by the parser, the test driver and the recorder."""

import re

from side_vim.text import split_clusters


def is_named(key: str) -> bool:
    """True for a key with a name, like "<Tab>" or "<C-v>". False for a character,
    even "<"."""
    return len(key) > 2 and key.startswith("<") and key.endswith(">")


def tokens(keys: str) -> list[str]:
    """Split "3w<Esc>ix" into "3", "w", "<Esc>", "i", "x". A character made of several
    code points, like a flag or e and a combining accent, is one key, as Qt sends it."""
    out: list[str] = []
    # with the group, re.split puts each named key at an odd index
    for n, part in enumerate(re.split(r"(<[^<>]+>)", keys)):
        if n % 2:
            out.append(part)
        else:
            out.extend(split_clusters(part))
    return out
