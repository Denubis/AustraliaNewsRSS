"""Polite HTTP client with ETag caching, rate limiting, and retry support."""

import time
from urllib.parse import urlparse

import httpx

from australianewsrss.state import HttpCache

_DEFAULT_USER_AGENT = (
    "AustraliaNewsRSS/0.1 "
    "(+https://github.com/Denubis/AustraliaNewsRSS; feed aggregation)"
)


class HttpError(Exception):
    """Raised when an HTTP request fails with a non-retryable error."""

    def __init__(self, url: str, status_code: int):
        self.url = url
        self.status_code = status_code
        super().__init__(f"HTTP {status_code} for {url}")


class PoliteHttpClient:
    def __init__(
        self,
        cache: HttpCache,
        delay_ms: int = 300,
        user_agent: str | None = None,
        timeout: float = 30.0,
    ):
        self._cache = cache
        self._delay_ms = delay_ms
        self._domain_timestamps: dict[str, float] = {}
        self._client = httpx.Client(
            headers={"User-Agent": user_agent or _DEFAULT_USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )

    def _wait_for_domain(self, url: str) -> None:
        """Enforce per-domain rate limiting (AC5.2)."""
        domain = urlparse(url).netloc
        now = time.monotonic()
        last = self._domain_timestamps.get(domain)
        if last is not None:
            elapsed = now - last
            required = self._delay_ms / 1000.0
            if elapsed < required:
                time.sleep(required - elapsed)
        self._domain_timestamps[domain] = time.monotonic()

    def get(self, url: str) -> tuple[str, bool]:
        """Fetch URL with conditional GET support.

        Returns (response_body, was_cached).

        AC5.1: Sends If-None-Match when ETag cached, returns cached on 304.
        AC5.2: Per-domain rate limiting.
        AC5.3: Custom User-Agent.
        AC5.4: Retry-After handling on 429.

        Raises HttpError for 4xx/5xx (except 429 which is retried).
        """
        self._wait_for_domain(url)

        # Check cache for ETag (AC5.1)
        etag, cached_data = self._cache.get(url)
        headers = {}
        if etag:
            headers["If-None-Match"] = etag

        response = self._client.get(url, headers=headers)

        # 304 Not Modified - return cached (AC5.1)
        if response.status_code == 304 and cached_data is not None:
            return cached_data, True

        # 429 Too Many Requests - respect Retry-After (AC5.4)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                delay = self._parse_retry_after(retry_after)
                time.sleep(delay)
            self._wait_for_domain(url)
            response = self._client.get(url, headers=headers)
            if response.status_code == 429:
                raise HttpError(url, 429)

        # Success - cache ETag if present
        if response.status_code == 200:
            resp_etag = response.headers.get("ETag")
            if resp_etag:
                self._cache.put(url, resp_etag, response.text)
            return response.text, False

        # Error
        raise HttpError(url, response.status_code)

    def head(self, url: str) -> int:
        """HEAD request returning status code. Respects rate limiting."""
        self._wait_for_domain(url)
        response = self._client.head(url, follow_redirects=True)
        return response.status_code

    def _parse_retry_after(self, value: str) -> float:
        """Parse Retry-After header value.

        Supports both integer seconds and HTTP-date format.
        """
        try:
            return float(value)
        except ValueError:
            pass
        # Try HTTP-date format
        from email.utils import parsedate_to_datetime

        try:
            retry_dt = parsedate_to_datetime(value)
            from datetime import UTC, datetime

            delay = (retry_dt - datetime.now(UTC)).total_seconds()
            return max(0.0, delay)
        except ValueError, TypeError:
            return 1.0  # Default fallback

    def close(self) -> None:
        """Close underlying httpx.Client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
