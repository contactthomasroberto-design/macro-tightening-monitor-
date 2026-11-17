"""Research tracker: the latest published views of banks, asset managers and hedge funds.

Collects headlines from Google News search feeds per institution (config/research_feeds.yaml),
keeps the headline, date and link, and extracts a stance per instrument when the wording is explicit
("Goldman upgrades Japanese stocks to overweight" → EWJ +1). Ambiguous headlines get no stance.
Appended to archive/research_tracker.csv (point in time) and compared with the model on the Research
page; the nightly research run turns the substantive ones into dated entries of config/house_views.yaml."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

import pandas as pd
import yaml

from macro import news
from macro.config import ROOT
from macro.data.http import get

PATH = ROOT / "config" / "research_feeds.yaml"
ARCHIVE = ROOT / "archive" / "research_tracker.csv"
GOOGLE = "https://news.google.com/rss/search?q={q}+when:3d&hl=en-US&gl=US&ceid=US:en"

POSITIVE = (
    r"\b(overweight|upgrade[sd]?|favou?rs?|prefers?|bullish|buy|raise[sd]? .{0,30}target|positive on)\b"
)
NEGATIVE = r"\b(underweight|downgrade[sd]?|bearish|sell rating|cuts? .{0,30}target|negative on|trims?)\b"


def load(path=PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def stances(title: str, assets: dict[str, list[str]]) -> dict[str, int]:
    """Stance per instrument for explicit wording in the same clause; {} when ambiguous."""
    out: dict[str, int] = {}
    for clause in re.split(r"[;,:]| but | while ", title, flags=re.I):
        pos = re.search(POSITIVE, clause, re.I) is not None
        neg = re.search(NEGATIVE, clause, re.I) is not None
        if pos == neg:  # neither, or both (ambiguous)
            continue
        for a, words in assets.items():
            if re.search(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", clause, re.I):
                out[a] = 1 if pos else -1
    return out


def collect(cfg: dict | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    cfg = cfg or load()
    frames, failed = [], {}
    for inst, q in cfg["institutions"].items():
        url = GOOGLE.format(q=urllib.parse.quote_plus(q))
        try:
            df = news.parse_rss(get(url).content, inst)
        except Exception as exc:  # noqa: BLE001 - one failed feed must not stop the others
            failed[inst] = str(exc)[:100]
            continue
        frames.append(df.rename(columns={"source": "institution"}))
    if not frames:
        return pd.DataFrame(columns=["title", "link", "published", "institution", "stances"]), failed
    df = pd.concat(frames, ignore_index=True).drop_duplicates("title")
    df["stances"] = df["title"].map(lambda t: stances(t, cfg["assets"]))
    return df.sort_values("published", ascending=False).reset_index(drop=True), failed


def publications(cfg: dict | None = None, max_age_days: int = 7) -> tuple[pd.DataFrame, dict[str, str]]:
    """Latest items of the official research feeds (central banks, academic, asset managers, quant)."""
    cfg = cfg or load()
    frames, failed = [], {}
    for f in cfg.get("publications", []):
        try:
            df = news.parse_rss(get(f["url"]).content, f["name"])
        except Exception as exc:  # noqa: BLE001 - one failed feed must not stop the others
            failed[f["name"]] = str(exc)[:100]
            continue
        frames.append(df.rename(columns={"source": "institution"}).assign(kind=f["kind"]))
    if not frames:
        return pd.DataFrame(columns=["title", "link", "published", "institution", "kind"]), failed
    df = pd.concat(frames, ignore_index=True).drop_duplicates("title")
    cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=max_age_days)
    df = df[df["published"].isna() | (df["published"] >= cut)]
    return df.sort_values("published", ascending=False).reset_index(drop=True), failed


def append_archive(df: pd.DataFrame, path: Path = ARCHIVE) -> int:
    old = pd.read_csv(path) if Path(path).exists() else pd.DataFrame(columns=["title"])
    new = df[~df["title"].isin(set(old["title"]))].copy()
    if new.empty:
        return 0
    new["first_seen"] = pd.Timestamp.now(tz="UTC").floor("min")
    new["stances"] = new["stances"].map(lambda d: ";".join(f"{k}:{v:+d}" for k, v in d.items()))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cols = ["first_seen", "published", "institution", "title", "link", "stances"]
    new[cols].to_csv(path, mode="a", header=not Path(path).exists(), index=False)
    return len(new)


def read_archive(path: Path = ARCHIVE) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=["first_seen", "published", "institution", "title", "link", "stances"])
    df = pd.read_csv(path)
    df["stances"] = (
        df["stances"]
        .fillna("")
        .map(lambda s: {k: int(v) for k, v in (x.split(":") for x in s.split(";") if x)})
    )
    for c in ("first_seen", "published"):
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    return df


def consensus(df: pd.DataFrame, days: int = 30) -> pd.DataFrame:
    """Per instrument: net stance and count over the last `days` days."""
    cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    when = df["published"].fillna(df["first_seen"]) if "first_seen" in df else df["published"]
    d = df[when >= cut]
    rows = [(a, v, r["institution"]) for _, r in d.iterrows() for a, v in r["stances"].items()]
    if not rows:
        return pd.DataFrame(columns=["net stance", "mentions", "institutions"])
    x = pd.DataFrame(rows, columns=["asset", "stance", "institution"])
    g = x.groupby("asset")
    return pd.DataFrame(
        {
            "net stance": g["stance"].mean(),
            "mentions": g.size(),
            "institutions": g["institution"].agg(lambda s: ", ".join(sorted(set(s)))),
        }
    ).sort_values("mentions", ascending=False)
