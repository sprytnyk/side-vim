"""Test recorder errors without running Vim."""

import importlib.util
import json
from pathlib import Path

import pytest
from casefiles import CASE_DIR, load_cases

SPEC = importlib.util.spec_from_file_location(
    "record_vim", Path(__file__).parent.parent / "scripts" / "record_vim.py"
)
assert SPEC is not None and SPEC.loader is not None
recorder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recorder)


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        ("ix<Esc>", r"ix\<Esc>"),
        ('i"\\<Esc>', r"i\"\\\<Esc>"),
        ("<C-[><C-r>", r"\<C-[>\<C-r>"),
        ("i日本é<CR><Esc>", "i日本é\\<CR>\\<Esc>"),
    ],
)
def test_keys_are_quoted_for_vim(keys: str, expected: str) -> None:
    assert recorder.vim_keys(keys) == expected


@pytest.mark.parametrize("keys", ["i\nx", "i\rx", "<x\n>"])
def test_raw_newlines_cannot_start_ex_commands(keys: str) -> None:
    with pytest.raises(ValueError, match="use <CR>"):
        recorder.vim_keys(keys)


def test_a_failed_recording_keeps_every_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    paths = [tmp_path / "first.json", tmp_path / "second.json"]
    original = json.dumps({"vim": "original", "cases": [{"id": "example"}]})
    for path in paths:
        path.write_text(original, encoding="utf-8")
    calls = 0

    def record(case: dict, directory: Path) -> tuple[dict, str]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("different character boundaries")
        return {"text": "new expectations"}, "vim example"

    monkeypatch.setattr(recorder, "record", record)
    monkeypatch.setattr(recorder.sys, "argv", ["record_vim.py", *map(str, paths)])
    assert recorder.main() == 1
    assert calls == 2
    assert all(path.read_text(encoding="utf-8") == original for path in paths)
    assert "second.json: example: different character boundaries" in capsys.readouterr().err


def test_cases_have_unique_names_and_recorded_results() -> None:
    cases = load_cases()
    assert cases
    assert len({case["id"] for case in cases}) == len(cases)
    for path in CASE_DIR.glob("*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["vim"].startswith("vim ")
    for case in cases:
        assert set(case["expected"]) == {"text", "cursor", "register"} | (
            {"top"} if "height" in case else set()
        )


@pytest.mark.parametrize(
    ("text", "vim_characters"),
    [
        ("🇺🇦", ["🇺", "🇦"]),
        ("👨\u200d👩\u200d👧", ["👨", "\u200d", "👩", "\u200d", "👧"]),
    ],
)
def test_result_with_different_characters_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str, vim_characters: list[str]
) -> None:
    def run(*args: object, **kwargs: object) -> None:
        output = {
            "expected": {"text": text, "cursor": [0, 0], "register": ["", False]},
            "clusters": [vim_characters],
        }
        (tmp_path / "output.json").write_text(json.dumps(output), encoding="utf-8")

    monkeypatch.setattr(recorder.subprocess, "run", run)
    with pytest.raises(ValueError, match="split characters differently in the result"):
        recorder.record({"text": "x", "cursor": [0, 0], "keys": ""}, tmp_path)
