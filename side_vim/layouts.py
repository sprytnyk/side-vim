"""Keyboard layout maps for VimMode.layout_map."""

# The Ukrainian layout: each Cyrillic letter maps to the Latin key in the same place,
# so Normal mode keys work without switching layouts. Only letters: punctuation stays
# as it is, so the English layout keeps working. ґ is left out, since its key differs
# between layout variants.
UKRAINIAN_LOWER = "йцукенгшщзхїфівапролджєячсмитьбю"
LATIN_LOWER = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
LATIN_UPPER = 'QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>'
UKRAINIAN: dict[str, str] = {
    **dict(zip(UKRAINIAN_LOWER, LATIN_LOWER, strict=True)),
    **dict(zip(UKRAINIAN_LOWER.upper(), LATIN_UPPER, strict=True)),
}
