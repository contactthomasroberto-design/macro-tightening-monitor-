"""Keep the live dashboard current without anyone running a script.

`refresh_and_warm()` re-downloads every catalogue series whose cache has expired (TTL by frequency in
`data/store.py`: 12 hours for daily series, 2 days weekly, 3 days monthly, 7 days quarterly) and, if
any observation changed, recomputes the model bundles so pages load the new numbers already
computed. `start_background()` runs it in a daemon thread every `interval_hours` (one thread per
process). Status is written to data/cache/refresh_status.json for the Data health page.

Forecast-archive writes are NOT done here: the archive is appended by `scripts/run_all.py` (the
scheduled GitHub workflow), so that every archived forecast has a commit and a run record.
Demo mode never refreshes (synthetic data).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from collections.abc import Callable

from macro.config import ROOT, catalogue
from macro.utils import is_demo

log = logging.getLogger("macro.autorefresh")
STATUS_PATH = ROOT / "data" / "cache" / "refresh_status.json"
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_status(**kw) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    cur = read_status()
    cur.update(kw)
    STATUS_PATH.write_text(json.dumps(cur, indent=2, default=str))


def read_status() -> dict:
    try:
        return json.loads(STATUS_PATH.read_text())
    except (OSError, ValueError):
        return {}


def refresh_stale(ids: list[str] | None = None) -> dict[str, str]:
    """Fetch every series whose cached copy has expired. Returns {id: 'ok' | error message}."""
    from macro.data import refresh_series, store

    st = store()
    out: dict[str, str] = {}
    for spec in catalogue().series:
        if ids is not None and spec.id not in ids:
            continue
        if st.is_fresh(spec.id, spec.freq):
            continue
        ok, msg = refresh_series(spec.id, st)
        out[spec.id] = "ok" if ok else msg
    return out


def _bundles() -> list[tuple[str, Callable]]:
    from macro import pipeline as p

    steps: list[tuple[str, Callable]] = [
        (f"inflation {r}", lambda r=r: p.inflation_bundle(r)) for r in ("US", "EA", "JP")
    ]
    steps += [(f"policy {b}", lambda b=b: p.policy_bundle(b)) for b in p.BANKS]
    steps += [
        ("policy cross-bank", p.cross_bank_bundle),
        ("financial conditions", p.fincond_bundle),
        ("curves", p.curves_bundle),
        ("transmission", p.transmission_bundle),
        ("positioning", p.positioning_bundle),
        ("growth and recession", p.growth_bundle),
        ("scenarios", p.scenario_bundle),
        ("regimes", p.regime_bundle),
        ("historical cycles", p.history_bundle),
        ("views", lambda: p.build_views(p.scenario_bundle()["base_weights"])),
    ]
    return steps


def refresh_and_warm(warm: bool = True) -> dict:
    """One refresh cycle. Never raises: failures are logged and written to the status file."""
    if is_demo():
        return {"skipped": "demo mode"}
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "a refresh is already running"}
    try:
        from macro.data import store

        v0 = store().data_version()
        _write_status(running=True, started=_now())
        res = refresh_stale()
        failed = {k: v for k, v in res.items() if v != "ok"}
        changed = store().data_version() != v0
        warm_errors: dict[str, str] = {}
        if warm and (changed or read_status().get("warmed_version") != store().data_version()):
            for name, fn in _bundles():
                try:
                    fn()
                except Exception as exc:  # one module failing must not stop the others
                    warm_errors[name] = f"{type(exc).__name__}: {exc}"[:300]
                    log.warning("warming %s failed: %s", name, exc)
            _write_status(warmed_version=store().data_version())
        summary = {
            "running": False,
            "finished": _now(),
            "checked": len(res),
            "updated_ok": len(res) - len(failed),
            "failed": failed,
            "data_changed": changed,
            "warm_errors": warm_errors,
        }
        _write_status(**summary)
        return summary
    except Exception as exc:
        log.exception("refresh cycle failed")
        _write_status(running=False, finished=_now(), error=f"{type(exc).__name__}: {exc}")
        return {"error": str(exc)}
    finally:
        _LOCK.release()


def start_background(interval_hours: float = 3.0) -> threading.Thread | None:
    """Start the refresh loop once per process (no-op in demo mode or if already running)."""
    global _THREAD
    if is_demo():
        return None
    if _THREAD is not None and _THREAD.is_alive():
        return _THREAD
    for t in threading.enumerate():  # started by a previous copy of this module (app redeploy)
        if t.name == "macro-autorefresh" and t.is_alive():
            return t

    def loop() -> None:
        while True:
            refresh_and_warm()
            time.sleep(interval_hours * 3600)

    _THREAD = threading.Thread(target=loop, name="macro-autorefresh", daemon=True)
    _THREAD.start()
    return _THREAD
