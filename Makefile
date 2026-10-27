PY ?= python
export PYTHONHASHSEED := 0

.PHONY: install demo demo-reports live test test-live lint typecheck weekly monthly figures app evaluate clean

install:
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e . --no-deps

## Full offline pipeline on synthetic data (CI-safe)
demo:
	MACRO_MODE=demo $(PY) scripts/update_data.py
	MACRO_MODE=demo $(PY) scripts/run_all.py

## Demo PDFs (SYNTHETIC watermark on every page; for checking the layout only)
demo-reports:
	MACRO_MODE=demo $(PY) scripts/weekly_monitor.py --allow-demo
	MACRO_MODE=demo $(PY) scripts/monthly_view.py --allow-demo

## Live refresh: real data sources (FRED_API_KEY optional, enables ALFRED vintages)
live:
	MACRO_MODE=live $(PY) scripts/update_data.py
	MACRO_MODE=live $(PY) scripts/run_all.py
	MACRO_MODE=live $(PY) scripts/update_readme.py

test:
	MACRO_MODE=demo $(PY) -m pytest

test-live:
	MACRO_MODE=live $(PY) -m pytest -m live

lint:
	$(PY) -m ruff check src app scripts tests
	$(PY) -m ruff format --check src app scripts tests

typecheck:
	$(PY) -m mypy

weekly:
	$(PY) scripts/weekly_monitor.py

monthly:
	$(PY) scripts/monthly_view.py

figures:
	$(PY) scripts/export_figures.py

evaluate:
	$(PY) scripts/evaluate_archive.py

app:
	$(PY) -m streamlit run app/streamlit_app.py

clean:
	rm -rf data/cache .pytest_cache .ruff_cache .mypy_cache out
