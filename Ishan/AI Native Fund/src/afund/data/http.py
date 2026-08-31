"""Shared HTTP plumbing for every Phase 1 data pipeline.

Provides:
  - make_session(): a requests.Session with a browser-like UA, gzip
    negotiation, and urllib3 Retry (exponential backoff on 429/5xx).
  - RateLimiter: a simple per-host minimum-interval limiter so pipelines stay
    polite to sources that specify rate_limit_seconds / max_requests_per_second
    in config/sources.yaml.
  - get(): a convenience wrapper combining session + rate limiting.
  - bootstrap_nse_session(): warms a session against nseindia.com so
    subsequent calls to nseindia.com JSON APIs succeed (NSE requires a
    same-session cookie before it will serve its API endpoints).
"""
from __future__ import annotations

import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

NSE_BASE_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}


def make_session(
    user_agent: str = DEFAULT_USER_AGENT,
    total_retries: int = 4,
    backoff_factor: float = 1.5,
    status_forcelist: tuple[int, ...] = (429, 500, 502, 503, 504),
) -> requests.Session:
    """Build a requests.Session with browser-like headers and retry/backoff.

    Retries are handled transparently by urllib3's Retry adapter: on 429/5xx
    it sleeps `backoff_factor * (2 ** (retry_count - 1))` seconds between
    attempts, up to `total_retries` times, before giving the response back
    to the caller (or raising if retries are exhausted).
    """
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            # Deliberately NOT advertising "br" (Brotli): requests/urllib3 can
            # only transparently decode Brotli responses if the optional
            # `brotli`/`brotlicffi` package is installed, which this project
            # does not depend on. Some sites (e.g. livemint.com) send Brotli
            # whenever it's offered, which then silently corrupts r.text for
            # any client without the decoder. gzip/deflate cover the polite
            # bandwidth-saving goal without that failure mode.
            "Accept-Encoding": "gzip, deflate",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=("GET", "POST", "HEAD"),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class RateLimiter:
    """Per-host minimum-interval rate limiter, thread-safe.

    Usage:
        limiter = RateLimiter()
        limiter.wait("screener.in", min_interval=2.0)
        # ... make the request ...
    """

    def __init__(self) -> None:
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, host_key: str, min_interval: float) -> None:
        """Block until at least `min_interval` seconds have passed since the
        last call for this host_key."""
        if min_interval <= 0:
            return
        with self._lock:
            last = self._last_call.get(host_key)
            now = time.monotonic()
            if last is not None:
                elapsed = now - last
                remaining = min_interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)
            self._last_call[host_key] = time.monotonic()


# Module-level shared limiter instance — pipelines can import this directly
# so rate limiting is coordinated across pipelines that hit the same host
# within one process.
default_rate_limiter = RateLimiter()


def get(
    session: requests.Session,
    url: str,
    *,
    host_key: str | None = None,
    min_interval: float = 0.0,
    rate_limiter: RateLimiter | None = None,
    timeout: float = 20.0,
    **kwargs: Any,
) -> requests.Response:
    """GET with optional per-host rate limiting applied before the request."""
    if host_key and min_interval:
        limiter = rate_limiter or default_rate_limiter
        limiter.wait(host_key, min_interval)
    return session.get(url, timeout=timeout, **kwargs)


def bootstrap_nse_session(session: requests.Session | None = None) -> requests.Session:
    """Warm a session against nseindia.com so subsequent API calls succeed.

    NSE serves its JSON APIs (www.nseindia.com/api/...) only to clients that
    already hold a same-session cookie. A plain GET to the homepage — even
    one that itself returns a non-200 (Akamai bot-check pages commonly
    respond 403) — is normally enough to set the cookie required by the API
    endpoints. We deliberately do not raise on a non-200 bootstrap response;
    we only need the cookie jar populated.
    """
    sess = session or make_session()
    sess.headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
    try:
        sess.get("https://www.nseindia.com", timeout=15)
    except requests.RequestException:
        pass  # best-effort warm-up; the caller's subsequent request will surface any real failure
    return sess
