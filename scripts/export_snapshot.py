"""Write the warm-start snapshot (snapshot/live/) from the live cache. Run after run_all.py in live
mode; the `refresh` workflow commits the result so the hosted dashboard starts with computed results."""

import json
import logging

import _bootstrap  # noqa: F401
from macro import warmstart


def main() -> int:
    logging.basicConfig(level=logging.WARNING)
    print(json.dumps(warmstart.export(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
