"""Keyboard layout maps for VimMode.layout_map."""

# The Ukrainian layout: each Cyrillic letter maps to the Latin key in the same place,
# so Normal mode keys work without switching layouts. Only letters: punctuation stays
# as it is, so the English layout keeps working. ґ is left out, since its key differs
# between layout variants.
_LOWER = "йцукенгшщзхїфівапролджєячсмитьбю"
_LATIN_LOWER = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
_LATIN_UPPER = 'QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>'
UKRAINIAN: dict[str, str] = {
    **dict(zip(_LOWER, _LATIN_LOWER, strict=True)),
    **dict(zip(_LOWER.upper(), _LATIN_UPPER, strict=True)),
}
