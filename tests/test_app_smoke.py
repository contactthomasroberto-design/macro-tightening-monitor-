"""AppTest smoke tests: every page renders without exception in demo mode."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGES = sorted((Path(__file__).resolve().parents[1] / "app" / "views").glob("*.py"))


@pytest.fixture(scope="module")
def portfolio_warm():
    """The portfolio bundle simulates 20 years of weekly rebalances: compute it once, outside the
    per-page time limit, so the Portfolio pages read it from the result cache."""
    from macro.pipeline import portfolio_bundle

    portfolio_bundle()


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_renders(page, request):
    if page.stem.startswith("portfolio"):
        request.getfixturevalue("portfolio_warm")
    at = AppTest.from_file(str(page), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("region", ["EA", "JP"])
def test_inflation_regions(region):
    page = Path(__file__).resolve().parents[1] / "app" / "views" / "inflation.py"
    at = AppTest.from_file(str(page), default_timeout=300)
    at.run()
    at.radio(key="infl_region").set_value(region).run()
    assert not at.exception, [e.value for e in at.exception]
