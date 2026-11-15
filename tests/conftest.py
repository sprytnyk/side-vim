"""Qt runs offscreen, with HOME and every XDG folder in a temp dir.

Setting HOME alone isn't enough: Qt still reads the real XDG folders.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QPlainTextEdit

import side_vim.vim as vim_module
from side_vim.edits import Register


@pytest.fixture(scope="session")
def home(tmp_path_factory: pytest.TempPathFactory) -> Path:
    h = tmp_path_factory.mktemp("home")
    os.environ.update(
        HOME=str(h),
        XDG_CONFIG_HOME=str(h / ".config"),
        XDG_DATA_HOME=str(h / ".local" / "share"),
        XDG_CACHE_HOME=str(h / ".cache"),
        XDG_STATE_HOME=str(h / ".local" / "state"),
        XDG_RUNTIME_DIR=str(h / "runtime"),
        QT_QPA_PLATFORM="offscreen",
    )
    (h / "runtime").mkdir(mode=0o700)
    return h


@pytest.fixture(scope="session")
def qapp(home: Path) -> Iterator[QApplication]:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    yield app
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    shiboken6.delete(app)


@pytest.fixture(autouse=True)
def flush_deletes() -> Iterator[None]:
    """Run the deletes a test queued with deleteLater() as soon as the test ends.
    Otherwise Qt runs them in a later test's event loop, and any error they cause
    fails that test instead."""
    yield
    app = QApplication.instance()
    if app is not None:
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def empty_register() -> Iterator[None]:
    vim_module._register = Register()
    yield
    vim_module._register = Register()


@pytest.fixture
def editor(qapp: QApplication) -> Iterator[QPlainTextEdit]:
    editor = QPlainTextEdit()
    editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * 8)
    editor.resize(600, 300)
    editor.show()
    yield editor
    editor.close()
    editor.deleteLater()
