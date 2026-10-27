"""Regenerate the README executive summary (between the SUMMARY markers) from current results.

In demo mode the block is a placeholder: no synthetic number ever reaches the README.

    MACRO_MODE=live python scripts/update_readme.py
"""

from __future__ import annotations

import re

import _bootstrap  # noqa: F401
from macro.config import ROOT
from macro.utils import DISCLAIMER, is_demo, run_metadata

START, END = "<!-- SUMMARY:START -->", "<!-- SUMMARY:END -->"


def summary() -> str:
    if is_demo():
        return (
            "_No live results yet. The executive summary is generated from real data by `make live` and the weekly "
            "`refresh` workflow (`scripts/update_readme.py`); it is never filled with synthetic numbers._"
        )
    from macro import pipeline

    v = pipeline.build_views()
    t = v["template"]
    meta = run_metadata()
    lines = [
        f"_Generated {meta['run_timestamp']} from data as of {v['as_of']:%Y-%m-%d} (git {meta['git_hash']}). {DISCLAIMER}_",
        "",
    ]
    lines += [f"- {c}" for c in v["comments"].values()]
    lines += [f"- {t['View']}", f"- {t['What is priced']}"]
    lines += [f"- {e}" for e in t["Evidence"][1:]]
    return "\n".join(lines)


def main() -> int:
    p = ROOT / "README.md"
    s = p.read_text()
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), f"{START}\n{summary()}\n{END}", s, flags=re.S)
    p.write_text(new)
    print("README summary updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
