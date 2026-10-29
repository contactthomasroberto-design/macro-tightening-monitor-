"""SQLite cache for observations, with vintages and a fetch log.

Schema
------
observations(series_id, date, value, vintage_date, source, fetched_at)
    vintage_date = '' for latest-vintage pulls (FRED csv, ECB, Yahoo, ...);
    a real date for ALFRED vintages. One latest-vintage snapshot is kept per series
    (replaced on refresh); ALFRED vintages are appended.
fetch_log(series_id, fetched_at, ok, message)
series_state(series_id, content_hash, last_date, changed_at)
    hash of the latest-vintage content: model results are validated against the hashes of the
    series they read (macro.results), so identical data gives identical keys on any machine.
releases(series_id, obs_date, value, detected_at)
    a new last observation found by a refresh (the dashboard's "new release" banner).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from macro.config import ROOT

# Time-to-live of a latest-vintage pull, by frequency.
TTL = {
    "D": dt.timedelta(hours=12),
    "W": dt.timedelta(days=2),
    "M": dt.timedelta(days=3),
    "Q": dt.timedelta(days=7),
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    series_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL,
    vintage_date TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (series_id, date, vintage_date)
);
CREATE INDEX IF NOT EXISTS ix_obs_series ON observations(series_id, vintage_date);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS series_state (
    series_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    last_date TEXT,
    changed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS releases (
    series_id TEXT NOT NULL,
    obs_date TEXT NOT NULL,
    value REAL,
    detected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fetch_log (
    series_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    ok INTEGER NOT NULL,
    message TEXT
);
"""


def default_path() -> Path:
    env = os.environ.get("MACRO_DB")
    if env:
        return Path(env)
    mode = os.environ.get("MACRO_MODE", "demo").lower()
    return ROOT / "data" / "cache" / f"macro_{mode}.sqlite"


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S")


def _content_hash(rows) -> str:
    """Hash of sorted (date, value) pairs; NaN and NULL hash alike (SQLite stores NaN as NULL)."""
    h = hashlib.sha1()
    for d, v in rows:
        h.update(f"{d}|{'nan' if v is None or v != v else repr(float(v))}\n".encode())
    return h.hexdigest()[:16]


class Store:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=60)  # the dashboard refreshes in a background thread
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ writes
    def write(self, series_id: str, df: pd.DataFrame, source: str, fetched_at: str | None = None) -> int:
        """Write tidy rows (date, value, vintage_date). Latest-vintage rows replace the previous snapshot."""
        fetched_at = fetched_at or _now()
        vint = df["vintage_date"].map(lambda v: "" if pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d"))
        rows = list(
            zip(
                [series_id] * len(df),
                df["date"].dt.strftime("%Y-%m-%d"),
                df["value"].astype(float),
                vint,
                [source] * len(df),
                [fetched_at] * len(df),
                strict=True,
            )
        )
        with self._conn() as c:
            latest = (vint == "").all()
            if latest:
                old = c.execute(
                    "SELECT date, value FROM observations WHERE series_id=? AND vintage_date='' ORDER BY date",
                    (series_id,),
                ).fetchall()
                new = sorted((r[1], r[2]) for r in rows)
                if len(old) == len(new) and all(
                    a[0] == b[0] and (a[1] == b[1] or (a[1] != a[1] and b[1] != b[1]))
                    for a, b in zip(old, new, strict=True)
                ):
                    # unchanged content: only record that it was checked (no new data version)
                    c.execute(
                        "UPDATE observations SET fetched_at=?, source=? WHERE series_id=? AND vintage_date=''",
                        (fetched_at, source, series_id),
                    )
                    return len(rows)
            if (vint == "").any():
                c.execute("DELETE FROM observations WHERE series_id=? AND vintage_date=''", (series_id,))
            c.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?,?)", rows)
            if latest and rows:
                now = _now()
                c.execute(
                    "INSERT OR REPLACE INTO series_state VALUES (?,?,?,?)",
                    (series_id, _content_hash(new), new[-1][0], now),
                )
                if old and new[-1][0] > old[-1][0]:  # a new observation, not just a revision
                    c.execute(
                        "INSERT INTO releases VALUES (?,?,?,?)", (series_id, new[-1][0], new[-1][1], now)
                    )
            c.execute(
                "INSERT INTO meta VALUES ('data_version', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = CAST(value AS INTEGER) + 1"
            )
        return len(rows)

    def set_data_version(self, version: int) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO meta VALUES ('data_version', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(int(version)),),
            )

    def latest_frame(self) -> pd.DataFrame:
        """All latest-vintage observations (series_id, date, value, source, fetched_at)."""
        with self._conn() as c:
            return pd.read_sql_query(
                "SELECT series_id, date, value, source, fetched_at FROM observations WHERE vintage_date=''", c
            )

    def is_empty(self) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM observations LIMIT 1").fetchone() is None

    def data_version(self) -> int:
        """Incremented whenever observations change (not when an unchanged series is re-checked):
        model results are cached against it."""
        with self._conn() as c:
            r = c.execute("SELECT value FROM meta WHERE key='data_version'").fetchone()
        return int(r[0]) if r else 0

    def log_fetch(self, series_id: str, ok: bool, message: str = "") -> None:
        with self._conn() as c:
            c.execute("INSERT INTO fetch_log VALUES (?,?,?,?)", (series_id, _now(), int(ok), message[:500]))

    # ------------------------------------------------------------------ reads
    def read(self, series_id: str, vintage: str | None = None) -> pd.Series:
        """Latest vintage, or the real-time view at `vintage`: for each date the value from the
        most recent ALFRED vintage on or before `vintage`."""
        with self._conn() as c:
            if vintage is None:
                q = "SELECT date, value FROM observations WHERE series_id=? AND vintage_date='' ORDER BY date"
                df = pd.read_sql_query(q, c, params=(series_id,))
            else:
                q = """
                SELECT o.date, o.value FROM observations o
                JOIN (SELECT date, MAX(vintage_date) AS v FROM observations
                      WHERE series_id=? AND vintage_date<>'' AND vintage_date<=? GROUP BY date) m
                  ON o.date=m.date AND o.vintage_date=m.v
                WHERE o.series_id=? ORDER BY o.date"""
                df = pd.read_sql_query(q, c, params=(series_id, vintage, series_id))
        s = pd.Series(df["value"].to_numpy(dtype=float), index=pd.to_datetime(df["date"]), name=series_id)
        s.index.name = "date"
        return s

    def last_fetched(self, series_id: str) -> dt.datetime | None:
        with self._conn() as c:
            r = c.execute(
                "SELECT MAX(fetched_at) FROM observations WHERE series_id=? AND vintage_date=''", (series_id,)
            ).fetchone()
        return dt.datetime.fromisoformat(r[0]).replace(tzinfo=dt.UTC) if r and r[0] else None

    def source_of(self, series_id: str) -> str | None:
        with self._conn() as c:
            r = c.execute(
                "SELECT source FROM observations WHERE series_id=? LIMIT 1", (series_id,)
            ).fetchone()
        return r[0] if r else None

    def vintages(self, series_id: str) -> list[str]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT DISTINCT vintage_date FROM observations WHERE series_id=? AND vintage_date<>'' ORDER BY 1",
                (series_id,),
            ).fetchall()
        return [r[0] for r in rows]

    def fetch_log(self, limit: int = 500) -> pd.DataFrame:
        with self._conn() as c:
            return pd.read_sql_query(
                "SELECT * FROM fetch_log ORDER BY fetched_at DESC LIMIT ?", c, params=(limit,)
            )

    def failed_recently(self, series_id: str, within: dt.timedelta, now: dt.datetime | None = None) -> bool:
        """True when the latest fetch attempt failed less than `within` ago (negative cache: a source
        that just refused is not asked again by every page that needs the series)."""
        with self._conn() as c:
            r = c.execute(
                "SELECT fetched_at, ok FROM fetch_log WHERE series_id=? ORDER BY rowid DESC LIMIT 1",
                (series_id,),
            ).fetchone()
        if not r or r[1]:
            return False
        t = dt.datetime.fromisoformat(r[0])
        t = t if t.tzinfo else t.replace(tzinfo=dt.UTC)
        return (now or dt.datetime.now(dt.UTC)) - t < within

    def last_failure(self, series_id: str) -> tuple[str, str] | None:
        with self._conn() as c:
            r = c.execute(
                "SELECT fetched_at, message, ok FROM fetch_log WHERE series_id=? ORDER BY rowid DESC LIMIT 1",
                (series_id,),
            ).fetchone()
        return (r[0], r[1]) if r and not r[2] else None

    def content_hashes(self, ids) -> dict[str, str]:
        """Latest-vintage content hash per series (computed and stored when missing)."""
        ids = sorted(set(ids))
        if not ids:
            return {}
        with self._conn() as c:
            q = f"SELECT series_id, content_hash FROM series_state WHERE series_id IN ({','.join('?' * len(ids))})"
            out = dict(c.execute(q, ids).fetchall())
            for sid in ids:
                if sid in out:
                    continue
                rows = c.execute(
                    "SELECT date, value FROM observations WHERE series_id=? AND vintage_date='' ORDER BY date",
                    (sid,),
                ).fetchall()
                out[sid] = _content_hash(rows) if rows else "missing"
                if rows:
                    c.execute(
                        "INSERT OR REPLACE INTO series_state VALUES (?,?,?,?)",
                        (sid, out[sid], rows[-1][0], _now()),
                    )
        return out

    def latest_state(self) -> dict[str, tuple[str, dt.datetime]]:
        """{series_id: (last observation date, last fetch time)} for every latest-vintage series."""
        with self._conn() as c:
            rows = c.execute(
                "SELECT series_id, MAX(date), MAX(fetched_at) FROM observations WHERE vintage_date='' GROUP BY series_id"
            ).fetchall()
        return {r[0]: (r[1], dt.datetime.fromisoformat(r[2]).replace(tzinfo=dt.UTC)) for r in rows}

    def recent_releases(self, since: dt.datetime) -> pd.DataFrame:
        """New observations detected by refreshes since `since` (most recent first)."""
        with self._conn() as c:
            return pd.read_sql_query(
                "SELECT series_id, obs_date, value, detected_at FROM releases WHERE detected_at>=? "
                "ORDER BY detected_at DESC",
                c,
                params=(since.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S"),),
            )

    def is_fresh(self, series_id: str, freq: str, now: dt.datetime | None = None) -> bool:
        lf = self.last_fetched(series_id)
        if lf is None:
            return False
        now = now or dt.datetime.now(dt.UTC)
        return now - lf < TTL[freq]
