"""Keep the live dashboard current without anyone running a script.

`refresh_and_warm()` fetches every catalogue series that is due (`macro.data.schedule`: polled every
10 to 30 minutes around its expected release, at the slow TTL otherwise), then recomputes the light
model bundles whose input series changed (`LIGHT`: inflation, policy rules, financial conditions,
curves, transmission, positioning, regimes, markets; a few seconds to a minute each, under 300 MB). The heavy
bundles (dynamic factor nowcast, scenarios, views) come from the snapshot computed by GitHub Actions
(macro.warmstart), unless MACRO_BACKGROUND_MODELS=1 (a server with enough memory).
`start_background()` runs it in a daemon thread every `interval_minutes` (one thread per process);
`ON_CHANGE` callbacks run after new data or results (the app clears its page caches). Status is
written to data/cache/refresh_status.json for the Data health page.

Forecast-archive writes are NOT done here: the archive is appended by `scripts/run_all.py` (the
scheduled GitHub workflow), so that every archived forecast has a commit and a run record.
Demo mode never refreshes (synthetic data).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
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


ON_CHANGE: list[Callable[[], None]] = []


def refresh_due(
    ids: list[str] | None = None, now: dt.datetime | None = None
) -> tuple[dict[str, str], set[str]]:
    """Fetch every series that is due. Returns ({id: 'ok' | error message}, ids whose content changed)."""
    from macro.data import RETRY_AFTER_FAILURE, refresh_series, store
    from macro.data.schedule import due

    st = store()
    state = st.latest_state()
    todo = []
    for spec in catalogue().series:
        if ids is not None and spec.id not in ids:
            continue
        last_obs, last_fetched = state.get(spec.id, (None, None))
        if not due(spec, last_obs, last_fetched, now):
            continue
        if st.failed_recently(spec.id, RETRY_AFTER_FAILURE):
            continue  # the source refused less than an hour ago
        todo.append(spec.id)
    before = st.content_hashes(todo)
    out: dict[str, str] = {}
    for sid in todo:
        ok, msg = refresh_series(sid, st)
        out[sid] = "ok" if ok else msg
    after = st.content_hashes(todo)
    return out, {sid for sid in todo if after.get(sid) != before.get(sid)}


def refresh_stale(ids: list[str] | None = None) -> dict[str, str]:
    """Fetch every series that is due (kept for scripts). Returns {id: 'ok' | error message}."""
    return refresh_due(ids)[0]


def light_bundles() -> list[tuple[str, Callable]]:
    """Bundles cheap enough to recompute inside the hosted app (measured: < 1 min, < 300 MB each)."""
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
        ("regimes", p.regime_bundle),
        ("markets", p.markets_bundle),
        ("recession signals", p.leading_bundle),
        ("stress testing", p.stress_bundle),
    ]
    return steps


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
        ("markets", p.markets_bundle),
        ("recession signals", p.leading_bundle),
        ("stress testing", p.stress_bundle),
        ("historical cycles", p.history_bundle),
        ("views", lambda: p.build_views(p.scenario_bundle()["base_weights"])),
    ]
    return steps


def background_models() -> bool:
    """Recompute models in the app's background thread? Off by default: on Streamlit Community Cloud
    (about 1 GB of memory) the daily snapshot computed by GitHub Actions provides the results, and
    recomputing the dynamic factor model there exceeded the memory limit. MACRO_BACKGROUND_MODELS=1
    turns it on (a local server with enough memory)."""
    return os.environ.get("MACRO_BACKGROUND_MODELS", "0") == "1"


def _recompute(steps: list[tuple[str, Callable]]) -> tuple[list[str], dict[str, str]]:
    """Bring each bundle up to date: only those whose stored result is no longer valid recompute.
    Returns (stored results rewritten, errors by step)."""
    from macro.results import _dir, fresh_results

    def stamps() -> dict[str, int]:
        return {f.stem.replace("__", ":"): f.stat().st_mtime_ns for f in _dir().glob("*.pkl")}

    before = stamps()
    errors = {}
    for name, fn in steps:
        try:
            with fresh_results():
                fn()
        except Exception as exc:  # one module failing must not stop the others
            errors[name] = f"{type(exc).__name__}: {exc}"[:300]
            log.warning("recomputing %s failed: %s", name, exc)
    after = stamps()
    return sorted(k for k, t in after.items() if before.get(k) != t), errors


def refresh_and_warm(warm: bool | None = None, light: bool = True) -> dict:
    """One refresh cycle: due data always; then the light bundles whose inputs changed (`light`), and
    every bundle when `warm` (default: background_models()). Never raises: failures are logged and
    written to the status file."""
    if warm is None:
        warm = background_models()
    if is_demo():
        return {"skipped": "demo mode"}
    if not _LOCK.acquire(blocking=False):
        return {"skipped": "a refresh is already running"}
    try:
        _write_status(running=True, started=_now())
        res, changed_ids = refresh_due()
        failed = {k: v for k, v in res.items() if v != "ok"}
        recomputed: list[str] = []
        warm_errors: dict[str, str] = {}
        first = not read_status().get("light_checked")
        if warm or (light and (changed_ids or first)):
            recomputed, warm_errors = _recompute(_bundles() if warm else light_bundles())
            _write_status(light_checked=_now())
        if changed_ids or recomputed:
            for cb in list(ON_CHANGE):
                try:
                    cb()
                except Exception as exc:
                    log.warning("on-change callback failed: %s", exc)
        summary = {
            "running": False,
            "finished": _now(),
            "checked": len(res),
            "updated_ok": len(res) - len(failed),
            "failed": failed,
            "data_changed": bool(changed_ids),
            "changed_series": sorted(changed_ids),
            "recomputed": recomputed,
            "warm_errors": warm_errors,
        }
        if changed_ids:
            summary["last_data_change"] = _now()
        _write_status(**summary)
        return summary
    except Exception as exc:
        log.exception("refresh cycle failed")
        _write_status(running=False, finished=_now(), error=f"{type(exc).__name__}: {exc}")
        return {"error": str(exc)}
    finally:
        _LOCK.release()


def start_background(interval_minutes: float = 10.0) -> threading.Thread | None:
    """Start the refresh loop once per process (no-op in demo mode or if already running). Each cycle
    is cheap when nothing is due: a few SQLite reads."""
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
            time.sleep(interval_minutes * 60)

    _THREAD = threading.Thread(target=loop, name="macro-autorefresh", daemon=True)
    _THREAD.start()
    return _THREAD
