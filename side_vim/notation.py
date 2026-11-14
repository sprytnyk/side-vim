"""Read vim key notation, shared by the test driver and the recorder."""

import re


def tokens(keys: str) -> list[str]:
    """Split "3w<Esc>ix" into "3", "w", "<Esc>", "i", "x"."""
    return re.findall(r"<[^<>]+>|.", keys, re.S)
