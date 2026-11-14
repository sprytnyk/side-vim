# Mac key checklist

Run `make run` on a real Mac before releasing 0.1.0. Use the physical Control
key for Ctrl below, and Command for Cmd. Start with the English keyboard layout.

| Check | Expected result |
| --- | --- |
| Type `x`, `u`, then Ctrl+R. | Delete one character, undo it, then redo it. |
| Try Ctrl+E/Y, Ctrl+D/U and Ctrl+F/B in the long part of the demo. | Scroll a line, half a screen and a screen in each direction. Ctrl+F/B put the cursor on the first non-blank character. |
| Press `v`, then try those scrolling keys and Ctrl+[. Repeat with `V`. | Scrolling extends the selection. Ctrl+[ returns to Normal. |
| Press `i`, type text, then Ctrl+[. Repeat with Esc. | Both leave Insert mode. |
| In Insert mode, try Cmd+A, Cmd+C, Cmd+V and Cmd+Z. | Qt selects, copies, pastes and undoes as usual. |
| In Normal and Visual modes, select text and try Cmd+C, then Cmd+V and Cmd+X. | Cmd+C copies. Cmd+V and Cmd+X leave the text as it is. |
| After `x` then `u`, press Cmd+R. | It does not run Vim's redo. Ctrl+R still does. |
| Press `/`, type `rent`, then Enter, `n` and `N`. Try `?` too. | Enter jumps to a match; `n` repeats in the chosen direction and `N` reverses it. |
| Open the find bar with `/`, then press Esc. | The find bar closes and focus returns to the editor. |
| Tick read-only, then try scrolling, `v`, `o`, `y`, `x` and `i`. | Movement, selection and yank work; editing does nothing. |
| Switch to Ukrainian: try `ц`, `ш`, Esc, `г`, and Ctrl+к after an edit and undo. | `ц` moves like `w`, `ш` enters Insert, `г` undoes and Ctrl+к redoes. Insert mode types Ukrainian normally. |
| Disable Vim with the checkbox and type; enable it again. | The plain editor works while disabled; enabling starts Normal mode. |

Record the macOS version, Python and PySide6 versions, keyboard layout, and any
failed check when reporting the result. Automated offscreen tests simulate key
events; this checks what the physical keyboard sends.
