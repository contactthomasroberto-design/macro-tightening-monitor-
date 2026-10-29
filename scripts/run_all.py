"""Run every model, refresh the result cache, and append forecasts to the archive.

MACRO_MODE=demo python scripts/run_all.py    # synthetic; archive goes to the ignored demo cache
MACRO_MODE=live python scripts/run_all.py    # real data; appends to archive/forecasts.csv
"""

from __future__ import annotations

import argparse
import logging
import time

import _bootstrap  # noqa: F401
from macro import archive, pipeline
from macro.utils import is_demo, run_metadata


def _step(name, fn):
    t0 = time.time()
    out = fn()
    print(f"  {name:28s} {time.time() - t0:6.1f}s")
    return out


def backfill_demo_archive(b: dict, region: str, last_n: int = 24) -> int:
    """DEMO ONLY: seed the demo archive with pseudo out-of-sample forecasts from the last `last_n`
    origins so the Track record page has evaluation points. Never used in live mode: the live
    archive only contains forecasts actually made by scheduled runs."""
    import pandas as pd

    assert is_demo()
    f = b["oos"]["forecasts"]
    f = f[f["model"].isin(["COMB", "RW"]) & f["origin"].isin(sorted(f["origin"].unique())[-last_n:])].dropna(
        subset=["point", "sigma"]
    )
    n = 0
    for origin, g in f.groupby("origin"):
        fc = pd.DataFrame(
            {
                "model": g["model"],
                "target_date": g["origin"] + g["h"].map(lambda h: pd.DateOffset(months=int(h))),
                "h": g["h"],
                "point": g["point"],
                "sigma": g["sigma"],
            }
        )
        n += archive.record(
            fc,
            module="inflation",
            variable=f"{region} headline inflation yoy",
            region=region,
            data_as_of=origin,
            vintage_label="demo backfill (pseudo out-of-sample)",
            run_date=origin.date(),
        )
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="recompute even if cached")
    ap.add_argument("--no-archive", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    meta = run_metadata()
    print("run:", meta)

    for region in ("US", "EA", "JP"):
        b = _step(f"inflation {region}", lambda r=region: pipeline.inflation_bundle(r, force=args.force))
        if "oos" in b and is_demo() and not args.no_archive:
            n = backfill_demo_archive(b, region)
            print(f"    demo only: backfilled {n} pseudo out-of-sample forecasts into the demo archive")
        if "forecasts" in b and not args.no_archive:
            n = archive.record(
                b["forecasts"],
                module="inflation",
                variable=f"{region} headline inflation yoy",
                region=region,
                data_as_of=b["as_of"],
                vintage_label=b["vintage_label"],
            )
            print(f"    archived {n} inflation forecasts -> {archive.archive_path()}")
    for bank in pipeline.BANKS:
        _step(f"policy {bank}", lambda b=bank: pipeline.policy_bundle(b, force=args.force))
    _step("policy cross-bank", lambda: pipeline.cross_bank_bundle(force=args.force))
    _step("financial conditions", lambda: pipeline.fincond_bundle(force=args.force))
    _step("curves", lambda: pipeline.curves_bundle(force=args.force))
    _step("transmission", lambda: pipeline.transmission_bundle(force=args.force))
    _step("positioning", lambda: pipeline.positioning_bundle(force=args.force))
    g = _step("growth and recession", lambda: pipeline.growth_bundle(force=args.force))
    if not args.no_archive:
        import pandas as pd

        nc = g["nowcast"]
        fc = pd.DataFrame(
            [
                {
                    "model": "DFM nowcast",
                    "target_date": nc["target"].to_timestamp(),
                    "h": 0,
                    "point": nc["point"],
                    "sigma": nc["se"],
                }
            ]
        )
        n = archive.record(
            fc,
            module="growth",
            variable="US real GDP growth q/q annualised",
            region="US",
            data_as_of=g["as_of"],
            vintage_label=g["vintage_label"],
        )
        print(f"    archived {n} GDP nowcast -> {archive.archive_path()}")
    sb = _step("scenarios and Monte Carlo", lambda: pipeline.scenario_bundle(force=args.force))
    _step("regimes", lambda: pipeline.regime_bundle(force=args.force))
    _step("markets", lambda: pipeline.markets_bundle(force=args.force))
    _step("historical cycles (GMD)", lambda: pipeline.history_bundle(force=args.force))
    _step("views", lambda: pipeline.build_views(sb["base_weights"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
