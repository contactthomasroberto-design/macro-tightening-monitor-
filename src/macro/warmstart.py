"""Warm start for the hosted dashboard: a daily snapshot of the live data cache and model results.

Streamlit Community Cloud keeps nothing between restarts, so every restart used to re-download every
series and recompute every model (several minutes). The `refresh` workflow now writes a snapshot
after its live run (`scripts/export_snapshot.py`) and commits it under `snapshot/live/`:

- `data.parquet`: latest-vintage observations with their source and fetch time (~2 MB)
- `results.tar.xz`: the result cache (one pickle per model bundle)
- `gmd.parquet`: the Global Macro Database extract used by the Historical cycles page
- `manifest.json`: creation time, git hash and the store data version the results were computed on

On start-up in live mode the app restores whatever is missing locally. The store's data version is
set to the snapshot's, so the results match their fingerprints and load instantly; the background
refresh then updates expired series and recomputes only what changed.

The repository must stay private: the snapshot contains copies of third-party data.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import shutil
import tarfile
from pathlib import Path

import pandas as pd

from macro.config import ROOT
from macro.utils import git_hash, mode

log = logging.getLogger("macro.warmstart")
SNAPSHOT_DIR = ROOT / "snapshot" / "live"


def _results_dir() -> Path:
    return ROOT / "data" / "cache" / "results" / "live"


def _gmd_dir() -> Path:
    from macro.data import gmd

    return gmd.CACHE_DIR


def export(out: Path = SNAPSHOT_DIR) -> dict:
    """Write the snapshot of the live cache (run after `scripts/run_all.py` in live mode)."""
    from macro.data import store

    if mode() != "live":
        raise RuntimeError("the snapshot is built from live data only (MACRO_MODE=live)")
    out.mkdir(parents=True, exist_ok=True)
    st = store()
    df = st.latest_frame()
    df["date"] = pd.to_datetime(df["date"])
    for c in ("series_id", "source", "fetched_at"):
        df[c] = df[c].astype("category")
    df.to_parquet(out / "data.parquet", compression="zstd", compression_level=19, index=False)
    res = _results_dir()
    with tarfile.open(out / "results.tar.xz", "w:xz") as tar:
        for f in sorted(res.glob("*.pkl")):
            tar.add(f, arcname=f.name)
    gmd_files = sorted(_gmd_dir().glob("GMD_*.parquet"))
    if gmd_files:
        shutil.copyfile(gmd_files[-1], out / "gmd.parquet")
        gmd_version = gmd_files[-1].stem.removeprefix("GMD_")
    else:
        gmd_version = None
    manifest = {
        "created": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_hash": git_hash(),
        "data_version": st.data_version(),
        "series": int(df["series_id"].nunique()),
        "observations": len(df),
        "results": len(list(res.glob("*.pkl"))),
        "gmd_version": gmd_version,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def restore_if_empty(src: Path = SNAPSHOT_DIR) -> dict:
    """Restore the snapshot pieces that are missing locally (live mode only). Never raises."""
    if mode() != "live" or not (src / "manifest.json").exists():
        return {"restored": False, "reason": "no snapshot or not live mode"}
    try:
        from macro.data import store

        manifest = json.loads((src / "manifest.json").read_text())
        done: list[str] = []
        st = store()
        if st.is_empty() and (src / "data.parquet").exists():
            df = pd.read_parquet(src / "data.parquet")
            for sid, g in df.groupby("series_id", observed=True):
                rows = pd.DataFrame(
                    {"date": pd.to_datetime(g["date"]).to_numpy(), "value": g["value"].to_numpy(float)}
                )
                rows["vintage_date"] = pd.NaT
                st.write(
                    str(sid),
                    rows,
                    source=str(g["source"].iloc[-1]),
                    fetched_at=str(g["fetched_at"].astype(str).max()),
                )
            st.set_data_version(int(manifest["data_version"]))
            done.append("data")
        res = _results_dir()
        res.mkdir(parents=True, exist_ok=True)
        if not any(res.glob("*.pkl")) and (src / "results.tar.xz").exists():
            with tarfile.open(src / "results.tar.xz", "r:xz") as tar:
                for m in tar.getmembers():
                    if m.isfile() and m.name.endswith(".pkl") and "/" not in m.name:
                        data = tar.extractfile(m)
                        if data is not None:
                            (res / m.name).write_bytes(io.BytesIO(data.read()).getvalue())
            done.append("results")
        gdir = _gmd_dir()
        if (
            (src / "gmd.parquet").exists()
            and manifest.get("gmd_version")
            and not any(gdir.glob("GMD_*.parquet"))
        ):
            gdir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src / "gmd.parquet", gdir / f"GMD_{manifest['gmd_version']}.parquet")
            done.append("gmd")
        log.info("warm start from snapshot %s: %s", manifest.get("created"), done or "nothing missing")
        return {"restored": bool(done), "parts": done, "snapshot": manifest.get("created")}
    except Exception as exc:  # a bad snapshot must never stop the app: it then computes from scratch
        log.warning("warm start failed: %s", exc)
        return {"restored": False, "reason": str(exc)}
