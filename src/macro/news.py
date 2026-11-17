"""Headline feed for the Portfolio → News tab (config/news.yaml).

Reads public RSS feeds, keeps the headline, time, source and link, and tags each headline with the
holdings and macro themes it mentions. Display only: headlines are not scored and do not enter the
allocation (the quantitative news input is the GDELT tone, research log H30)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd
import yaml

from macro.config import ROOT
from macro.data.http import SourceError, get

PATH = ROOT / "config" / "news.yaml"


def load(path=PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def parse_rss(xml: bytes | str, source: str) -> pd.DataFrame:
    """Items of an RSS 2.0 or Atom feed: title, link, published (UTC), source."""
    root = ET.fromstring(xml)
    rows = []
    atom = "{http://www.w3.org/2005/Atom}"
    for it in root.iter("item"):
        rows.append(
            {
                "title": (it.findtext("title") or "").strip(),
                "link": (it.findtext("link") or "").strip(),
                "published": it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date"),
            }
        )
    for it in root.iter(f"{atom}entry"):
        ln = it.find(f"{atom}link")
        rows.append(
            {
                "title": (it.findtext(f"{atom}title") or "").strip(),
                "link": ln.get("href", "") if ln is not None else "",
                "published": it.findtext(f"{atom}updated") or it.findtext(f"{atom}published"),
            }
        )
    df = pd.DataFrame(rows, columns=["title", "link", "published"])

    def when(s):
        if not s:
            return pd.NaT
        try:
            return pd.Timestamp(parsedate_to_datetime(s)).tz_convert("UTC")
        except (TypeError, ValueError):
            t = pd.to_datetime(s, utc=True, errors="coerce")
            return t

    df["published"] = df["published"].map(when)
    df["source"] = source
    return df[df["title"] != ""]


def tag(titles: pd.Series, tags: dict[str, list[str]]) -> pd.Series:
    pats = {k: re.compile(r"\b(" + "|".join(re.escape(w) for w in v) + r")\b", re.I) for k, v in tags.items()}
    return titles.map(lambda t: [k for k, p in pats.items() if p.search(t)])


def headlines(cfg: dict | None = None, max_age_hours: int = 72) -> tuple[pd.DataFrame, dict[str, str]]:
    """All feeds, newest first, de-duplicated on the title; plus the feeds that failed."""
    cfg = cfg or load()
    frames, failed = [], {}
    for f in cfg["feeds"]:
        try:
            frames.append(parse_rss(get(f["url"]).content, f["name"]))
        except (SourceError, ET.ParseError) as exc:
            failed[f["name"]] = str(exc)[:120]
    if not frames:
        return pd.DataFrame(columns=["title", "link", "published", "source", "tags"]), failed
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates("title")
    cut = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=max_age_hours)
    df = df[df["published"].isna() | (df["published"] >= cut)]
    df["tags"] = tag(df["title"], cfg["tags"])
    return df.sort_values("published", ascending=False, na_position="last").reset_index(drop=True), failed
