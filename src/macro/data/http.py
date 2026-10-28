"""HTTP access with retries and exponential backoff. Every source goes through `get`,
which is the single point mocked in tests."""

from __future__ import annotations

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("macro.data")

USER_AGENT = "macro-tightening-monitor/0.1 (educational research; +https://github.com/contactthomasroberto-design/macro-tightening-monitor-)"
TIMEOUT = 30

_session: requests.Session | None = None


class SourceError(RuntimeError):
    """Raised when a source cannot deliver a series (network, HTTP status, parsing)."""


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(
            total=4,
            backoff_factor=2.0,  # 0, 2, 4, 8 s
            # 429 (rate limit) is not retried: waiting out a Retry-After header blocked whole pages
            # for minutes; the catalogue fallback or the cached copy is used instead.
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET",),
            raise_on_status=False,
            respect_retry_after_header=False,
        )
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers.update({"User-Agent": USER_AGENT})
        _session = s
    return _session


def get(url: str, params: dict | None = None) -> requests.Response:
    try:
        r = session().get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SourceError(f"network error for {url}: {exc}") from exc
    if r.status_code != 200:
        raise SourceError(f"HTTP {r.status_code} for {r.url}")
    return r
