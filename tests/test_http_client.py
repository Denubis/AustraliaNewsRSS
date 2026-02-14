"""Tests for australianewsrss.http_client PoliteHttpClient (AC5 criteria)."""

import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from australianewsrss.http_client import HttpError, PoliteHttpClient
from australianewsrss.state import HttpCache


def _make_client(
    tmp_path: Path,
    handler: Callable[[httpx.Request], httpx.Response],
    delay_ms: int = 0,
) -> PoliteHttpClient:
    """Build a PoliteHttpClient with a mock transport for testing.

    Replaces the internal httpx.Client with one backed by MockTransport,
    preserving the original client's headers (including User-Agent).
    """
    cache = HttpCache(tmp_path / "cache.db")
    client = PoliteHttpClient(cache, delay_ms=delay_ms)
    transport = httpx.MockTransport(handler)
    client._client = httpx.Client(transport=transport, headers=client._client.headers)
    return client


# ---------------------------------------------------------------------------
# AC5.1 - ETag / Conditional GET
# ---------------------------------------------------------------------------


class TestETagConditionalGet:
    """ETag caching and If-None-Match conditional GET (AC5.1)."""

    def test_etag_from_200_is_stored_in_cache(self, tmp_path: Path) -> None:
        """First GET returns 200 with ETag; ETag is persisted in HttpCache."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, text="<rss>content</rss>", headers={"ETag": '"abc123"'}
            )

        client = _make_client(tmp_path, handler)
        body, was_cached = client.get("https://example.com/feed")

        assert body == "<rss>content</rss>"
        assert was_cached is False

        # Verify ETag was stored in the cache
        cache = HttpCache(tmp_path / "cache.db")
        etag, data = cache.get("https://example.com/feed")
        assert etag == '"abc123"'
        assert data == "<rss>content</rss>"

    def test_subsequent_request_sends_if_none_match(self, tmp_path: Path) -> None:
        """After caching an ETag, next request includes If-None-Match header."""
        captured_requests: list[httpx.Request] = []
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            captured_requests.append(request)
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    200,
                    text="<rss>content</rss>",
                    headers={"ETag": '"etag-v1"'},
                )
            # Second request: 304 Not Modified
            return httpx.Response(304)

        client = _make_client(tmp_path, handler)

        # First request - populates cache
        client.get("https://example.com/feed")

        # Second request - should send If-None-Match
        client.get("https://example.com/feed")

        assert len(captured_requests) == 2
        second_req = captured_requests[1]
        assert second_req.headers.get("if-none-match") == '"etag-v1"'

    def test_304_returns_cached_content_with_was_cached_true(
        self, tmp_path: Path
    ) -> None:
        """On 304, client returns cached body and was_cached=True."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    200,
                    text="<rss>original</rss>",
                    headers={"ETag": '"etag-v1"'},
                )
            return httpx.Response(304)

        client = _make_client(tmp_path, handler)

        # First request populates cache
        body1, cached1 = client.get("https://example.com/feed")
        assert cached1 is False
        assert body1 == "<rss>original</rss>"

        # Second request gets 304
        body2, cached2 = client.get("https://example.com/feed")
        assert cached2 is True
        assert body2 == "<rss>original</rss>"

    def test_etag_end_to_end_flow(self, tmp_path: Path) -> None:
        """Full cycle: 200 with ETag -> cache -> If-None-Match -> 304 -> cached body."""
        captured_requests: list[httpx.Request] = []
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            captured_requests.append(request)
            call_count += 1
            if call_count == 1:
                return httpx.Response(
                    200,
                    text="<rss>data</rss>",
                    headers={"ETag": '"end-to-end"'},
                )
            return httpx.Response(304)

        client = _make_client(tmp_path, handler)

        # Step 1: initial fetch
        body1, cached1 = client.get("https://example.com/feed")
        assert body1 == "<rss>data</rss>"
        assert cached1 is False

        # Step 2: ETag stored in cache
        cache = HttpCache(tmp_path / "cache.db")
        etag, data = cache.get("https://example.com/feed")
        assert etag == '"end-to-end"'
        assert data == "<rss>data</rss>"

        # Step 3: second fetch sends If-None-Match, gets 304
        body2, cached2 = client.get("https://example.com/feed")
        assert body2 == "<rss>data</rss>"
        assert cached2 is True

        # Step 4: verify If-None-Match was sent
        assert captured_requests[1].headers.get("if-none-match") == '"end-to-end"'


# ---------------------------------------------------------------------------
# AC5.2 - Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimiting:
    """Per-domain rate limiting (AC5.2)."""

    def test_same_domain_requests_are_delayed(self, tmp_path: Path) -> None:
        """Two rapid requests to the same domain must be >= 300ms apart."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok", headers={"ETag": '"x"'})

        client = _make_client(tmp_path, handler, delay_ms=300)

        start = time.monotonic()
        client.get("https://example.com/feed1")
        client.get("https://example.com/feed2")
        elapsed = time.monotonic() - start

        assert elapsed >= 0.3, f"Expected >= 300ms delay, got {elapsed * 1000:.0f}ms"

    def test_different_domains_are_not_delayed(self, tmp_path: Path) -> None:
        """Requests to different domains are not delayed."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok", headers={"ETag": '"x"'})

        client = _make_client(tmp_path, handler, delay_ms=300)

        start = time.monotonic()
        client.get("https://alpha.com/feed")
        client.get("https://beta.com/feed")
        elapsed = time.monotonic() - start

        # Two requests to different domains should complete well under 300ms
        # (accounting for some overhead, but never the 300ms domain delay)
        assert elapsed < 0.3, (
            f"Different-domain requests took {elapsed * 1000:.0f}ms, "
            "suggesting they were incorrectly rate-limited"
        )


# ---------------------------------------------------------------------------
# AC5.3 - User-Agent
# ---------------------------------------------------------------------------


class TestUserAgent:
    """Custom User-Agent header (AC5.3)."""

    _EXPECTED_UA = (
        "AustraliaNewsRSS/0.1 "
        "(+https://github.com/BrianBallworthy/AustraliaNewsRSS; feed aggregation)"
    )

    def test_get_request_includes_user_agent(self, tmp_path: Path) -> None:
        """GET requests include the correct User-Agent header."""
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, text="ok", headers={"ETag": '"x"'})

        client = _make_client(tmp_path, handler)
        client.get("https://example.com/feed")

        assert len(captured_requests) == 1
        assert captured_requests[0].headers["user-agent"] == self._EXPECTED_UA

    def test_head_request_includes_user_agent(self, tmp_path: Path) -> None:
        """HEAD requests include the correct User-Agent header."""
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200)

        client = _make_client(tmp_path, handler)
        client.head("https://example.com/feed")

        assert len(captured_requests) == 1
        assert captured_requests[0].headers["user-agent"] == self._EXPECTED_UA


# ---------------------------------------------------------------------------
# AC5.4 - Retry-After
# ---------------------------------------------------------------------------


class TestRetryAfter:
    """Retry-After handling for 429 responses (AC5.4)."""

    def test_429_with_retry_after_retries_successfully(self, tmp_path: Path) -> None:
        """429 with Retry-After triggers wait then retry; 200 succeeds."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, headers={"Retry-After": "1"})
            return httpx.Response(200, text="success", headers={"ETag": '"retry-ok"'})

        client = _make_client(tmp_path, handler)

        start = time.monotonic()
        body, was_cached = client.get("https://example.com/feed")
        elapsed = time.monotonic() - start

        assert body == "success"
        assert was_cached is False
        assert call_count == 2
        assert elapsed >= 1.0, (
            f"Expected >= 1s delay for Retry-After, got {elapsed:.2f}s"
        )

    def test_429_with_http_date_retry_after(self, tmp_path: Path) -> None:
        """When Retry-After contains HTTP-date, client computes delay and retries."""
        from datetime import UTC, datetime, timedelta
        from email.utils import format_datetime

        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Set retry_time to 2 seconds in the future (accounts for parsing delay)
                retry_time = datetime.now(UTC) + timedelta(seconds=2)
                return httpx.Response(
                    429,
                    headers={"Retry-After": format_datetime(retry_time)},
                )
            return httpx.Response(200, text="ok", headers={"ETag": '"http-date-ok"'})

        client = _make_client(tmp_path, handler)

        start = time.monotonic()
        body, was_cached = client.get("http://example.com/feed.xml")
        elapsed = time.monotonic() - start

        assert body == "ok"
        assert was_cached is False
        assert call_count == 2
        # Verify delay occurred (at least 1.2s to ensure HTTP-date was parsed)
        assert elapsed >= 1.2, (
            f"Expected >= 1.2s delay for HTTP-date Retry-After, got {elapsed:.2f}s"
        )


# ---------------------------------------------------------------------------
# HEAD request
# ---------------------------------------------------------------------------


class TestHeadRequest:
    """HEAD request returns status code (no body)."""

    def test_head_returns_200(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200)

        client = _make_client(tmp_path, handler)
        status = client.head("https://example.com/feed")
        assert status == 200

    def test_head_returns_404(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        client = _make_client(tmp_path, handler)
        status = client.head("https://example.com/missing")
        assert status == 404


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """HttpError raised on non-retryable failures."""

    def test_404_raises_http_error(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        client = _make_client(tmp_path, handler)

        with pytest.raises(HttpError) as exc_info:
            client.get("https://example.com/missing")

        assert exc_info.value.status_code == 404
        assert exc_info.value.url == "https://example.com/missing"


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    """Context manager properly closes client."""

    def test_context_manager_closes_client(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="ok", headers={"ETag": '"x"'})

        cache = HttpCache(tmp_path / "cache.db")
        with PoliteHttpClient(cache, delay_ms=0) as client:
            transport = httpx.MockTransport(handler)
            client._client = httpx.Client(
                transport=transport, headers=client._client.headers
            )
            body, _ = client.get("https://example.com/feed")
            assert body == "ok"

        # After exiting context, the underlying client should be closed.
        # httpx.Client raises RuntimeError when used after close.
        with pytest.raises(RuntimeError):
            client._client.get("https://example.com/feed")
