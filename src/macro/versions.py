"""Model versions. Every archived forecast carries the version of the model that produced it.

Rule (BRIEF §2.6): within an evaluation window (a calendar month) the code behind an archived
forecast is frozen. Bump the version here AND add a row to docs/MODEL_CHANGELOG.md; the archive
refuses to record a new version for a model inside a window that already holds rows from an
older version (the change ships in the next window). tests/test_governance.py checks that every
version below appears in the changelog.
"""

MODEL_VERSIONS: dict[str, str] = {
    "inflation": "0.1.0",
    "policy": "0.1.0",
    "fincond": "0.1.0",
    "curves": "0.1.0",
    "growth": "0.1.0",
    "recession": "0.1.0",
    "transmission": "0.1.0",
    "positioning": "0.1.0",
    "scenarios": "0.2.0",
    "regimes": "0.1.0",
    "history": "0.1.0",
    "markets": "0.3.0",
    "leading": "0.1.0",
    "stress_test": "0.3.0",
    "backtest": "0.2.0",
    "forecast_book": "0.1.0",
}
