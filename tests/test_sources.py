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
    csv = "KEY,FREQ,TIME_PERIOD,OBS_VALUE\nFM.D,D,2024-01-02,4.0\nFM.D,D,2024-01-03,4.0\n"
    with patch.object(sources, "get", return_value=FakeResp(text=csv)) as g:
        df = sources.fetch_ecb(catalogue().get("EA_DFR"))
    assert g.call_args.args[0].endswith("/FM/D.U2.EUR.4F.KR.DFR.LEV")
    assert df["date"].tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]


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
            "lev_money_positions_long": "500",
            "lev_money_positions_short": "1500",
        },
        {
            "report_date_as_yyyy_mm_dd": "2024-01-09T00:00:00.000",
            "lev_money_positions_long": "600",
            "lev_money_positions_short": "1400",
        },
    ]
    with patch.object(sources, "get", return_value=FakeResp(js=rows)) as g:
        df = sources.fetch_cftc(catalogue().get("TFF_UST10_LEV"))
    assert df["value"].tolist() == [-1000.0, -800.0]
    assert "cftc_contract_market_code='043602'" in g.call_args.args[1]["$where"]


def _jsonstat(times, values):
    return {
        "dimension": {"time": {"category": {"index": {t: i for i, t in enumerate(times)}}}},
        "value": {str(i): v for i, v in enumerate(values) if v is not None},
    }


def test_eurostat_hicp_jsonstat():
    js = _jsonstat(["2025-01", "2025-02", "2025-03"], [99.0, None, 100.5])
    with patch.object(sources, "get", return_value=FakeResp(js=js)):
        df = sources.fetch_eurostat(catalogue().get("EA_HICP"))
    assert df["date"].tolist() == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-03-01")]
    assert df["value"].tolist() == [99.0, 100.5]


def test_eurostat_technical_recession():
    # q/q: Q2 -, Q3 -, Q4 +, Q1 - (isolated): only Q2-Q3 2020 are a technical recession
    js = _jsonstat(["2020-Q1", "2020-Q2", "2020-Q3", "2020-Q4", "2021-Q1"], [100, 99, 98, 99, 98.5])
    with patch.object(sources, "get", return_value=FakeResp(js=js)):
        df = sources.fetch_eurostat(catalogue().get("EUROREC")).set_index("date")["value"]
    assert df.index[0] == pd.Timestamp("2020-01-01") and df.index[-1] == pd.Timestamp("2021-03-01")
    assert df[df == 1].index.tolist() == list(pd.date_range("2020-04-01", "2020-09-01", freq="MS"))


def test_bis_csv():
    text = "FREQ,REF_AREA,TIME_PERIOD,OBS_VALUE\nM,JP,2024-01,105.1\nM,JP,2024-02,105.3\n"
    with patch.object(sources, "get", return_value=FakeResp(text=text)):
        df = sources.fetch_bis(catalogue().get("JP_CPI"))
    assert df["value"].tolist() == [105.1, 105.3]


def test_spf_growth_four_quarter_and_current():
    buf = io.BytesIO()
    df = pd.DataFrame(
        {"YEAR": [2024], "QUARTER": [1], "drgdp2": [1.0], **{f"drgdp{k}": [2.0] for k in range(3, 7)}}
    )
    with pd.ExcelWriter(buf) as xw:
        df.to_excel(xw, sheet_name="RGDP", index=False)
    four = sources._parse_spf_growth(buf.getvalue(), "RGDP:4q")
    cq = sources._parse_spf_growth(buf.getvalue(), "RGDP:cq")
    assert four["value"].iloc[0] == pytest.approx(2.0)
    assert cq["value"].iloc[0] == 1.0
    assert four["date"].iloc[0] == pd.Timestamp("2024-01-01")


def test_fallback_source_used_when_primary_fails():
    spec = catalogue().get("SPX")
    fred = pd.DataFrame({"date": pd.to_datetime(["2024-01-02"]), "value": [4700.0], "vintage": [None]})
    with (
        patch.dict(
            sources.FETCHERS,
            {"yahoo": lambda s, v: (_ for _ in ()).throw(SourceError("429")), "fred": lambda s, v: fred},
        ),
    ):
        df = sources.fetch(spec)
    assert df["value"].tolist() == [4700.0]
    assert "fallback" in df.attrs["source"]


def test_research_file_manual_drop(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "MANUAL_DIR", tmp_path)
    (tmp_path / "CIE.csv").write_text("date,value\n2024-01-01,2.1\n2024-04-01,2.0\n")
    df = sources.fetch_research_file(catalogue().get("CIE"))
    assert df["value"].tolist() == [2.1, 2.0]


def test_research_file_without_url_explains(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, "MANUAL_DIR", tmp_path)
    with pytest.raises(SourceError, match="data/manual/CIE.csv"):
        sources.fetch_research_file(catalogue().get("CIE"))


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


def test_boj_api_pages_and_monthly_dates():
    p1 = {
        "STATUS": 200,
        "NEXTPOSITION": 3,
        "RESULTSET": [{"VALUES": {"SURVEY_DATES": [202401, 202402], "VALUES": [0.1, None]}}],
    }
    p2 = {
        "STATUS": 200,
        "NEXTPOSITION": None,
        "RESULTSET": [{"VALUES": {"SURVEY_DATES": [202403], "VALUES": [0.2]}}],
    }
    with patch.object(sources, "get", side_effect=[FakeResp(js=p1), FakeResp(js=p2)]) as g:
        df = sources.fetch_boj(catalogue().get("JP_POLICY"))
    assert df["date"].tolist() == [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-03-01")]
    assert df["value"].tolist() == [0.1, 0.2]
    assert g.call_args_list[1].args[1]["startPosition"] == 3


def test_boj_api_error_raises():
    bad = FakeResp(js={"STATUS": 400, "MESSAGE": "bad code"})
    with patch.object(sources, "get", return_value=bad), pytest.raises(SourceError, match="bad code"):
        sources.fetch_boj(catalogue().get("JP_POLICY"))


def test_mof_jgb_history_plus_current_month():
    hist = "Interest Rate,,,(Unit : %)\nDate,1Y,2Y,10Y\n2026/9/29,1.6,1.9,3.0\n2026/9/30,1.6,1.9,-\n"
    cur = "Interest Rate (October 2026),,,(Unit : %)\nDate,1Y,2Y,10Y\n2026/10/1,1.7,1.9,3.09\n,,,\n"
    with patch.object(sources, "get", side_effect=[FakeResp(text=hist), FakeResp(text=cur)]):
        df = sources.fetch_mof_jgb(catalogue().get("JP_10Y"))
    assert df["date"].tolist() == [pd.Timestamp("2026-09-29"), pd.Timestamp("2026-10-01")]
    assert df["value"].tolist() == [3.0, 3.09]


def test_mpt_interpolates_twelve_months_ahead():
    buf = io.BytesIO()
    d = pd.DataFrame(
        {
            "date": ["2026-01-01"] * 3,
            "reference_start": ["2026-07-01", "2027-01-01", "2027-07-01"],
            "target_range": ["375bps - 400bps"] * 3,
            "field": ["Rate: mean"] * 3,
            "value": [400.0, 420.0, 440.0],
        }
    )
    with pd.ExcelWriter(buf) as xw:
        d.to_excel(xw, sheet_name="DATA", index=False)
    out = sources._parse_mpt(buf.getvalue(), "12m")
    assert out["value"].iloc[0] == pytest.approx(4.2, abs=0.01)


def test_market_priced_prefers_fresh_series(monkeypatch):
    from macro import panels

    s = pd.Series([4.5], index=[pd.Timestamp(panels.reference_today())])
    monkeypatch.setattr(panels, "try_series", lambda sid: s)
    got = panels.market_priced("fed", {"value": 3.0, "source": "manual", "as_of": "2020-01-01"})
    assert got["value"] == 4.5 and "Atlanta" in got["source"]
    stale = pd.Series([4.5], index=[pd.Timestamp(panels.reference_today()) - pd.Timedelta(days=60)])
    monkeypatch.setattr(panels, "try_series", lambda sid: stale)
    assert panels.market_priced("fed", {"value": 3.0})["value"] == 3.0
    assert panels.market_priced("ecb", None) is None


def test_yahoo_circuit_breaker_after_rate_limit(monkeypatch):
    monkeypatch.setattr(sources, "_yahoo_blocked_until", None)
    calls = []

    def rate_limited(url, params=None):
        calls.append(url)
        raise SourceError(f"HTTP 429 for {url}")

    with patch.object(sources, "get", side_effect=rate_limited):
        with pytest.raises(SourceError, match="429"):
            sources.fetch_yahoo(catalogue().get("SOX"))
        with pytest.raises(SourceError, match="paused"):
            sources.fetch_yahoo(catalogue().get("NVDA"))
    assert len(calls) == 1  # the second series did not hit Yahoo
    monkeypatch.setattr(sources, "_yahoo_blocked_until", None)
