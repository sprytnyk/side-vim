"""A demo: an editor with vim keys and a status bar. Run it with `make run`."""

import sys

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QMainWindow, QPlainTextEdit

from side_vim import Mode, VimMode

SAMPLE = """\
side-vim demo. Esc goes back to Normal mode; i, a, I, A, o and O start typing.
Try w b e, W B E, 0 ^ $, gg G, h j k l, with counts: 3w, 2j, 5G.
Edit with x, dw, d2j, cw, cc, C, D, dd, yy, yw, p, P and J; u undoes, Ctrl+R redoes.
Tick "clipboard" to yank to the system clipboard and paste from it.
v and V select, or drag with the mouse; then move, o, and d c y x p on the selection.

\tA tab first, then words: foo.bar(baz) and foo-bar_baz.
Emoji count as one character: 😀 👨‍👩‍👧 🇺🇦 1️⃣ and é.
CJK is two cells wide, so j and k keep the column: 日本語のテキスト here.
Українською теж: слово, ще одне слово.

A long line that wraps when the window is narrow enough, to show that j and k move by \
whole lines and not by the rows on the screen, the same as in vim with its defaults.
"""


def main() -> int:
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("side-vim demo")

    editor = QPlainTextEdit()
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(16)
    editor.setFont(font)
    editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * 8)
    editor.setPlainText(SAMPLE)
    window.setCentralWidget(editor)

    vim = VimMode(editor)

    mode_label = QLabel()
    keys_label = QLabel()
    toggle = QCheckBox("vim")
    toggle.setChecked(True)
    toggle.toggled.connect(vim.set_enabled)
    toggle.toggled.connect(lambda on: mode_label.setVisible(on))
    toggle.toggled.connect(lambda _: editor.setFocus())
    clipboard = QCheckBox("clipboard")
    clipboard.toggled.connect(lambda on: setattr(vim, "clipboard", on))
    clipboard.toggled.connect(lambda _: editor.setFocus())

    def show_mode(mode: Mode) -> None:
        mode_label.setText(f"-- {mode.value.upper()} --")

    show_mode(vim.mode)
    vim.mode_changed.connect(show_mode)
    vim.pending_changed.connect(keys_label.setText)

    status = window.statusBar()
    status.addWidget(mode_label)
    status.addPermanentWidget(keys_label)
    status.addPermanentWidget(clipboard)
    status.addPermanentWidget(toggle)

    window.resize(1200, 640)
    window.show()
    editor.setFocus()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
