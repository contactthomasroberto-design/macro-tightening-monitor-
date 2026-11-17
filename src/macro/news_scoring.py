"""Scoring headlines: sentiment, relevance, novelty, source credibility and freshness.

Each tagged headline gets
    sentiment  s ∈ [-1, 1]   FinBERT P(positive) − P(negative) (scored in GitHub Actions; the app
                             reads the archive, it does not load the model);
    relevance  r ∈ (0, 1]    1 for the company itself, 0.6 for its sector, 0.3 for the market;
    novelty    n ∈ (0, 1]    1 / (1 + number of similar earlier headlines in the last 72 hours);
    credibility c            by source (config/news.yaml);
    freshness  d = 2^(−age / half-life), half-life 24 hours.
An asset's news score is the weighted mean of s with weights r² n² c d (squared relevance and
novelty as in commercial news analytics), and its attention is the sum of the weights.

Every scored headline is appended to archive/news_scored.csv when it is first seen: a point-in-time
record that the news signal can later be tested on without hindsight."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from macro.config import ROOT

ARCHIVE = ROOT / "archive" / "news_scored.csv"
COLUMNS = ["first_seen", "published", "source", "title", "link", "tags", "sentiment", "novelty"]
_TOKEN = re.compile(r"[a-z0-9]+")
STOP = {
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "for",
    "and",
    "as",
    "at",
    "by",
    "with",
    "is",
    "its",
    "after",
}


def tokens(title: str) -> set[str]:
    t = re.sub(r"\s+-\s+[^-]+$", "", title.lower())  # drop the " - Publisher" suffix of Google News
    return {w for w in _TOKEN.findall(t) if w not in STOP}


def novelty(
    titles: Sequence[str], times: Sequence[pd.Timestamp], threshold: float, window_hours: int = 72
) -> np.ndarray:
    """1 / (1 + number of earlier headlines in the window with token Jaccard similarity ≥ threshold)."""
    toks = [tokens(t) for t in titles]
    order = np.argsort(
        pd.to_datetime(pd.Series(times), utc=True).fillna(pd.Timestamp.max.tz_localize("UTC")).to_numpy()
    )
    out = np.ones(len(titles))
    seen: list[int] = []
    tt = pd.to_datetime(pd.Series(times), utc=True)
    for i in order:
        k = 0
        for j in seen:
            if pd.notna(tt[i]) and pd.notna(tt[j]) and (tt[i] - tt[j]) > pd.Timedelta(hours=window_hours):
                continue
            a, b = toks[i], toks[j]
            if a and b and len(a & b) / len(a | b) >= threshold:
                k += 1
        out[i] = 1 / (1 + k)
        seen.append(i)
    return out


def score(df: pd.DataFrame, sentiment_fn: Callable[[list[str]], np.ndarray], cfg: dict) -> pd.DataFrame:
    """Add sentiment and novelty to tagged headlines (columns title, published, source, tags)."""
    d = df[df["tags"].map(bool)].copy()
    if d.empty:
        return d.assign(sentiment=pd.Series(dtype=float), novelty=pd.Series(dtype=float))
    d["sentiment"] = sentiment_fn(d["title"].tolist())
    d["novelty"] = novelty(d["title"].tolist(), d["published"].tolist(), cfg["scoring"]["novelty_jaccard"])
    return d


def finbert() -> Callable[[list[str]], np.ndarray]:
    """FinBERT sentiment (ProsusAI/finbert): P(positive) − P(negative) per headline. Loaded only in the
    GitHub workflow (needs torch and transformers, requirements-news.txt)."""
    from transformers import pipeline

    clf: Any = pipeline("text-classification", model="ProsusAI/finbert", top_k=None)

    def fn(titles: list[str]) -> np.ndarray:
        out = []
        for res in clf(titles, batch_size=32, truncation=True):
            p = {r["label"]: r["score"] for r in res}
            out.append(p.get("positive", 0.0) - p.get("negative", 0.0))
        return np.array(out)

    return fn


def asset_scores(scored: pd.DataFrame, cfg: dict, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """Per asset: weighted sentiment, attention (sum of weights) and headline count, at `now`."""
    sc = cfg["scoring"]
    now = now or pd.Timestamp.now(tz="UTC")
    if scored.empty:
        return pd.DataFrame(columns=["news score", "attention", "headlines"])
    pub = pd.to_datetime(scored["published"], utc=True).fillna(
        pd.to_datetime(scored.get("first_seen"), utc=True)
    )
    age_h = ((now - pub).dt.total_seconds() / 3600).clip(lower=0)
    fresh = 0.5 ** (age_h / sc["half_life_hours"])
    cred = scored["source"].map(lambda s: sc["credibility"].get(s, sc["credibility"]["other"]))
    rows = []
    for i, r in scored.iterrows():
        best: dict[str, float] = {}
        for t in r["tags"]:
            ent = sc["entities"].get(t)
            if not ent:
                continue
            for a in ent["assets"]:
                best[a] = max(best.get(a, 0.0), float(ent["relevance"]))
        for a, rel in best.items():
            w = rel**2 * r["novelty"] ** 2 * cred[i] * fresh[i]
            rows.append({"asset": a, "w": w, "ws": w * r["sentiment"]})
    if not rows:
        return pd.DataFrame(columns=["news score", "attention", "headlines"])
    g = pd.DataFrame(rows).groupby("asset")
    out = pd.DataFrame(
        {"news score": g["ws"].sum() / g["w"].sum(), "attention": g["w"].sum(), "headlines": g.size()}
    )
    return out.sort_values("attention", ascending=False)


def impact(scored: pd.DataFrame, cfg: dict, now: pd.Timestamp | None = None) -> pd.Series:
    """Headline-level impact for ranking: max relevance × |sentiment| × novelty × credibility × freshness."""
    sc = cfg["scoring"]
    now = now or pd.Timestamp.now(tz="UTC")
    pub = pd.to_datetime(scored["published"], utc=True)
    fresh = 0.5 ** (((now - pub).dt.total_seconds() / 3600).clip(lower=0).fillna(0) / sc["half_life_hours"])
    rel = scored["tags"].map(
        lambda ts: max([sc["entities"].get(t, {}).get("relevance", 0.1) for t in ts] or [0.1])
    )
    cred = scored["source"].map(lambda s: sc["credibility"].get(s, sc["credibility"]["other"]))
    return rel * scored["sentiment"].abs() * scored["novelty"] * cred * fresh


# ------------------------------------------------------------------ archive
def read_archive(path: Path = ARCHIVE) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path)
    df["tags"] = df["tags"].fillna("").map(lambda s: [t for t in s.split("|") if t])
    for c in ("first_seen", "published"):
        df[c] = pd.to_datetime(df[c], utc=True, errors="coerce")
    return df


def append_archive(scored: pd.DataFrame, path: Path = ARCHIVE, now: pd.Timestamp | None = None) -> int:
    """Append headlines not archived yet (by title). Returns the number of new rows."""
    old = read_archive(path)
    new = scored[~scored["title"].isin(set(old["title"]))].copy()
    if new.empty:
        return 0
    new["first_seen"] = (now or pd.Timestamp.now(tz="UTC")).floor("min")
    new["tags"] = new["tags"].map("|".join)
    new["sentiment"] = new["sentiment"].round(4)
    new["novelty"] = new["novelty"].round(4)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    new[COLUMNS].to_csv(path, mode="a", header=not Path(path).exists(), index=False)
    return len(new)


def daily_index(archive: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Daily per-asset news score from the archive, each day scored as of its end (point in time)."""
    if archive.empty:
        return pd.DataFrame()
    a = archive.copy()
    a["published"] = a["published"].fillna(a["first_seen"])
    days = pd.date_range(
        a["first_seen"].min().normalize(), a["first_seen"].max().normalize(), freq="D", tz="UTC"
    )
    out = {}
    for d in days:
        end = d + pd.Timedelta(days=1)
        known = a[(a["first_seen"] < end) & (a["published"] >= end - pd.Timedelta(days=3))]
        s = asset_scores(known, cfg, now=end)
        out[d.tz_localize(None)] = s["news score"]
    return pd.DataFrame(out).T
