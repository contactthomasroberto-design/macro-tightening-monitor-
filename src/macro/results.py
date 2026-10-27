"""Disk cache of heavy model results, so dashboard pages load in seconds (BRIEF §7).

`scripts/run_all.py` computes and stores every result; pages call `load_or_compute`, which
returns the stored object if it was computed from the current data cache and model version,
and computes it otherwise. Key = (name, mode, model version, data-cache modification time).
"""

from __future__ import annotations

import hashlib
import logging
import pickle
from collections.abc import Callable
from pathlib import Path
from typing import Any

from macro.config import ROOT
from macro.data.store import default_path
from macro.utils import mode
from macro.versions import MODEL_VERSIONS

log = logging.getLogger("macro.results")


def _dir() -> Path:
    d = ROOT / "data" / "cache" / "results" / mode()
    d.mkdir(parents=True, exist_ok=True)
    return d


_CODE_HASH: str | None = None


def code_hash() -> str:
    """Hash of the model package source: any code change invalidates cached results."""
    global _CODE_HASH
    if _CODE_HASH is None:
        h = hashlib.sha1()
        for f in sorted((ROOT / "src" / "macro").rglob("*.py")):
            h.update(f.read_bytes())
        _CODE_HASH = h.hexdigest()[:12]
    return _CODE_HASH


def _fingerprint(name: str) -> str:
    db = default_path()
    mtime = db.stat().st_mtime if db.exists() else 0
    version = MODEL_VERSIONS.get(name.split(":")[0], "0")
    return hashlib.sha1(f"{name}|{mode()}|{version}|{mtime}|{code_hash()}".encode()).hexdigest()[:16]


def load_or_compute(name: str, fn: Callable[[], Any], force: bool = False) -> Any:
    path = _dir() / f"{name.replace(':', '__')}.pkl"
    fp = _fingerprint(name)
    if path.exists() and not force:
        try:
            with open(path, "rb") as fh:
                stored_fp, obj = pickle.load(fh)
            if stored_fp == fp:
                return obj
        except (pickle.UnpicklingError, EOFError, AttributeError, ModuleNotFoundError) as exc:
            log.warning("discarding unreadable result cache %s: %s", path.name, exc)
    obj = fn()
    with open(path, "wb") as fh:
        pickle.dump((fp, obj), fh)
    return obj
