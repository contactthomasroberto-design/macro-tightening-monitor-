"""Stale-while-revalidate: the app serves results computed by the same code from older data."""

from macro import results


def test_stale_results_served_only_to_the_app_and_only_for_the_same_code(tmp_path, monkeypatch):
    monkeypatch.setattr(results, "_dir", lambda: tmp_path)
    fp = {"v": "old"}
    monkeypatch.setattr(results, "_fingerprint", lambda name: fp["v"])
    calls = []

    def compute():
        calls.append(1)
        return len(calls)

    assert results.load_or_compute("policy:fed", compute) == 1
    fp["v"] = "new-data"
    monkeypatch.setattr(results, "SERVE_STALE", True)
    assert results.load_or_compute("policy:fed", compute) == 1  # stale result at once, no compute
    with results.fresh_results():  # the background refresh recomputes
        assert results.load_or_compute("policy:fed", compute) == 2
    monkeypatch.setattr(results, "code_hash", lambda: "other-code")
    fp["v"] = "newer"
    assert results.load_or_compute("policy:fed", compute) == 3  # different code: never stale
