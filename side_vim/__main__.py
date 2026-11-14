"""A demo: an editor with vim keys and a status bar. Run it with `make run`."""

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
)

from side_vim import Mode, VimMode

SAMPLE = """\
side-vim demo. Esc goes back to Normal mode; i, a, I, A, o and O start typing.
Try w b e, W B E, 0 ^ $, gg G, h j k l, with counts: 3w, 2j, 5G.
Edit with x, dw, d2j, cw, cc, C, D, dd, yy, yw, p, P and J; u undoes, Ctrl+R redoes.
Tick "clipboard" to yank to the system clipboard and paste from it.
v and V select, or drag with the mouse; then move, o, and d c y x p on the selection.
/ and ? open the find bar: type, Enter, then n and N. Esc closes the find bar first.
Scroll with Ctrl+E and Ctrl+Y (a line), Ctrl+D and Ctrl+U (half a screen), Ctrl+F and
Ctrl+B (a screen). Tick "read-only" to try that; on the Ukrainian layout, ц works as w.

\tA tab first, then words: foo.bar(baz) and foo-bar_baz.
Emoji count as one character: 😀 👨‍👩‍👧 🇺🇦 1️⃣ and é.
CJK is two cells wide, so j and k keep the column: 日本語のテキスト here.
Українською теж: слово, ще одне слово.

A long line that wraps when the window is narrow enough, to show that j and k move by \
whole lines and not by the rows on the screen, the same as in vim with its defaults.

The lines below are there to scroll through and to search in (try /rent or /😀).
"""

FILLER = [
    "rent 1200, food 350, transport 90",
    "    indented: savings = rent * 0.2",
    "a line with an emoji 😀 and a flag 🇺🇦",
    "",
    "\tafter a tab: total, rent, food",
    "short",
    "Українська: оренда, їжа, транспорт",
    "日本語のテキスト and rent again",
]


def sample() -> str:
    lines = [f"{i:3}  {FILLER[i % len(FILLER)]}" for i in range(1, 301)]
    return SAMPLE + "\n" + "\n".join(lines) + "\n"


class Demo(QMainWindow):
    """The demo window: an editor with vim keys, a find bar and a status bar."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("side-vim demo")

        self.editor = editor = QPlainTextEdit()
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(16)
        editor.setFont(font)
        editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * 8)
        editor.setPlainText(sample())
        self.setCentralWidget(editor)

        self.vim = vim = VimMode(editor)

        # a find bar: / and ? open it; Enter hands the text to vim, which jumps to it
        self.find = QLineEdit()
        self.find.setPlaceholderText("find")
        self.find.hide()
        self._forward = True
        self.find.returnPressed.connect(self._run_find)
        QShortcut(
            QKeySequence("Esc"),
            self.find,
            self.close_find,
            context=Qt.ShortcutContext.WidgetShortcut,
        )
        vim.search_hook = self.open_find
        vim.escape_hook = self.close_find

        self.mode_label = QLabel()
        keys_label = QLabel()
        toggle = QCheckBox("vim")
        toggle.setChecked(True)
        toggle.toggled.connect(vim.set_enabled)
        toggle.toggled.connect(self.mode_label.setVisible)
        clipboard = QCheckBox("clipboard")
        clipboard.toggled.connect(lambda on: setattr(vim, "clipboard", on))
        read_only = QCheckBox("read-only")
        read_only.toggled.connect(editor.setReadOnly)
        for box in (toggle, clipboard, read_only):
            box.toggled.connect(lambda _: editor.setFocus())

        self._show_mode(vim.mode)
        vim.mode_changed.connect(self._show_mode)
        vim.pending_changed.connect(keys_label.setText)

        status = self.statusBar()
        status.addWidget(self.mode_label)
        status.addWidget(self.find, 1)
        status.addPermanentWidget(keys_label)
        status.addPermanentWidget(read_only)
        status.addPermanentWidget(clipboard)
        status.addPermanentWidget(toggle)
        self.resize(1200, 640)

    def open_find(self, forward: bool) -> None:
        self._forward = forward
        self.find.setPlaceholderText("find down" if forward else "find up")
        self.find.show()
        self.find.selectAll()
        self.find.setFocus()

    def close_find(self) -> bool:
        """The Esc hook: closes the find bar first, if it's open."""
        if not self.find.isVisible():
            return False
        self.find.hide()
        self.editor.setFocus()
        return True

    def _run_find(self) -> None:
        self.close_find()
        self.vim.set_search(self.find.text(), self._forward)

    def _show_mode(self, mode: Mode) -> None:
        self.mode_label.setText(f"-- {mode.value.upper()} --")


def main() -> int:
    app = QApplication(sys.argv)
    window = Demo()
    window.show()
    window.editor.setFocus()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
