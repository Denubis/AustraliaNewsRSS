"""Shared test helpers for discovery tests."""

from pathlib import Path

import httpx

from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.state import HttpCache

FIXTURES = Path(__file__).parent / "fixtures"


def make_mock_client(
    tmp_path: Path,
    responses: dict[str, tuple[int, str]] | None = None,
    head_responses: dict[str, int] | None = None,
    default_html: str = "",
) -> PoliteHttpClient:
    """Create a PoliteHttpClient with mock transport.

    responses: dict of URL -> (status, body) for GET requests.
    head_responses: dict of URL -> status code for HEAD requests
                    (default 200).
    default_html: fallback HTML for unmatched GET requests.
    """
    resp_map = responses or {}
    head_map = head_responses or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            status = head_map.get(str(request.url), 200)
            return httpx.Response(status)
        url_str = str(request.url)
        if url_str in resp_map:
            status, body = resp_map[url_str]
            return httpx.Response(status, text=body)
        return httpx.Response(200, text=default_html)

    cache = HttpCache(tmp_path / "cache.db")
    client = PoliteHttpClient(cache, delay_ms=0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers=client._client.headers,
    )
    return client
