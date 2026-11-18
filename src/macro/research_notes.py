"""The analysts' written research: proposals extracted from their notes and what became of them.

Every note (docs/research/notes/<date>/*.md, docs/research/committee/<date>/note-*.md) ends with a YAML block
`proposals:` (docs/research/STANDARDS.md). `proposals` collects them; `follow_up` matches each one with the
committee's decisions (archive/decisions.csv, agent chief-investment-officer, same instrument and direction,
decided within 2 days): adopted proposals are in the book, the others must carry the CIO's reason in the
daily note."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import yaml

from macro.config import ROOT

RESEARCH = ROOT / "docs" / "research"
COLUMNS = [
    "date",
    "agent",
    "source",
    "ticker",
    "direction",
    "threshold",
    "horizon",
    "probability",
    "rationale",
]


def _blocks(text: str) -> list[str]:
    return re.findall(r"```ya?ml\s*\n(.*?)```", text, flags=re.S)


def proposals(root: Path = RESEARCH) -> pd.DataFrame:
    rows = []
    for folder in ("notes", "committee"):
        for f in sorted((Path(root) / folder).glob("20*/*.md")):
            agent = f.stem.removeprefix("note-")
            for block in _blocks(f.read_text(encoding="utf-8")):
                try:
                    data = yaml.safe_load(block) or {}
                except yaml.YAMLError:
                    continue
                for p in (data.get("proposals") or []) if isinstance(data, dict) else []:
                    if not isinstance(p, dict) or "ticker" not in p:
                        continue
                    rows.append(
                        {
                            "date": f.parent.name,
                            "agent": agent,
                            "source": str(f.relative_to(Path(root).parent.parent))
                            if ROOT in f.parents
                            else str(f),
                            **{k: p.get(k) for k in COLUMNS[3:]},
                        }
                    )
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def follow_up(props: pd.DataFrame, decisions: pd.DataFrame, days: int = 2) -> pd.DataFrame:
    """Adds `adopted` (a CIO decision on the same instrument and direction within `days` days)."""
    out = props.copy()
    if out.empty:
        return out.assign(adopted=pd.Series(dtype=bool))
    d = decisions[decisions["agent"] == "chief-investment-officer"] if not decisions.empty else decisions
    adopted = []
    for _, p in out.iterrows():
        ok = False
        if not d.empty:
            m = d[(d["target"].astype(str) == str(p["ticker"])) & (d["direction"] == p["direction"])]
            ok = bool(((pd.to_datetime(m["date"]) - p["date"]).abs() <= pd.Timedelta(days=days)).any())
        adopted.append(ok)
    return out.assign(adopted=adopted)


def word_counts(root: Path = RESEARCH) -> pd.DataFrame:
    """Words written per day and kind of work: the volume of the team's research, on the record."""
    rows = []
    for folder, kind in (("notes", "recherche approfondie"), ("committee", "comité")):
        for f in (Path(root) / folder).glob("20*/*.md"):
            rows.append(
                {
                    "date": f.parent.name,
                    "kind": kind,
                    "words": len(re.findall(r"\w+", f.read_text(encoding="utf-8"))),
                }
            )
    df = pd.DataFrame(rows, columns=["date", "kind", "words"])
    return (
        df.groupby(["date", "kind"])["words"]
        .agg(["count", "sum"])
        .rename(columns={"count": "notes", "sum": "words"})
        .reset_index()
        if not df.empty
        else df
    )
