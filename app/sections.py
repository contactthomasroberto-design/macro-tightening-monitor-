"""Section pages: one navigation entry holding several sub-pages behind a segmented control.

Only the selected sub-page runs, so a section costs no more than one page. The sub-pages are the
ordinary page scripts in app/views/ (each still runs on its own, which the smoke tests check); inside
a section their header and footer shrink to a subtitle (components.EMBEDDED).
"""

from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

from components import EMBEDDED, footer, header

VIEWS = Path(__file__).parent / "views"


def render(title: str, subtitle: str, parts: list[tuple[str, str]], key: str) -> None:
    header(title, subtitle)
    labels = [lab for lab, _ in parts]
    choice = st.segmented_control(
        "Section", labels, default=labels[0], key=f"sec_{key}", label_visibility="collapsed"
    )
    file = dict(parts)[choice or labels[0]]
    EMBEDDED["on"] = True
    try:
        runpy.run_path(str(VIEWS / file), run_name=f"mtm_{Path(file).stem}")
    finally:
        EMBEDDED["on"] = False
    footer()
