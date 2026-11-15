"""Record tests/cases/*.json with Vim, without loading the user's configuration.

Run `uv run python scripts/record_vim.py [case-file ...]`. Positions are zero-based
characters. `|` separates undo steps. Search text is literal. Scrolling uses a
terminal with `height` text rows and 80 columns. Results include the Vim version.
Tests replay the results without running Vim.
"""

import argparse
import json
import os
import select
import signal
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if sys.platform != "win32":
    import fcntl
    import pty
    import termios

from side_vim.notation import is_named, tokens
from side_vim.text import split_clusters

ROOT = Path(__file__).resolve().parent.parent

# What can go wrong while recording one case: Vim fails or hangs, or refuses it.
ERRORS = (ValueError, OSError, subprocess.SubprocessError)

VIM = ["vim", "-u", "NONE", "-i", "NONE", "-N", "-n", "--noplugin"]

PRELUDE = r"""
set encoding=utf-8 nojoinspaces nomodeline noswapfile nobackup nowritebackup
set laststatus=0 noruler noshowcmd shortmess+=I nowrap
function! Clusters(text)
  let chars = []
  for i in range(strchars(a:text, 1))
    call add(chars, strcharpart(a:text, i, 1, 1))
  endfor
  return chars
endfunction
function! Check(lines, expected)
  let actual = map(copy(a:lines), 'Clusters(v:val)')
  if actual != a:expected
    throw 'vim and side-vim split characters differently'
  endif
endfunction
"""


def vim_string(text: str) -> str:
    """Quote a literal Vim string. Pass newlines through JSON instead."""
    return "'" + text.replace("'", "''") + "'"


def vim_keys(keys: str) -> str:
    """Escape keys for a Vim double-quoted string and expand named keys."""
    if "\n" in keys or "\r" in keys:
        raise ValueError("use <CR> for a typed newline")
    parts = []
    for token in tokens(keys):
        if is_named(token):
            parts.append("\\" + token.replace("\\", "\\\\").replace('"', '\\"'))
        elif token in '\\"':
            parts.append("\\" + token)
        else:
            parts.append(token)
    return "".join(parts)


def terminal_run(command: list[str], height: int, environment: dict[str, str]) -> None:
    """Run Vim in a fixed-size terminal and read its output until it exits."""
    if sys.platform == "win32":
        raise ValueError("record scrolling on Unix; replay works on Windows too")
    master, slave = pty.openpty()
    process = None
    try:
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", height + 1, 80, 0, 0))
        process = subprocess.Popen(
            command,
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            env=environment,
        )
        os.close(slave)
        slave = -1
        # Read output so Vim cannot block on a full terminal buffer.
        # Check the deadline between reads.
        deadline = time.monotonic() + 15
        while process.poll() is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("vim timed out in the fixed-size terminal")
            if select.select([master], [], [], 0.1)[0]:
                try:
                    os.read(master, 65536)
                except OSError:
                    break
        process.wait(timeout=2)
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command)
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        os.close(master)
        if slave != -1:
            os.close(slave)


def case_input(case: dict) -> dict:
    """Validate the starting cursor and prepare character-boundary checks."""
    lines = case["text"].split("\n")
    cursor = case["cursor"]
    if not 0 <= cursor[0] < len(lines) or cursor[1] < 0:
        raise ValueError(f"invalid starting cursor: {cursor}")
    check_lines = lines + [case["keys"]]
    if "search" in case:
        check_lines += case["search"]["text"].split("\n")
    return {
        "lines": lines,
        "check_lines": check_lines,
        "clusters": [split_clusters(row) for row in check_lines],
    }


def build_script(case: dict, directory: Path) -> str:
    """Build the Vim script for one case."""
    cursor = case["cursor"]
    output = directory / "output.json"
    script = [
        PRELUDE,
        "try",
        f"let input = json_decode(join(readfile({vim_string(str(directory / 'input.json'))}), ''))",
        "call Check(input.check_lines, input.clusters)",
        "set undolevels=-1",
        # Leave an empty buffer untouched. setline(['']) creates an empty line
        # that Vim treats as deleted text when updating the register.
        "if input.lines !=# [''] | call setline(1, input.lines) | endif",
        "set undolevels=1000",
        "let &undolevels = &undolevels",
    ]
    if "height" in case:
        script += [
            "redraw",
            f"if winheight(0) != {case['height']} | throw 'wrong terminal height' | endif",
            f"call cursor({case['top'] + 1}, 1)",
            "normal! zt",
            "redraw",
        ]
    script.append(f"call setcursorcharpos({cursor[0] + 1}, {cursor[1] + 1})")
    if "search" in case and case["search"]["text"]:
        search = case["search"]
        pattern = "\\V" + search["text"].replace("\\", "\\\\").replace("\n", "\\n")
        script += [
            f"let @/ = {vim_string(pattern)}",
            f"let v:searchforward = {int(search['forward'])}",
        ]
        if search["jump"]:
            # n shares / and ?'s literal matching, wrap and no-match behavior.
            script.append('silent! execute "normal! n"')
    for chunk in case["keys"].split("|"):
        if chunk:
            script += [
                f'silent! execute "normal! {vim_keys(chunk)}"',
                "let &undolevels = &undolevels",
            ]
            if "height" in case:
                script.append("redraw")
    script += [
        "let result = {'text': join(getline(1, '$'), \"\\n\"),",
        "      \\ 'cursor': [line('.') - 1, charcol('.') - 1],",
        "      \\ 'register': [getreg('\"'), getregtype('\"') ==# 'V' ? v:true : v:false]}",
        "let clusters = map(getline(1, '$'), 'Clusters(v:val)')",
        "let vim_version = execute('version')",
    ]
    if "height" in case:
        script.append("let result.top = line('w0') - 1")
    script += [
        "let output = {'expected': result, 'clusters': clusters, 'vim': vim_version}",
        f"call writefile([json_encode(output)], {vim_string(str(output))})",
        "catch",
        "let output = {'error': v:exception, 'at': v:throwpoint}",
        f"call writefile([json_encode(output)], {vim_string(str(output))})",
        "endtry",
        "qa!",
    ]
    return "\n".join(script) + "\n"


def read_result(output: Path) -> tuple[dict, str]:
    """Read a Vim result and reject incompatible character boundaries."""
    result = json.loads(output.read_text(encoding="utf-8"))
    if "error" in result:
        raise ValueError(f"{result['error']} ({result['at']})")
    expected = result["expected"]
    for row, clusters in zip(expected["text"].split("\n"), result["clusters"], strict=True):
        if list(split_clusters(row)) != clusters:
            raise ValueError("vim and side-vim split characters differently in the result")
    version_lines = result["vim"].splitlines()
    version = next(line for line in version_lines if "IMproved" in line).split()[4]
    patches = next((line for line in version_lines if line.startswith("Included patches")), "")
    return expected, f"vim {version}" + (
        f", patches {patches.partition(':')[2].strip()}" if patches else ""
    )


def record(case: dict, directory: Path) -> tuple[dict, str]:
    """Start a fresh Vim for each case to reset registers, undo and search."""
    payload = case_input(case)
    (directory / "input.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    output = directory / "output.json"
    script_path = directory / "record.vim"
    script_path.write_text(build_script(case, directory), encoding="utf-8")
    command = VIM + ([] if "height" in case else ["-Es"]) + ["-S", str(script_path)]
    environment = {
        # Find the same vim the user runs, such as Homebrew's on macOS.
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(directory),
        "XDG_CONFIG_HOME": str(directory),
        "XDG_DATA_HOME": str(directory),
        "XDG_CACHE_HOME": str(directory),
        "XDG_STATE_HOME": str(directory),
        "TERM": "xterm",
        "LANG": "C.UTF-8",
    }
    if "height" in case:
        terminal_run(command, case["height"], environment)
    else:
        subprocess.run(
            command,
            check=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=environment,
        )
    return read_result(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.files or sorted((ROOT / "tests" / "cases").glob("*.json"))
    documents = []
    try:
        with tempfile.TemporaryDirectory(prefix="side-vim-record-") as temporary:
            for path in paths:
                document = json.loads(path.read_text(encoding="utf-8"))
                for index, row in enumerate(document["cases"]):
                    directory = Path(temporary) / f"case-{len(documents)}-{index}"
                    directory.mkdir()
                    try:
                        row["expected"], document["vim"] = record(
                            document.get("defaults", {}) | row, directory
                        )
                    except ERRORS as error:
                        raise ValueError(f"{path.name}: {row['id']}: {error}") from error
                documents.append((path, document))
                print(f"{path.name}: recorded {len(document['cases'])} cases", flush=True)
        # Save only after every selected case records successfully.
        for path, document in documents:
            path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    except ERRORS as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
