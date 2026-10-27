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
from macro.utils import run_metadata


def _step(name, fn):
    t0 = time.time()
    out = fn()
    print(f"  {name:28s} {time.time() - t0:6.1f}s")
    return out


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
    g = _step("growth and recession", lambda: pipeline.growth_bundle(force=args.force))
    if not args.no_archive:
        import pandas as pd

        nc = g["nowcast"]
        fc = pd.DataFrame([{"model": "DFM nowcast", "target_date": nc["target"].to_timestamp(), "h": 0,
                            "point": nc["point"], "sigma": nc["se"]}])
        n = archive.record(fc, module="growth", variable="US real GDP growth q/q annualised", region="US",
                           data_as_of=g["as_of"], vintage_label=g["vintage_label"])
        print(f"    archived {n} GDP nowcast -> {archive.archive_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
