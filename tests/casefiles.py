"""Load recorded cases for unit and editor tests."""

import json
from pathlib import Path

CASE_DIR = Path(__file__).parent / "cases"


def load_cases(group: str | None = None) -> list[dict]:
    cases = []
    for path in sorted(CASE_DIR.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for row in document["cases"]:
            case = document.get("defaults", {}) | row
            if group is None or case["group"] == group:
                cases.append(case)
    return cases


def motion_rows(group: str) -> list[tuple]:
    return [
        (
            c["text"],
            c["cursor"][0] + 1,
            c["cursor"][1] + 1,
            c["keys"],
            tuple(n + 1 for n in c["expected"]["cursor"]),
        )
        for c in load_cases(group)
    ]


def search_rows() -> list[tuple]:
    return [
        (
            c["text"],
            *c["cursor"],
            c["keys"],
            c["search"]["text"],
            c["search"]["forward"],
            tuple(c["expected"]["cursor"]),
        )
        for c in load_cases("search")
    ]


def operator_rows(group: str) -> list[tuple]:
    return [
        (
            c["text"],
            c["cursor"][0] + 1,
            c["cursor"][1] + 1,
            c["keys"].removesuffix("X<Esc>"),
            c["expected"]["text"],
        )
        for c in load_cases(group)
    ]


def scroll_rows() -> list[tuple]:
    return [
        (c["top"], *c["cursor"], c["keys"], (c["expected"]["top"], *c["expected"]["cursor"]))
        for c in load_cases("scroll")
    ]
