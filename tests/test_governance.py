"""Governance checks (BRIEF §2.6-2.7): versions logged, model cards and notes present."""

from macro.config import ROOT
from macro.versions import MODEL_VERSIONS

IMPLEMENTED = ["inflation"]  # extended milestone by milestone


def test_every_version_in_changelog():
    log = (ROOT / "docs" / "MODEL_CHANGELOG.md").read_text()
    for module, v in MODEL_VERSIONS.items():
        assert f"| {module} | {v} |" in log, f"{module} {v} missing from MODEL_CHANGELOG.md"


def test_model_cards_and_notes_exist():
    for m in IMPLEMENTED:
        assert (ROOT / "docs" / "model_cards" / f"{m}.md").exists(), f"model card missing for {m}"
        assert (ROOT / "docs" / "notes" / f"{m}.md").exists(), f"note missing for {m}"


def test_research_log_has_entries_for_implemented_modules():
    log = (ROOT / "docs" / "research_log.md").read_text()
    for m in IMPLEMENTED:
        assert f"| {m} |" in log
