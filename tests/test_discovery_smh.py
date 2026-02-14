"""Tests for SMH feed discovery.

Covers acceptance criteria:
- AC1.4: All 17 static feed paths returned; navigation slug discovery
- AC1.5: Dead feeds recorded (not dropped) on 404
"""

from pathlib import Path

import httpx

from australianewsrss.discovery.smh import (
    BASE_URL,
    HOMEPAGE_URL,
    STATIC_FEED_PATHS,
    _extract_nav_slugs,
    discover_feeds,
)
from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.state import FeedRegistry, HttpCache

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mock_client(
    tmp_path: Path,
    responses: dict[str, tuple[int, str]] | None = None,
    head_responses: dict[str, int] | None = None,
    default_html: str = "",
) -> PoliteHttpClient:
    """Create a PoliteHttpClient with mock transport.

    responses: dict of URL -> (status, body) for GET requests.
    head_responses: dict of URL -> status code for HEAD requests (default 200).
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


# ---------------------------------------------------------------------------
# Unit tests for _extract_nav_slugs
# ---------------------------------------------------------------------------


class TestExtractNavSlugs:
    """Unit tests for the navigation slug extraction helper."""

    def test_extracts_section_slugs(self) -> None:
        html = (FIXTURES / "smh_homepage.html").read_text()
        slugs = _extract_nav_slugs(html)
        assert "national" in slugs
        assert "business" in slugs
        assert "opinion" in slugs
        assert "entertainment" in slugs

    def test_excludes_login_slug(self) -> None:
        html = (FIXTURES / "smh_homepage.html").read_text()
        slugs = _extract_nav_slugs(html)
        assert "login" not in slugs

    def test_returns_four_slugs_from_fixture(self) -> None:
        """Fixture has 5 nav links; 'login' is excluded, leaving 4."""
        html = (FIXTURES / "smh_homepage.html").read_text()
        slugs = _extract_nav_slugs(html)
        assert len(slugs) == 4

    def test_empty_html_returns_empty(self) -> None:
        slugs = _extract_nav_slugs("<html><body></body></html>")
        assert slugs == set()

    def test_single_char_slug_excluded(self) -> None:
        """Slugs of length 1 are filtered out."""
        html = '<html><body><a href="/x/">X</a></body></html>'
        slugs = _extract_nav_slugs(html)
        assert slugs == set()


# ---------------------------------------------------------------------------
# AC1.4: All 17 static feed paths returned
# ---------------------------------------------------------------------------


def test_all_static_feeds_returned(tmp_path: Path) -> None:
    """All 17 static feed paths produce discovered feeds."""
    # Homepage returns empty nav so no dynamic feeds added
    empty_html = "<html><body></body></html>"
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, empty_html),
    }

    client = _make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    assert len(feeds) == len(STATIC_FEED_PATHS)
    feed_urls = {f.url for f in feeds}
    for path in STATIC_FEED_PATHS:
        expected = f"{BASE_URL}{path}"
        assert expected in feed_urls, f"Missing static feed: {expected}"


def test_static_feeds_all_active_when_head_200(tmp_path: Path) -> None:
    """All static feeds are active when HEAD returns 200."""
    empty_html = "<html><body></body></html>"
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, empty_html),
    }

    client = _make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    for feed in feeds:
        assert feed.status == "active"
        assert feed.publisher == "smh"


# ---------------------------------------------------------------------------
# AC1.4: Navigation slug discovery constructs new feed URL
# ---------------------------------------------------------------------------


def test_nav_slugs_produce_new_feed_urls(tmp_path: Path) -> None:
    """Navigation slugs not in static paths produce new feed URLs."""
    homepage_html = (FIXTURES / "smh_homepage.html").read_text()
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, homepage_html),
    }

    client = _make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_urls = {f.url for f in feeds}
    # "opinion" and "entertainment" are not in static paths
    assert f"{BASE_URL}/rss/opinion.xml" in feed_urls
    assert f"{BASE_URL}/rss/entertainment.xml" in feed_urls


def test_nav_discovery_adds_to_static_count(tmp_path: Path) -> None:
    """Discovery with nav slugs produces more feeds than static alone."""
    homepage_html = (FIXTURES / "smh_homepage.html").read_text()
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, homepage_html),
    }

    client = _make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    # 17 static + 2 new (opinion, entertainment) = 19
    assert len(feeds) == len(STATIC_FEED_PATHS) + 2


# ---------------------------------------------------------------------------
# Excluded slugs not turned into feed URLs
# ---------------------------------------------------------------------------


def test_excluded_slugs_not_in_feeds(tmp_path: Path) -> None:
    """Excluded slugs like 'login' do not produce feed URLs."""
    homepage_html = (FIXTURES / "smh_homepage.html").read_text()
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, homepage_html),
    }

    client = _make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_urls = {f.url for f in feeds}
    assert f"{BASE_URL}/rss/login.xml" not in feed_urls


# ---------------------------------------------------------------------------
# AC1.5: Dead feed recorded, not dropped
# ---------------------------------------------------------------------------


def test_dead_feed_recorded_not_dropped_on_404(tmp_path: Path) -> None:
    """When HEAD probe returns 404 for a static feed, it is recorded as dead."""
    empty_html = "<html><body></body></html>"
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, empty_html),
    }

    dead_url = f"{BASE_URL}/rss/national.xml"
    client = _make_mock_client(
        tmp_path,
        responses=responses,
        head_responses={dead_url: 404},
    )
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    dead_feed = next(f for f in feeds if f.url == dead_url)
    assert dead_feed.status == "dead"

    # Verify it is in the registry, not silently dropped
    stored = registry.get_feeds(publisher="smh")
    stored_urls = {f.url for f in stored}
    assert dead_url in stored_urls


# ---------------------------------------------------------------------------
# Deduplication: static + nav overlap
# ---------------------------------------------------------------------------


def test_deduplicates_static_and_nav_overlap(tmp_path: Path) -> None:
    """Slugs already covered by static paths do not create duplicate feeds.

    The fixture nav contains 'national' and 'business' which are in
    STATIC_FEED_PATHS. These should not produce duplicate entries.
    """
    homepage_html = (FIXTURES / "smh_homepage.html").read_text()
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, homepage_html),
    }

    client = _make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    # Count how many feeds have the national URL
    national_url = f"{BASE_URL}/rss/national.xml"
    national_feeds = [f for f in feeds if f.url == national_url]
    assert len(national_feeds) == 1


# ---------------------------------------------------------------------------
# Feed ID and title derivation
# ---------------------------------------------------------------------------


def test_feed_id_derived_from_path(tmp_path: Path) -> None:
    """Feed ID is derived from the RSS URL path."""
    empty_html = "<html><body></body></html>"
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, empty_html),
    }

    client = _make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_by_url = {f.url: f for f in feeds}
    # /rss/national.xml -> feed_id = "national"
    assert feed_by_url[f"{BASE_URL}/rss/national.xml"].feed_id == "national"
    # /rss/politics/federal.xml -> feed_id = "politics-federal"
    assert (
        feed_by_url[f"{BASE_URL}/rss/politics/federal.xml"].feed_id
        == "politics-federal"
    )
    # /rss/sport/rugby-league.xml -> feed_id = "sport-rugby-league"
    assert (
        feed_by_url[f"{BASE_URL}/rss/sport/rugby-league.xml"].feed_id
        == "sport-rugby-league"
    )


def test_title_format(tmp_path: Path) -> None:
    """Title follows the 'SMH - ...' format with path segments."""
    empty_html = "<html><body></body></html>"
    responses: dict[str, tuple[int, str]] = {
        HOMEPAGE_URL: (200, empty_html),
    }

    client = _make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_by_url = {f.url: f for f in feeds}
    assert feed_by_url[f"{BASE_URL}/rss/national.xml"].title == "SMH - National"
    assert (
        feed_by_url[f"{BASE_URL}/rss/politics/federal.xml"].title
        == "SMH - Politics > Federal"
    )
    assert (
        feed_by_url[f"{BASE_URL}/rss/sport/rugby-league.xml"].title
        == "SMH - Sport > Rugby League"
    )
