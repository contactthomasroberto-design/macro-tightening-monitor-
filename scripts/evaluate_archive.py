"""Compare archived forecasts with later outcomes (track record), GDPNow-style.

MACRO_MODE=live python scripts/evaluate_archive.py
"""

from __future__ import annotations

import _bootstrap  # noqa: F401
from macro import archive, pipeline
from macro.reports import out_dir


def main() -> int:
    a = archive.read()
    print(
        f"archive: {archive.archive_path()} — {len(a)} rows, {a['data_as_of'].nunique() if len(a) else 0} vintages"
    )
    rows, summ = pipeline.track_record()
    n_eval = int(rows["actual"].notna().sum()) if len(rows) else 0
    print(f"evaluated forecasts (outcome known): {n_eval}")
    if summ.empty:
        print("no evaluation points yet: the track record needs outcomes for archived target dates")
        return 0
    print(summ.round(3).to_string(index=False))
    path = out_dir() / "track_record_summary.csv"
    summ.to_csv(path, index=False)
    rows.to_csv(out_dir() / "track_record_rows.csv", index=False)
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
