"""Disk cache of heavy model results, so dashboard pages load in seconds (BRIEF §7).

`scripts/run_all.py` computes and stores every result; pages call `load_or_compute`, which
returns the stored object if it was computed from the current data and model version, and
computes it otherwise. Key = (name, mode, model version, data version of the store, code hash).
"""

from __future__ import annotations

import hashlib
import logging
import pickle
import threading
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
    """Changes when the data content changes (store data version), the model version or the code."""
    from macro.data.store import Store

    db = default_path()
    data_v = Store(db).data_version() if db.exists() else 0
    version = MODEL_VERSIONS.get(name.split(":")[0], "0")
    return hashlib.sha1(f"{name}|{mode()}|{version}|{data_v}|{code_hash()}".encode()).hexdigest()[:16]


_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock(name: str) -> threading.RLock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(name, threading.RLock())


def load_or_compute(name: str, fn: Callable[[], Any], force: bool = False) -> Any:
    """One computation per result at a time in a process: dashboard sessions and the background
    refresh thread asking for the same bundle wait for the first one instead of duplicating it."""
    with _lock(name):
        return _load_or_compute(name, fn, force)


# Dashboard processes set SERVE_STALE: a stored result computed by the same code and model version,
# but from older data, is returned at once while the background refresh (macro.autorefresh, which
# computes inside `fresh_results()`) replaces it. Scripts and tests never serve stale results.
SERVE_STALE = False
_FRESH = threading.local()


class fresh_results:  # noqa: N801  (used as a context manager)
    """Within this block, load_or_compute never returns a stale result."""

    def __enter__(self):
        _FRESH.on = True

    def __exit__(self, *exc):
        _FRESH.on = False


def _meta(name: str) -> dict:
    return {"code": code_hash(), "mode": mode(), "version": MODEL_VERSIONS.get(name.split(":")[0], "0")}


def _load_or_compute(name: str, fn: Callable[[], Any], force: bool) -> Any:
    path = _dir() / f"{name.replace(':', '__')}.pkl"
    fp = _fingerprint(name)
    if path.exists() and not force:
        try:
            with open(path, "rb") as fh:
                stored = pickle.load(fh)
            stored_fp, obj = stored[0], stored[1]
            stored_meta = stored[2] if len(stored) > 2 else {}
            if stored_fp == fp:
                return obj
            if SERVE_STALE and not getattr(_FRESH, "on", False) and stored_meta == _meta(name):
                log.info("serving %s computed from older data while it is refreshed", name)
                return obj
        except (pickle.UnpicklingError, EOFError, AttributeError, ModuleNotFoundError) as exc:
            log.warning("discarding unreadable result cache %s: %s", path.name, exc)
    obj = fn()
    with open(path, "wb") as fh:
        pickle.dump((fp, obj, _meta(name)), fh)
    return obj
