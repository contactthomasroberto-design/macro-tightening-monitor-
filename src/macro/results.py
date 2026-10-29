"""Disk cache of heavy model results, so dashboard pages load in seconds (BRIEF §7).

`scripts/run_all.py` computes and stores every result; pages call `load_or_compute`, which
returns the stored object if it is still valid, and computes it otherwise.

A stored result is valid when
- its fingerprint matches: (name, mode, model version, code hash, config hash), and
- every series it read (recorded by `macro.inputs` during the computation) still has the content
  hash it had then (`Store.content_hashes`).
So a new CPI print invalidates the inflation and policy results that read CPI, not the yield-curve
results; and a result computed elsewhere from identical data (the daily snapshot built by GitHub
Actions) is valid locally.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import pickle
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from macro import inputs
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
        for f in sorted((ROOT / "config").glob("*.yaml")):
            if f.name != "calendar.yaml":  # events only: no model reads them
                h.update(f.read_bytes())
        _CODE_HASH = h.hexdigest()[:12]
    return _CODE_HASH


def _fingerprint(name: str) -> str:
    """Changes with the model version, the code or the configuration (data is checked separately)."""
    version = MODEL_VERSIONS.get(name.split(":")[0], "0")
    return hashlib.sha1(f"{name}|{mode()}|{version}|{code_hash()}".encode()).hexdigest()[:16]


def _hashes(ids) -> dict[str, str]:
    from macro.data import store

    return store().content_hashes(ids) if default_path().exists() else {}


def inputs_current(meta: dict) -> bool:
    """True when every input series still has the content it had when the result was computed."""
    stored = meta.get("inputs")
    if stored is None:  # computed before inputs were recorded
        return False
    return _hashes(stored) == stored if stored else True


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


def _same_code(name: str, meta: dict) -> bool:
    return all(meta.get(k) == v for k, v in _meta(name).items())


def read_meta(path: Path) -> dict:
    """Metadata of a stored result (empty when unreadable or written by an older version)."""
    try:
        with open(path, "rb") as fh:
            stored = pickle.load(fh)
        return stored[2] if len(stored) > 2 else {}
    except Exception:
        return {}


def is_valid(name: str, path: Path) -> bool:
    """True when the result stored at `path` would be returned without recomputing."""
    try:
        with open(path, "rb") as fh:
            stored = pickle.load(fh)
    except Exception:
        return False
    meta = stored[2] if len(stored) > 2 else {}
    return stored[0] == _fingerprint(name) and inputs_current(meta)


def _load_or_compute(name: str, fn: Callable[[], Any], force: bool) -> Any:
    path = _dir() / f"{name.replace(':', '__')}.pkl"
    fp = _fingerprint(name)
    if path.exists() and not force:
        try:
            with open(path, "rb") as fh:
                stored = pickle.load(fh)
            stored_fp, obj = stored[0], stored[1]
            stored_meta = stored[2] if len(stored) > 2 else {}
            if stored_fp == fp and inputs_current(stored_meta):
                inputs.record(stored_meta.get("inputs") or ())
                return obj
            if SERVE_STALE and not getattr(_FRESH, "on", False) and _same_code(name, stored_meta):
                log.info("serving %s computed from older data while it is refreshed", name)
                inputs.record(stored_meta.get("inputs") or ())
                return obj
        except (pickle.UnpicklingError, EOFError, AttributeError, ModuleNotFoundError) as exc:
            log.warning("discarding unreadable result cache %s: %s", path.name, exc)
    with inputs.recording() as used:
        obj = fn()
    inputs.record(used)  # a bundle computed inside another one feeds the outer bundle's inputs
    meta = _meta(name) | {
        "inputs": _hashes(used),
        "computed": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as fh:
        pickle.dump((fp, obj, meta), fh)
    tmp.replace(path)  # atomic: a page never reads a half-written result
    return obj
