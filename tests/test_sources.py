"""Source adapters against mocked HTTP payloads shaped like the real endpoints."""

import io
import json
from unittest.mock import patch

import pandas as pd
import pytest

from macro.config import catalogue
from macro.data import sources
from macro.data.http import SourceError


class FakeResp:
    def __init__(self, text="", content=b"", js=None):
        self.text = text
        self.content = content
        self._js = js
        self.status_code = 200

    def json(self):
        return self._js


def test_fred_csv(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    csv = "observation_date,DGS10\n2024-01-02,3.95\n2024-01-03,.\n2024-01-04,4.0\n"
    with patch.object(sources, "get", return_value=FakeResp(text=csv)) as g:
        df = sources.fetch_fred(catalogue().get("DGS10"))
    assert g.call_args.args[1] == {"id": "DGS10"}
    assert df["value"].tolist() == [3.95, 4.0]
    assert df["vintage_date"].isna().all()


def test_fred_api_vintage(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "k")
    js = {"observations": [{"date": "2024-01-01", "value": "308.4"}, {"date": "2024-02-01", "value": "."}]}
    with patch.object(sources, "get", return_value=FakeResp(js=js)) as g:
        df = sources.fetch_fred(catalogue().get("CPIAUCSL"), vintage="2024-03-12")
    assert g.call_args.args[1]["realtime_start"] == "2024-03-12"
    assert df["value"].tolist() == [308.4]
    assert df["vintage_date"].iloc[0] == pd.Timestamp("2024-03-12")


def test_fred_vintage_without_key_is_explicit(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    with pytest.raises(SourceError, match="latest-vintage"):
        sources.fetch_fred(catalogue().get("CPIAUCSL"), vintage="2024-03-12")


def test_ecb_csv():
    csv = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nICP.M.U2,M,2024-01,125.1\nICP.M.U2,M,2024-02,125.9\n"
    with patch.object(sources, "get", return_value=FakeResp(text=csv)) as g:
        df = sources.fetch_ecb(catalogue().get("EA_HICP"))
    assert g.call_args.args[0].endswith("/ICP/M.U2.N.000000.4.INX")
    assert df["date"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")]


def test_yahoo_chart():
    js = {
        "chart": {
            "result": [
                {
                    "timestamp": [1704205800, 1704292200],
                    "indicators": {
                        "quote": [{"close": [4742.8, None]}],
                        "adjclose": [{"adjclose": [4742.8, 4704.8]}],
                    },
                }
            ]
        }
    }
    with patch.object(sources, "get", return_value=FakeResp(js=js)):
        df = sources.fetch_yahoo(catalogue().get("SPX"))
    assert df["value"].tolist() == [4742.8, 4704.8]


def test_yahoo_bad_payload():
    with (
        patch.object(sources, "get", return_value=FakeResp(js={"chart": {"result": None}})),
        pytest.raises(SourceError),
    ):
        sources.fetch_yahoo(catalogue().get("SPX"))


def test_cftc_net_positions():
    rows = [
        {
            "report_date_as_yyyy_mm_dd": "2024-01-02T00:00:00.000",
            "market_and_exchange_names": "UST 10Y NOTE - CBOT",
            "lev_money_positions_long_all": "500",
            "lev_money_positions_short_all": "1500",
        },
        {
            "report_date_as_yyyy_mm_dd": "2024-01-09T00:00:00.000",
            "market_and_exchange_names": "UST 10Y NOTE - CBOT",
            "lev_money_positions_long_all": "600",
            "lev_money_positions_short_all": "1400",
        },
    ]
    with patch.object(sources, "get", return_value=FakeResp(js=rows)):
        df = sources.fetch_cftc(catalogue().get("TFF_UST10_LEV"))
    assert df["value"].tolist() == [-1000.0, -800.0]


def test_spf_four_quarter_average():
    buf = io.BytesIO()
    df = pd.DataFrame(
        {
            "YEAR": [2024],
            "QUARTER": [1],
            "CPI1": [3.0],
            "CPI2": [3.0],
            "CPI3": [2.0],
            "CPI4": [2.0],
            "CPI5": [2.0],
            "CPI6": [2.0],
        }
    )
    with pd.ExcelWriter(buf) as xw:
        df.to_excel(xw, sheet_name="CPI", index=False)
    out = sources._parse_spf(buf.getvalue(), "CPI:4q-ahead")
    assert out["value"].iloc[0] == pytest.approx(2.0)
    assert out["date"].iloc[0] == pd.Timestamp("2024-01-01")


def test_research_file_manual_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "MANUAL_DIR", tmp_path)
    (tmp_path / "CIE.csv").write_text("date,value\n2024-01-01,2.1\n2024-04-01,2.0\n")
    df = sources.fetch_research_file(catalogue().get("CIE"))
    assert df["value"].tolist() == [2.1, 2.0]


def test_research_file_without_url_explains(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "MANUAL_DIR", tmp_path)
    with pytest.raises(SourceError, match="data/manual/FCIG_1Y.csv"):
        sources.fetch_research_file(catalogue().get("FCIG_1Y"))


def test_http_error_raises_sourceerror():
    from macro.data import http

    class R:
        status_code = 404
        url = "u"

    with patch.object(http, "session") as s:
        s.return_value.get.return_value = R()
        with pytest.raises(SourceError, match="HTTP 404"):
            http.get("u")
    json.dumps({})  # keep json import used for clarity of payload shapes
