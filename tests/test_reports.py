"""Report products: build in demo (SYNTHETIC on every page), refuse demo without the flag, and
LinkedIn exports refuse demo mode."""

import subprocess
import sys

import pytest

from macro.config import ROOT


def _run(script, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "MACRO_MODE": "demo"},
        timeout=1200,
    )


def test_export_figures_refuses_demo():
    r = _run("export_figures.py")
    assert r.returncode != 0 and "refuses to run in demo mode" in (r.stderr + r.stdout)


def test_weekly_refuses_demo_without_flag():
    r = _run("weekly_monitor.py")
    assert r.returncode != 0 and "Refusing" in (r.stderr + r.stdout)


@pytest.mark.slow
@pytest.mark.parametrize("script", ["weekly_monitor.py", "monthly_view.py"])
def test_reports_build_in_demo_with_watermark(script):
    from pypdf import PdfReader

    r = _run(script, "--allow-demo")
    assert r.returncode == 0, r.stderr[-2000:]
    path = r.stdout.strip().splitlines()[-1]
    pdf = PdfReader(path)
    n = len(pdf.pages)
    assert (n == 2) if script.startswith("weekly") else (4 <= n <= 6)
    for page in pdf.pages:
        text = page.extract_text()
        assert "SYNTHETIC DATA" in text
        assert "not investment advice" in text


def test_archive_outcomes_mapping():
    from macro import pipeline

    out = pipeline.archive_outcomes()
    assert "US headline inflation yoy" in out and "US real GDP growth q/q annualised" in out
