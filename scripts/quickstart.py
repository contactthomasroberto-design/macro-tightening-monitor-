"""One-shot setup from a plain Python prompt (no terminal, no git needed).

Private repository: download the ZIP from GitHub in the browser (branch claude/ecstatic-cannon-fztm87,
Code -> Download ZIP), unzip it, then at the Python prompt (>>>):

    p = r"C:/path/to/unzipped/folder/scripts/quickstart.py"; exec(open(p).read(), {"__file__": p, "__name__": "__main__"})

Public repository: from the Python prompt (>>>), paste:

    import urllib.request; exec(urllib.request.urlopen("https://raw.githubusercontent.com/contactthomasroberto-design/macro-tightening-monitor-/claude/ecstatic-cannon-fztm87/scripts/quickstart.py").read())

It downloads the project into ~/Documents/macro-tightening-monitor, installs the dependencies into
the current Python, computes the demo (synthetic) data, and opens the dashboard in the browser.
Running it again skips the steps already done.
"""

import io
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

BRANCH = "claude/ecstatic-cannon-fztm87"
ZIP_URL = f"https://github.com/contactthomasroberto-design/macro-tightening-monitor-/archive/refs/heads/{BRANCH}.zip"
HOME = Path.home() / "Documents" if (Path.home() / "Documents").exists() else Path.home()
_here = Path(globals().get("__file__", "")).resolve()
if globals().get("__file__") and (_here.parents[1] / "app" / "streamlit_app.py").exists():
    TARGET = _here.parents[1]  # run from an unzipped copy of the project: use it in place
else:
    TARGET = Path(os.environ.get("MTM_DIR", HOME / "macro-tightening-monitor"))
PACKAGES = [
    "pandas",
    "numpy",
    "scipy",
    "statsmodels",
    "scikit-learn",
    "plotly",
    "streamlit",
    "requests",
    "PyYAML",
    "pydantic",
    "fpdf2",
    "openpyxl",
    "xlrd",
    "kaleido",
]


def step(msg):
    print(f"\n=== {msg}", flush=True)


def run(args, **kw):
    print("  >", " ".join(str(a) for a in args), flush=True)
    return subprocess.run(args, **kw)


def download():
    if (TARGET / "app" / "streamlit_app.py").exists():
        print(f"  project already in {TARGET}")
        return
    step(f"Downloading the project into {TARGET}")
    data = urllib.request.urlopen(ZIP_URL).read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = z.namelist()[0].split("/")[0]
        z.extractall(TARGET.parent)
    (TARGET.parent / root).rename(TARGET)


def install():
    step(f"Installing dependencies into this Python ({sys.version.split()[0]})")
    pinned = sys.version_info[:2] <= (3, 13)
    if pinned:
        r = run([sys.executable, "-m", "pip", "install", "-r", str(TARGET / "requirements.txt")])
    else:
        print("  Python newer than 3.13: installing the latest versions instead of the pinned ones")
        r = run([sys.executable, "-m", "pip", "install", *PACKAGES])
    if r.returncode != 0:
        raise SystemExit(
            "\nInstallation failed. Most likely some packages have no build yet for this Python version.\n"
            "Install Python 3.13 from https://www.python.org/downloads/ and run this script from Python 3.13."
        )


def compute():
    env = {**os.environ, "MACRO_MODE": "demo", "PYTHONPATH": str(TARGET / "src")}
    marker = TARGET / "data" / "cache" / "results" / "demo"
    if marker.exists() and any(marker.iterdir()):
        print("  demo results already computed")
        return env
    step("Computing the demo data and models (about 5 minutes the first time)")
    for script in ("update_data.py", "run_all.py"):
        r = run([sys.executable, str(TARGET / "scripts" / script)], cwd=TARGET, env=env)
        if r.returncode != 0:
            raise SystemExit(f"{script} failed: copy the messages above and send them.")
    return env


def launch(env):
    step("Starting the dashboard at http://localhost:8501 (close this Python window to stop it)")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(TARGET / "app" / "streamlit_app.py"),
            "--server.headless",
            "true",
        ],
        cwd=TARGET,
        env=env,
    )
    time.sleep(6)
    webbrowser.open("http://localhost:8501")
    return proc


download()
install()
_env = compute()
dashboard = launch(_env)
print("\nDashboard running. To stop it: dashboard.terminate()")
