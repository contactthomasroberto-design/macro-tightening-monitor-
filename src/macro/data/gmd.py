"""Global Macro Database (Müller, Xu, Lehbib and Chen, 2025): annual country panel, 1086 to the
latest release, 240 countries, harmonised from about a hundred sources.

Licence: free for academic use; other uses need written permission from the authors
(https://www.globalmacrodata.com/license.html). The project only downloads it on the user's machine
and never commits it. The latest release includes projections for recent and future years (IMF WEO
based); `last_actual_year()` separates them from realised data.

Loaded as a whole panel (country x year), not through `get_series`: it is used for long-history
cross-country statistics (the Historical cycles page), never as an input to the monthly models.
"""

from __future__ import annotations

import datetime as dt
import io
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from macro.config import ROOT
from macro.data.http import SourceError, get
from macro.utils import is_demo

log = logging.getLogger("macro.data")

GMD_BASE = "https://gmd-releases.s3.ap-southeast-2.amazonaws.com/data"
GMD_MIRROR = "https://raw.githubusercontent.com/KMueller-Lab/Global-Macro-Database/refs/heads/main/data"
CACHE_DIR = ROOT / "data" / "cache" / "gmd"
TTL_DAYS = 30  # releases are quarterly
COLUMNS = [
    "ISO3",
    "countryname",
    "year",
    "cbrate",
    "strate",
    "ltrate",
    "infl",
    "rGDP",
    "unemp",
    "BankingCrisis",
    "CurrencyCrisis",
    "SovDebtCrisis",
]
CITATION = (
    "Müller, K., Xu, C., Lehbib, M. and Chen, Z. (2025), The Global Macro Database: A New International "
    "Macroeconomic Dataset, NBER Working Paper 33714. www.globalmacrodata.com"
)
LICENCE = "Global Macro Database: free for academic use; other uses need written permission from the authors."


def _get(path: str):
    try:
        return get(f"{GMD_BASE}/{path}")
    except SourceError as exc:
        log.warning("GMD primary host failed (%s); trying the GitHub mirror", exc)
        return get(f"{GMD_MIRROR}/{path}")


def latest_version() -> str:
    """Latest release tag, e.g. '2026_09' (from helpers/versions.csv)."""
    v = pd.read_csv(io.StringIO(_get("helpers/versions.csv").text))
    tags = v["versions"].astype(str)
    return str(sorted(tags, key=lambda t: tuple(int(x) for x in t.split("_")))[-1])


def _cached() -> list[Path]:
    return sorted(CACHE_DIR.glob("GMD_*.parquet"))


def _fresh(path: Path) -> bool:
    age = dt.datetime.now() - dt.datetime.fromtimestamp(path.stat().st_mtime)
    return age.days < TTL_DAYS


def load_panel(refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """(panel, version). Demo mode returns a synthetic panel. Live: cached parquet if younger than
    TTL_DAYS, otherwise the latest release is downloaded; on failure the last cached release is used."""
    if is_demo():
        return demo_panel(), "SYNTHETIC"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = _cached()
    if cached and not refresh and _fresh(cached[-1]):
        return pd.read_parquet(cached[-1]), cached[-1].stem.removeprefix("GMD_")
    try:
        ver = latest_version()
        target = CACHE_DIR / f"GMD_{ver}.parquet"
        if not target.exists():
            raw = pd.read_stata(
                io.BytesIO(_get(f"distribute/GMD_{ver}.dta").content), convert_categoricals=False
            )
            df = raw[[c for c in COLUMNS if c in raw.columns]].copy()
            df["year"] = df["year"].astype(int)
            df.to_parquet(target, index=False)
        else:
            target.touch()
        return pd.read_parquet(target), ver
    except (SourceError, ValueError, KeyError) as exc:
        if cached:
            log.warning("GMD download failed (%s); using cached %s", exc, cached[-1].name)
            return pd.read_parquet(cached[-1]), cached[-1].stem.removeprefix("GMD_")
        raise


def last_actual_year(today: dt.date | None = None) -> int:
    """Annual data for the current year is a projection until the year is over."""
    today = today or dt.date.today()
    return today.year - 1


def demo_panel(seed: int = 7) -> pd.DataFrame:
    """Synthetic country-year panel with tightening cycles, recessions and crises (SYNTHETIC)."""
    g = np.random.default_rng(seed)
    rows = []
    countries = [("USA", "United States"), ("DEU", "Germany"), ("JPN", "Japan"), ("GBR", "United Kingdom")]
    countries += [(f"C{k:02d}", f"Synthetic country {k}") for k in range(1, 17)]
    years = np.arange(1900, 2028)
    for iso, name in countries:
        rate, infl, gdp = 4.0, 2.5, 100.0
        for y in years:
            infl = 0.75 * infl + 0.6 + g.normal(0, 1.6)
            rate = max(0.0, rate + 0.45 * (infl - rate + 1.0) + g.normal(0, 0.6))
            growth = 2.5 - 0.35 * max(0.0, rate - infl - 1.5) + g.normal(0, 2.2)
            gdp *= 1 + growth / 100
            crisis = float(g.random() < 0.02 + 0.03 * (growth < -1))
            rows.append(
                {
                    "ISO3": iso,
                    "countryname": name,
                    "year": int(y),
                    "cbrate": round(rate, 3),
                    "strate": round(rate + 0.2, 3),
                    "ltrate": round(rate + 1.2, 3),
                    "infl": infl,
                    "rGDP": gdp,
                    "unemp": max(1.0, 6 - 0.4 * growth + g.normal(0, 0.5)),
                    "BankingCrisis": crisis,
                    "CurrencyCrisis": float(g.random() < 0.02),
                    "SovDebtCrisis": float(g.random() < 0.01),
                }
            )
    return pd.DataFrame(rows)
