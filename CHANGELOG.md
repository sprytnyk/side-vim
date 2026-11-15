# Changelog

## 0.2.0 - 2026-11-15

### Highlights

- Add `r` to replace characters in Normal and Visual mode. After `r`, Enter,
  `Ctrl+E`, `Ctrl+Y`, `Ctrl+V` and `Ctrl+K` digraphs work as in Vim.
- Add `~` to switch case in Normal and Visual mode, with Vim's case rules.
- Pass `Ctrl+W` and the next key to a new `window_hook`, so an app can move the
  focus between its panels.
- Pass `z=`, `]s`, `[s`, `zg` and `zG` to a new `spell_hook`.

### Fixes

- Drop pending keys when the focus moves to another widget, so a click elsewhere
  no longer leaves an `r` or `2d` waiting.

## 0.1.1 - 2026-11-15

### Fixes

- Show the character on the Normal mode block cursor in the background colour, as
  Vim does, so dim text like comments stays readable.

### Changes

- Outside Insert mode the editor is in overwrite mode, so a click lands on the
  character under the mouse. The editor's own setting comes back in Insert mode
  and when Vim is off.
- Sign PEP 740 attestations for the files uploaded to PyPI.
- Attach the PyPI wheel to GitHub releases with signed checksums.

## 0.1.0 - 2026-11-15

### Highlights

- Add Normal, Insert, Visual and Visual Line modes to an existing `QPlainTextEdit`.
- Support motions, counts, editing, yank and paste, undo and redo, and scrolling.
- Provide search and Esc hooks, mode and pending-key signals, and `normal()`.
- Keep emoji and accented characters whole, support Ukrainian keyboard layouts,
  and allow movement, selection and yank in read-only editors.
- Include a demo app and tests against saved Vim results.

### Fixes

- Leave Insert mode safely after the app switches documents.
- Keep a document marked as saved when leaving Insert mode after a save.

### Changes

- Include a release skill for signed releases and PyPI publishing.
