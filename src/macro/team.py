"""The fund's research team: roles (config/team.yaml, .claude/agents/) and their work log
(archive/team_log.csv: one row per assignment, written by the research runs)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from macro.config import ROOT

TEAM = ROOT / "config" / "team.yaml"
LOG = ROOT / "archive" / "team_log.csv"
DESK_LOG = ROOT / "archive" / "desk_log.csv"  # computed GitHub desk notes (scripts/desk_run.py)
AGENTS = ROOT / ".claude" / "agents"
COLUMNS = ["date", "agent", "status", "task", "summary", "link"]


def roster(path: Path = TEAM) -> pd.DataFrame:
    with open(path, encoding="utf-8") as fh:
        t = yaml.safe_load(fh)["teams"]
    rows = [
        {
            "team": team,
            "agent": a,
            "title": d["title"],
            "mandate": d["mandate"],
            "defined": (AGENTS / f"{a}.md").exists(),
        }
        for team, members in t.items()
        for a, d in members.items()
    ]
    return pd.DataFrame(rows)


def read_log(path: Path = LOG, desk: Path | None = DESK_LOG) -> pd.DataFrame:
    """The committee's log, plus the GitHub desk's daily lines when `desk` exists. A committee line
    and a desk line of the same day both show; the committee's comes first (it is the judgement)."""
    parts = [pd.read_csv(p) for p in (path, desk) if p is not None and Path(p).exists()]
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat(parts, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["_desk"] = df["task"].astype(str).str.contains("(calcul GitHub)", regex=False)
    return df.sort_values(["date", "_desk"], ascending=[True, False], kind="stable").drop(columns="_desk")


def append_log(rows: list[dict], path: Path = LOG) -> int:
    """Append assignments (date, agent, status 'en cours' or 'terminé', task, summary, link)."""
    df = pd.DataFrame(rows, columns=COLUMNS)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, mode="a", header=not Path(path).exists(), index=False)
    return len(df)


def current_and_past(log: pd.DataFrame, agent: str, n: int = 5) -> tuple[pd.Series | None, pd.DataFrame]:
    """The latest assignment of an agent and its previous ones, newest first."""
    d = log[log["agent"] == agent].sort_values("date", ascending=False, kind="stable")
    if d.empty:
        return None, d
    return d.iloc[0], d.iloc[1 : n + 1]
