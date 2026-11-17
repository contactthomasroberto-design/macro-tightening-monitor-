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


# ---------------------------------------------------------------------------- live task board
STATUS = ROOT / "archive" / "committee_status.csv"  # written by the nightly committee as it works
STATUS_COLUMNS = ["time", "agent", "stage", "status", "task"]
STAGES = ["à faire", "en cours", "terminé"]


def set_status(rows: list[dict], path: Path = STATUS) -> int:
    """Record what members are doing now: one row per (agent, stage, task) with status à faire,
    en cours or terminé and a UTC time. The board keeps the latest row of each agent and task."""
    now = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M")
    df = pd.DataFrame([{"time": now, **r} for r in rows], columns=STATUS_COLUMNS)
    bad = set(df["status"]) - set(STAGES)
    if bad:
        raise ValueError(f"status must be one of {STAGES}, not {bad}")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, mode="a", header=not Path(path).exists(), index=False)
    return len(df)


def board(
    status_path: Path = STATUS,
    desk_index: Path | None = None,
    now: pd.Timestamp | None = None,
    hours: int = 30,
) -> pd.DataFrame:
    """Tasks of the last `hours` hours, one row per agent and task (latest status), from the
    committee's status file, the GitHub desk (each note is a finished task at its run time) and the
    committee log's 'en cours' lines for the next day (to do)."""
    now = now or pd.Timestamp.now(tz="UTC")
    rows = []
    if Path(status_path).exists():
        s = pd.read_csv(status_path)
        s["time"] = pd.to_datetime(s["time"], utc=True, errors="coerce")
        s = s[s["time"] >= now - pd.Timedelta(hours=hours)]
        s = s.sort_values("time").groupby(["agent", "task"], as_index=False).last()
        rows += [dict(r, source="comité") for r in s.to_dict("records")]
    desk_index = desk_index or ROOT / "docs" / "research" / "desk" / "README.md"
    if Path(desk_index).exists():
        text = Path(desk_index).read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        try:
            t = pd.to_datetime(first.split("—", 1)[1].replace("UTC", "").strip(), dayfirst=True).tz_localize(
                "UTC"
            )
        except (IndexError, ValueError):
            t = pd.NaT
        for line in text.splitlines():
            if line.startswith("| `"):
                cells = [c.strip() for c in line.strip("|").split("|")]
                agent = cells[0].strip("`")
                task = cells[1].split("](")[0].lstrip("[")
                rows.append(
                    {
                        "time": t,
                        "agent": agent,
                        "stage": "desk GitHub",
                        "status": "terminé",
                        "task": task,
                        "source": "desk",
                    }
                )
    log = read_log(desk=None)
    if not log.empty:
        todo = log[
            (log["status"] == "en cours")
            & (log["date"] >= (now - pd.Timedelta(days=1)).tz_localize(None).normalize())
        ]
        rows += [
            {
                "time": pd.Timestamp(r["date"]).tz_localize("UTC"),
                "agent": r["agent"],
                "stage": "prochain comité",
                "status": "à faire",
                "task": r["task"],
                "source": "comité",
            }
            for _, r in todo.iterrows()
            if not any(
                x["agent"] == r["agent"] and x["source"] == "comité" and x["status"] != "à faire"
                for x in rows
            )
        ]
    df = pd.DataFrame(rows, columns=[*STATUS_COLUMNS, "source"])
    return df.sort_values("time", ascending=False, na_position="last")
