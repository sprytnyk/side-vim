from importlib.metadata import version

import side_vim


def test_installed_version_is_set() -> None:
    assert side_vim.__doc__
    assert version("side-vim") != "0"
