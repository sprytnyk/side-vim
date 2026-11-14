"""Qt runs offscreen, with HOME and every XDG folder in a temp dir.

Setting HOME alone isn't enough: Qt still reads the real XDG folders.
"""

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication


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
def qapp(home: Path) -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app
