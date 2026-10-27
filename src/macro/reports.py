"""PDF products (BRIEF §6): Weekly Monitor (2 pages) and Monthly Macro View (4-6 pages).

Every page carries the disclaimer; demo-mode PDFs carry a SYNTHETIC DATA watermark on every page.
Charts are rendered with kaleido (needs Chrome/Chromium; `ensure_browser` points kaleido to a
Chromium build when Chrome is not installed).
"""

from __future__ import annotations

import datetime as dt
import glob
import os
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF

from macro.config import ROOT
from macro.utils import DISCLAIMER, SYNTHETIC_BANNER, is_demo, run_metadata

FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/Library/Fonts",
    str(ROOT / "assets" / "fonts"),
]
STATUS_LABEL = {"good": "OK", "warning": "Watch", "serious": "Serious", "critical": "Critical"}
STATUS_RGB = {
    "good": (12, 163, 12),
    "warning": (200, 140, 0),
    "serious": (236, 131, 90),
    "critical": (208, 59, 59),
}


def ensure_browser() -> None:
    """Let kaleido find a Chromium when Google Chrome is not installed (cloud containers)."""
    if os.environ.get("BROWSER_PATH") or shutil.which("google-chrome") or shutil.which("chromium"):
        return
    for pat in ("/opt/pw-browsers/chromium*/chrome-linux*/chrome", "/usr/lib/chromium/chromium"):
        hits = sorted(glob.glob(pat))
        if hits:
            os.environ["BROWSER_PATH"] = hits[-1]
            return


def fig_png(fig: go.Figure, width: int = 1000, height: int = 480) -> str:
    ensure_browser()
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    fig.write_image(path, width=width, height=height, scale=2)
    return path


def _font_path(bold: bool = False) -> str | None:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        p = Path(d) / name
        if p.exists():
            return str(p)
    return None


class Report(FPDF):
    def __init__(self, title: str, subtitle: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.title_text, self.subtitle = title, subtitle
        self.unicode = _font_path() is not None and _font_path(True) is not None
        if self.unicode:
            self.add_font("DejaVu", "", _font_path())
            self.add_font("DejaVu", "B", _font_path(True))
            self.family = "DejaVu"
        else:
            self.family = "Helvetica"
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(14, 14, 14)
        self.meta = run_metadata()

    def t(self, s) -> str:
        s = str(s)
        if self.unicode:
            return s
        return s.encode("latin-1", "replace").decode("latin-1")

    def header(self):
        self.set_font(self.family, "B", 9)
        self.set_text_color(90, 90, 90)
        self.cell(0, 5, self.t(f"{self.title_text} — {self.subtitle}"), new_x="LMARGIN", new_y="NEXT")
        if is_demo():
            self.set_text_color(208, 59, 59)
            self.set_font(self.family, "B", 11)
            self.cell(0, 6, self.t(SYNTHETIC_BANNER), new_x="LMARGIN", new_y="NEXT", align="C")
            with self.local_context(fill_opacity=0.12):
                self.set_font(self.family, "B", 40)
                y = self.get_y()
                self.set_xy(14, 140)
                self.cell(0, 20, "SYNTHETIC DATA", align="C")
                self.set_y(y)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.family, "", 7)
        self.set_text_color(110, 110, 110)
        m = self.meta
        self.multi_cell(
            0,
            3.2,
            self.t(
                f"{DISCLAIMER} Run {m['run_timestamp']} · git {m['git_hash']} · mode {m['mode']} · page {self.page_no()}"
            ),
            align="L",
        )

    # ------------------------------------------------------------------ building blocks
    def h1(self, s):
        self.set_font(self.family, "B", 15)
        self.multi_cell(0, 7, self.t(s), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def h2(self, s):
        self.ln(1)
        self.set_font(self.family, "B", 11)
        self.multi_cell(0, 6, self.t(s), new_x="LMARGIN", new_y="NEXT")

    def para(self, s, size: float = 9):
        self.set_font(self.family, "", size)
        self.multi_cell(0, 4.4, self.t(s), new_x="LMARGIN", new_y="NEXT")

    def bullets(self, items, size: float = 9):
        self.set_font(self.family, "", size)
        for it in items:
            self.multi_cell(
                0, 4.4, self.t(f"• {it}" if self.unicode else f"- {it}"), new_x="LMARGIN", new_y="NEXT"
            )

    def table(
        self,
        df: pd.DataFrame,
        col_widths: list[float] | None = None,
        size: float = 7.5,
        status_col: str | None = None,
        index: bool = True,
    ):
        d = df.reset_index() if index else df.copy()
        cols = list(d.columns)
        w = col_widths or [(self.w - 28) / len(cols)] * len(cols)
        self.set_font(self.family, "B", size)
        self.set_fill_color(235, 238, 242)
        for c, cw in zip(cols, w, strict=True):
            self.cell(cw, 5, self.t(str(c))[:40], border=0, fill=True)
        self.ln()
        self.set_font(self.family, "", size)
        for _, r in d.iterrows():
            for c, cw in zip(cols, w, strict=True):
                v = r[c]
                txt = f"{v:,.2f}" if isinstance(v, float) else str(v)
                if status_col and c == status_col:
                    self.set_text_color(*STATUS_RGB.get(str(v), (0, 0, 0)))
                    txt = STATUS_LABEL.get(str(v), txt)
                self.cell(cw, 4.6, self.t(txt)[: int(cw * 0.75)], border="B")
                self.set_text_color(0, 0, 0)
            self.ln()
        self.ln(1)

    def image_fig(self, fig: go.Figure, w_mm: float | None = None, px=(1000, 480)):
        path = fig_png(fig, *px)
        w_mm = w_mm or (self.w - 28)
        self.image(path, w=w_mm)
        os.unlink(path)

    def box(self, title: str, text: str):
        self.ln(1)
        self.set_fill_color(248, 240, 220)
        self.set_font(self.family, "B", 9)
        self.multi_cell(0, 5, self.t(title), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_font(self.family, "", 8)
        self.multi_cell(0, 4, self.t(text), fill=True, new_x="LMARGIN", new_y="NEXT")


def out_dir() -> Path:
    d = ROOT / "out" / ("demo" if is_demo() else "live")
    d.mkdir(parents=True, exist_ok=True)
    return d


def changelog_rows(month: str) -> pd.DataFrame:
    """Rows of docs/MODEL_CHANGELOG.md whose effective window is `month` (YYYY-MM)."""
    rows = []
    for line in (ROOT / "docs" / "MODEL_CHANGELOG.md").read_text().splitlines():
        parts = [p.strip() for p in line.strip().strip("|").split("|")]
        if len(parts) >= 5 and parts[0] == month:
            rows.append(
                {
                    "window": parts[0],
                    "model": parts[1],
                    "version": parts[2],
                    "change": parts[3],
                    "reason": parts[4],
                }
            )
    return pd.DataFrame(rows)


def today_label() -> str:
    return dt.date.today().isoformat()
