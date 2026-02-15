"""Tests for SBS News feed discovery.

Covers acceptance criteria:
- AC1.3: Feed URLs from feeds page, alternate links, and topic slugs
- AC1.5: Dead feeds recorded (not dropped) on 404
"""

from pathlib import Path

from australianewsrss.discovery.sbs import (
    FEEDS_PAGE_URL,
    SECTION_SEED_URLS,
    _extract_alternate_links,
    _extract_feed_urls_from_feeds_page,
    _extract_topic_slugs,
    discover_feeds,
)
from australianewsrss.state import FeedRegistry

from .conftest import FIXTURES, make_mock_client

# ---------------------------------------------------------------------------
# Unit tests for extraction helpers
# ---------------------------------------------------------------------------


class TestExtractFeedUrlsFromFeedsPage:
    """Unit tests for _extract_feed_urls_from_feeds_page."""

    def test_extracts_absolute_feed_urls(self) -> None:
        html = (FIXTURES / "sbs_feeds_page.html").read_text()
        urls = _extract_feed_urls_from_feeds_page(html)
        assert "https://www.sbs.com.au/news/feed" in urls
        assert "https://www.sbs.com.au/news/topic/world/feed" in urls

    def test_converts_relative_urls_to_absolute(self) -> None:
        html = (FIXTURES / "sbs_feeds_page.html").read_text()
        urls = _extract_feed_urls_from_feeds_page(html)
        assert "https://www.sbs.com.au/news/topic/australia/feed" in urls

    def test_ignores_non_feed_links(self) -> None:
        html = (FIXTURES / "sbs_feeds_page.html").read_text()
        urls = _extract_feed_urls_from_feeds_page(html)
        for url in urls:
            assert "/about" not in url

    def test_returns_three_urls_from_fixture(self) -> None:
        html = (FIXTURES / "sbs_feeds_page.html").read_text()
        urls = _extract_feed_urls_from_feeds_page(html)
        assert len(urls) == 3

    def test_empty_html_returns_empty(self) -> None:
        urls = _extract_feed_urls_from_feeds_page("<html><body></body></html>")
        assert urls == set()


class TestExtractAlternateLinks:
    """Unit tests for _extract_alternate_links."""

    def test_extracts_rss_link_from_head(self) -> None:
        html = (FIXTURES / "sbs_section_page.html").read_text()
        urls = _extract_alternate_links(html)
        assert "https://www.sbs.com.au/news/topic/science/feed" in urls

    def test_returns_one_url_from_fixture(self) -> None:
        html = (FIXTURES / "sbs_section_page.html").read_text()
        urls = _extract_alternate_links(html)
        assert len(urls) == 1

    def test_empty_html_returns_empty(self) -> None:
        urls = _extract_alternate_links("<html><head></head><body></body></html>")
        assert urls == set()


class TestExtractTopicSlugs:
    """Unit tests for _extract_topic_slugs."""

    def test_extracts_topic_slugs_from_nav(self) -> None:
        html = (FIXTURES / "sbs_section_page.html").read_text()
        slugs = _extract_topic_slugs(html)
        assert "politics" in slugs
        assert "health" in slugs
        assert "science" in slugs

    def test_returns_three_slugs_from_fixture(self) -> None:
        html = (FIXTURES / "sbs_section_page.html").read_text()
        slugs = _extract_topic_slugs(html)
        assert len(slugs) == 3

    def test_empty_html_returns_empty(self) -> None:
        slugs = _extract_topic_slugs("<html><body></body></html>")
        assert slugs == set()


# ---------------------------------------------------------------------------
# AC1.3: Feed URLs from feeds page
# ---------------------------------------------------------------------------


def test_feeds_page_urls_discovered(tmp_path: Path) -> None:
    """Feeds page HTML produces discovered feeds with correct URLs."""
    feeds_html = (FIXTURES / "sbs_feeds_page.html").read_text()
    section_html = "<html><body></body></html>"

    responses: dict[str, tuple[int, str]] = {
        FEEDS_PAGE_URL: (200, feeds_html),
    }
    # All section seed URLs return empty HTML
    for url in SECTION_SEED_URLS:
        responses[url] = (200, section_html)

    client = make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_urls = {f.url for f in feeds}
    assert "https://www.sbs.com.au/news/feed" in feed_urls
    assert "https://www.sbs.com.au/news/topic/australia/feed" in feed_urls
    assert "https://www.sbs.com.au/news/topic/world/feed" in feed_urls


# ---------------------------------------------------------------------------
# AC1.3: Alternate links from section pages
# ---------------------------------------------------------------------------


def test_section_alternate_links_discovered(tmp_path: Path) -> None:
    """Section page <link rel="alternate"> tags produce discovered feeds."""
    empty_feeds_page = "<html><body></body></html>"
    section_html = (FIXTURES / "sbs_section_page.html").read_text()

    responses: dict[str, tuple[int, str]] = {
        FEEDS_PAGE_URL: (200, empty_feeds_page),
    }
    for url in SECTION_SEED_URLS:
        responses[url] = (200, section_html)

    client = make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_urls = {f.url for f in feeds}
    assert "https://www.sbs.com.au/news/topic/science/feed" in feed_urls


# ---------------------------------------------------------------------------
# AC1.3: Topic slugs produce feed URLs
# ---------------------------------------------------------------------------


def test_topic_slugs_produce_feed_urls(tmp_path: Path) -> None:
    """Topic slugs from navigation are converted to feed URLs."""
    empty_feeds_page = "<html><body></body></html>"
    section_html = (FIXTURES / "sbs_section_page.html").read_text()

    responses: dict[str, tuple[int, str]] = {
        FEEDS_PAGE_URL: (200, empty_feeds_page),
    }
    for url in SECTION_SEED_URLS:
        responses[url] = (200, section_html)

    client = make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_urls = {f.url for f in feeds}
    # Topic slugs: politics, health, science
    # These get constructed as /news/topic/{slug}/feed
    assert "https://www.sbs.com.au/news/topic/politics/feed" in feed_urls
    assert "https://www.sbs.com.au/news/topic/health/feed" in feed_urls
    # "science" appears both as alternate link and topic slug — deduplicates
    assert "https://www.sbs.com.au/news/topic/science/feed" in feed_urls


# ---------------------------------------------------------------------------
# AC1.5: Dead feed recorded, not dropped
# ---------------------------------------------------------------------------


def test_dead_feed_recorded_not_dropped_on_404(tmp_path: Path) -> None:
    """When HEAD probe returns 404, feed is recorded with status='dead'."""
    feeds_html = (FIXTURES / "sbs_feeds_page.html").read_text()
    empty_section = "<html><body></body></html>"

    responses: dict[str, tuple[int, str]] = {
        FEEDS_PAGE_URL: (200, feeds_html),
    }
    for url in SECTION_SEED_URLS:
        responses[url] = (200, empty_section)

    dead_url = "https://www.sbs.com.au/news/topic/australia/feed"
    client = make_mock_client(
        tmp_path,
        responses=responses,
        head_responses={dead_url: 404},
    )
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    dead_feed = next(f for f in feeds if f.url == dead_url)
    assert dead_feed.status == "dead"

    # Verify it is in the registry, not silently dropped
    stored = registry.get_feeds(publisher="sbs")
    stored_urls = {f.url for f in stored}
    assert dead_url in stored_urls


# ---------------------------------------------------------------------------
# Feed ID and title derivation
# ---------------------------------------------------------------------------


def test_feed_id_derived_from_url(tmp_path: Path) -> None:
    """Feed ID is derived from URL path segment, not from the trailing /feed."""
    feeds_html = (FIXTURES / "sbs_feeds_page.html").read_text()
    empty_section = "<html><body></body></html>"

    responses: dict[str, tuple[int, str]] = {
        FEEDS_PAGE_URL: (200, feeds_html),
    }
    for url in SECTION_SEED_URLS:
        responses[url] = (200, empty_section)

    client = make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_by_url = {f.url: f for f in feeds}
    # https://www.sbs.com.au/news/feed -> feed_id = "main"
    assert feed_by_url["https://www.sbs.com.au/news/feed"].feed_id == "main"
    # https://www.sbs.com.au/news/topic/australia/feed -> feed_id = "australia"
    assert (
        feed_by_url["https://www.sbs.com.au/news/topic/australia/feed"].feed_id
        == "australia"
    )
    # https://www.sbs.com.au/news/topic/world/feed -> feed_id = "world"
    assert (
        feed_by_url["https://www.sbs.com.au/news/topic/world/feed"].feed_id == "world"
    )


def test_all_feeds_have_sbs_publisher(tmp_path: Path) -> None:
    """All discovered feeds have publisher='sbs'."""
    feeds_html = (FIXTURES / "sbs_feeds_page.html").read_text()
    empty_section = "<html><body></body></html>"

    responses: dict[str, tuple[int, str]] = {
        FEEDS_PAGE_URL: (200, feeds_html),
    }
    for url in SECTION_SEED_URLS:
        responses[url] = (200, empty_section)

    client = make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    for feed in feeds:
        assert feed.publisher == "sbs"


# ---------------------------------------------------------------------------
# Empty fixture
# ---------------------------------------------------------------------------


def test_empty_pages_produce_no_feeds(tmp_path: Path) -> None:
    """Empty feeds page and empty section pages produce no feeds."""
    empty_html = "<html><body></body></html>"

    responses: dict[str, tuple[int, str]] = {
        FEEDS_PAGE_URL: (200, empty_html),
    }
    for url in SECTION_SEED_URLS:
        responses[url] = (200, empty_html)

    client = make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    assert feeds == []
    assert registry.get_feeds(publisher="sbs") == []


def test_all_feeds_have_distinct_feed_ids(tmp_path: Path) -> None:
    """All discovered SBS feeds have distinct feed_ids (no collisions)."""
    feeds_html = (FIXTURES / "sbs_feeds_page.html").read_text()
    section_html = (FIXTURES / "sbs_section_page.html").read_text()

    responses: dict[str, tuple[int, str]] = {
        FEEDS_PAGE_URL: (200, feeds_html),
    }
    for url in SECTION_SEED_URLS:
        responses[url] = (200, section_html)

    client = make_mock_client(tmp_path, responses=responses)
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_ids = [f.feed_id for f in feeds]
    # All feed_ids should be unique
    assert len(feed_ids) == len(set(feed_ids)), f"feed_ids are not unique: {feed_ids}"
