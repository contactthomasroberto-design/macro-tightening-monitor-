import json
import os

import pytest

from macro.config import ROOT
from macro.snapshot import collect

SNAP = ROOT / "tests" / "fixtures" / "demo_snapshot.json"


def test_demo_outputs_match_snapshot():
    got = collect()
    if os.environ.get("UPDATE_SNAPSHOT") == "1" or not SNAP.exists():
        SNAP.write_text(json.dumps(got, indent=2, sort_keys=True))
        pytest.skip("snapshot written")
    want = json.loads(SNAP.read_text())
    for k, v in want.items():
        assert k in got, f"{k} no longer produced"
        assert got[k] == pytest.approx(v, rel=1e-4, abs=1e-8), f"{k}: {got[k]} != {v}"
