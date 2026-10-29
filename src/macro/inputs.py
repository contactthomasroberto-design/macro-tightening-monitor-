"""Record which catalogue series a computation reads (thread-local, nestable).

`macro.results.load_or_compute` opens a recorder around each model bundle; `macro.data.get_series`
reports every series it returns. The stored result then knows its inputs, and is recomputed only
when one of them changes.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable

_LOCAL = threading.local()


def _stack() -> list[set[str]]:
    if not hasattr(_LOCAL, "stack"):
        _LOCAL.stack = []
    return _LOCAL.stack


def record(ids: str | Iterable[str]) -> None:
    """Add series ids to every open recorder of this thread (nested bundles feed their parents)."""
    ids = {ids} if isinstance(ids, str) else set(ids)
    for s in _stack():
        s |= ids


class recording:  # noqa: N801  (context manager)
    def __enter__(self) -> set[str]:
        self.ids: set[str] = set()
        _stack().append(self.ids)
        return self.ids

    def __exit__(self, *exc) -> None:
        _stack().pop()
