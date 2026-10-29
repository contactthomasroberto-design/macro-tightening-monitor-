"""Warm start for the hosted dashboard: a daily snapshot of the live data cache and model results.

Streamlit Community Cloud keeps nothing between restarts, so every restart used to re-download every
series and recompute every model (several minutes). The `refresh` workflow now writes a snapshot
after its live run (`scripts/export_snapshot.py`) and commits it under `snapshot/live/`:

- `data.parquet`: latest-vintage observations with their source and fetch time (~2 MB)
- `results.tar.xz`: the result cache (one pickle per model bundle)
- `gmd.parquet`: the Global Macro Database extract used by the Historical cycles page
- `manifest.json`: creation time, git hash and the store data version the results were computed on

On start-up in live mode the app restores whatever is missing locally. Results are validated against
the content hashes of the series they read, so a result computed by GitHub Actions from the same data
is valid here and loads instantly; the background refresh then polls for new releases and recomputes
only the results whose inputs changed.

The repository must stay private: the snapshot contains copies of third-party data.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pickle
import shutil
import tarfile
import threading
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


_LOCK = threading.Lock()


def _marker() -> Path:
    return ROOT / "data" / "cache" / "snapshot_applied.json"


def _keep_local(target: Path, snap_bytes: bytes) -> bool:
    """Keep the local result rather than the snapshot's when it is still valid for the local data, or
    when it was computed by the running code more recently than the snapshot's (the dashboard
    recomputes light models after a release; the snapshot may predate that release)."""
    from macro import results

    name = target.stem.replace("__", ":")
    if results.is_valid(name, target):
        return True
    local = results.read_meta(target)
    if local.get("code") != results.code_hash():
        return False
    try:
        snap = pickle.loads(snap_bytes)
        snap_meta = snap[2] if len(snap) > 2 else {}
    except Exception:
        return True
    return str(local.get("computed", "")) > str(snap_meta.get("computed", ""))


def apply_snapshot(src: Path = SNAPSHOT_DIR) -> dict:
    """Bring the local cache up to the snapshot in the repository (live mode). Cheap when the snapshot
    was already applied: called on every app run, because Streamlit Community Cloud pulls a new
    commit (and so a new snapshot) without restarting the process. Never raises.

    - data: a series is written when the snapshot holds a newer fetch than the local cache; if the
      local cache holds nothing newer, the store takes the snapshot's data version, so the snapshot's
      results match their fingerprints exactly;
    - results: a local result is replaced unless it is still valid for the local data, or was computed
      by the running code after the snapshot's;
    - GMD extract: copied when missing.
    """
    if mode() != "live" or not (src / "manifest.json").exists():
        return {"applied": False, "reason": "no snapshot or not live mode"}
    try:
        manifest = json.loads((src / "manifest.json").read_text())
        marker = _marker()
        if marker.exists() and json.loads(marker.read_text()).get("created") == manifest.get("created"):
            return {"applied": False, "reason": "already applied"}
        with _LOCK:
            return _apply(src, manifest, marker)
    except Exception as exc:  # a bad snapshot must never stop the app: it then computes from scratch
        log.warning("warm start failed: %s", exc)
        return {"applied": False, "reason": str(exc)}


def _apply(src: Path, manifest: dict, marker: Path) -> dict:
    from macro.data import store

    done: list[str] = []
    st = store()
    if (src / "data.parquet").exists():
        df = pd.read_parquet(src / "data.parquet")
        local_newer = 0
        written = 0
        for sid, g in df.groupby("series_id", observed=True):
            snap_fetched = str(g["fetched_at"].astype(str).max())
            lf = st.last_fetched(str(sid))
            if lf is not None and lf.strftime("%Y-%m-%dT%H:%M:%S") >= snap_fetched:
                local_newer += 1
                continue
            rows = pd.DataFrame(
                {"date": pd.to_datetime(g["date"]).to_numpy(), "value": g["value"].to_numpy(float)}
            )
            rows["vintage_date"] = pd.NaT
            st.write(str(sid), rows, source=str(g["source"].iloc[-1]), fetched_at=snap_fetched)
            written += 1
        if local_newer == 0:
            st.set_data_version(int(manifest["data_version"]))
        if written:
            done.append(f"data ({written} series)")
    res = _results_dir()
    res.mkdir(parents=True, exist_ok=True)
    if (src / "results.tar.xz").exists():
        n = 0
        with tarfile.open(src / "results.tar.xz", "r:xz") as tar:
            for m in tar.getmembers():
                if not (m.isfile() and m.name.endswith(".pkl") and "/" not in m.name):
                    continue
                target = res / m.name
                data = tar.extractfile(m)
                if data is None:
                    continue
                payload = data.read()
                if target.exists() and _keep_local(target, payload):
                    continue
                tmp = target.with_suffix(".tmp")
                tmp.write_bytes(payload)
                tmp.replace(target)
                n += 1
        if n:
            done.append(f"results ({n})")
    gdir = _gmd_dir()
    if (src / "gmd.parquet").exists() and manifest.get("gmd_version") and not any(gdir.glob("GMD_*.parquet")):
        gdir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / "gmd.parquet", gdir / f"GMD_{manifest['gmd_version']}.parquet")
        done.append("gmd")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"created": manifest.get("created"), "applied": done}))
    log.info("warm start from snapshot %s: %s", manifest.get("created"), done or "nothing to update")
    return {"applied": bool(done), "parts": done, "snapshot": manifest.get("created")}


restore_if_empty = apply_snapshot  # backwards-compatible name
