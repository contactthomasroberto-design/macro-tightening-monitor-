import pandas as pd

from macro import research_notes as rn


def test_proposals_and_follow_up(tmp_path):
    d = tmp_path / "notes" / "2026-11-19"
    d.mkdir(parents=True)
    (d / "japan-asia-analyst.md").write_text(
        "# Japon\n\ntexte\n\n```yaml\nproposals:\n  - ticker: EWJ\n    direction: above\n    threshold: 0.03\n"
        "    horizon: 2027-02-18\n    probability: 0.62\n    rationale: BoJ\n```\n"
    )
    c = tmp_path / "committee" / "2026-11-19"
    c.mkdir(parents=True)
    (c / "note-fx-strategist.md").write_text(
        "```yaml\nproposals:\n  - {ticker: FXY, direction: above, probability: 0.55}\nviews: []\n```"
    )
    p = rn.proposals(tmp_path)
    assert set(p["agent"]) == {"japan-asia-analyst", "fx-strategist"}
    dec = pd.DataFrame(
        [{"agent": "chief-investment-officer", "target": "EWJ", "direction": "above", "date": "2026-11-20"}]
    )
    f = rn.follow_up(p, dec).set_index("ticker")
    assert bool(f.loc["EWJ", "adopted"]) and not bool(f.loc["FXY", "adopted"])
    w = rn.word_counts(tmp_path)
    assert w["notes"].sum() == 2 and w["words"].sum() > 10
