"""Refresh the data cache.

MACRO_MODE=demo python scripts/update_data.py            # synthetic data into the demo cache
MACRO_MODE=live python scripts/update_data.py            # every catalogue series from its source
MACRO_MODE=live python scripts/update_data.py --vintages # + ALFRED vintages (needs FRED_API_KEY)
python scripts/update_data.py --catalogue                # regenerate docs/data_catalogue.md
"""

from __future__ import annotations

import argparse
import logging
import os

import _bootstrap  # noqa: F401
from macro.config import ROOT, catalogue
from macro.data import load_demo_into_store, refresh_series, sources, store
from macro.data.health import catalogue_markdown, health_table
from macro.utils import is_demo, run_metadata

# Monthly/quarterly FRED series whose real-time vintages matter for forecast evaluation.
VINTAGE_SERIES = [
    "CPIAUCSL",
    "CPILFESL",
    "PCEPI",
    "PCEPILFE",
    "UNRATE",
    "PAYEMS",
    "GDPC1",
    "GDPPOT",
    "INDPRO",
    "RSAFS",
    "PCEC96",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="series ids to refresh")
    ap.add_argument("--vintages", action="store_true", help="also pull ALFRED vintages")
    ap.add_argument("--catalogue", action="store_true", help="write docs/data_catalogue.md and exit")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.catalogue:
        (ROOT / "docs" / "data_catalogue.md").write_text(catalogue_markdown(), encoding="utf-8")
        print("wrote docs/data_catalogue.md")
        return 0

    st = store()
    print("run:", run_metadata())
    if is_demo():
        n = load_demo_into_store(st)
        print(f"demo: wrote {n} synthetic observations to {st.path}")
        return 0

    ids = args.only or catalogue().ids
    failures = []
    for sid in ids:
        ok, msg = refresh_series(sid, st)
        print(f"{'OK  ' if ok else 'FAIL'} {sid:24s} {msg}")
        if not ok:
            failures.append(sid)
    if args.vintages:
        if not os.environ.get("FRED_API_KEY"):
            print(
                "FRED_API_KEY not set: skipping ALFRED vintages (results stay latest-vintage, not point-in-time)"
            )
        else:
            for sid in VINTAGE_SERIES:
                try:
                    df = sources.fetch_alfred_all_vintages(catalogue().get(sid))
                except Exception as e:  # noqa: BLE001 - one failed series must not stop the refresh
                    print(f"FAIL ALFRED {sid}: {e}")
                    failures.append(f"ALFRED:{sid}")
                    continue
                st.write(sid, df, source="alfred")
                print(f"ALFRED {sid}: {df['vintage_date'].nunique()} vintages")
    h = health_table(st)
    print(h["status"].value_counts().to_string())
    print(f"{len(failures)} failures: {failures}")
    return 0  # failures are reported, not fatal: the dashboard degrades to cached copies


if __name__ == "__main__":
    raise SystemExit(main())
