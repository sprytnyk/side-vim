Run `uv run python scripts/record_vim.py` to record all case files. Pass file paths
to record specific files. The recorder needs Vim with `+eval` and a Unix terminal
for scrolling. Tests read the saved results, so CI does not need Vim.

Each file has a `vim` version and a `cases` list. Optional `defaults` supply fields
shared by every case in the file. Each case has:

- `id`: a unique test name.
- `group`: a category used to select cases for unit tests.
- `text`: the starting text.
- `cursor`: the starting `[line, column]`. Both start at zero. Columns count
  characters, not bytes.
- `keys`: Vim notation, such as `3w` or `ix<Esc>|u`. `|` separates undo steps.
- Optional `search`: literal `text`, `forward`, and `jump`. With `jump: false`,
  setting the pattern does not move the cursor before the keys run.
- Optional `height` and `top`: text rows in the fixed-size terminal and the first
  visible line. The terminal is 80 columns wide, with wrapping off.
- `expected`: the recorded `text`, `cursor`, and `register`. The register is
  `[text, linewise]`. Scrolling cases also record `top`.

The recorder rejects cases where Vim and side-vim split characters differently.
It checks the input, keys, search text and result. Accents, CJK and single emoji
work. Joined emoji and flags have separate Qt tests. Backspace cases also have
separate tests because Vim's default Insert-mode behavior differs.

Qt stops scrolling with the last line at the bottom. Vim can put it at the top.
The editor tests limit the expected top line to Qt's range. Cases that start
beyond that range run only in the scrolling unit tests.
