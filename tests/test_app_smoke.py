"""AppTest smoke tests: every page renders without exception in demo mode."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

PAGES = sorted((Path(__file__).resolve().parents[1] / "app" / "pages").glob("*.py"))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_page_renders(page):
    at = AppTest.from_file(str(page), default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
