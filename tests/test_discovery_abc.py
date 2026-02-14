"""Tests for ABC News CoreMedia feed discovery.

Covers acceptance criteria:
- AC1.1: Collection ID extraction and feed URL construction
- AC1.2: Both static and dynamic collection types extracted
- AC1.5: Dead feeds recorded (not dropped) on 404/500
- AC1.6: Dynamic collection type tracking
"""

from pathlib import Path

import httpx

from australianewsrss.discovery.abc import (
    FEED_URL_TEMPLATE,
    _extract_collection_ids,
    discover_feeds,
)
from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.state import FeedRegistry, HttpCache

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mock_client(
    tmp_path: Path,
    seed_html_file: str,
    head_responses: dict[str, int] | None = None,
) -> PoliteHttpClient:
    """Create a PoliteHttpClient with mock transport.

    seed_html_file: fixture filename to return for seed URL GETs.
    head_responses: dict of URL -> status code for HEAD requests (default 200).
    """
    fixture_html = (FIXTURES / seed_html_file).read_text()
    head_map = head_responses or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            status = head_map.get(str(request.url), 200)
            return httpx.Response(status)
        # GET requests return fixture HTML for any seed URL
        return httpx.Response(200, text=fixture_html)

    cache = HttpCache(tmp_path / "cache.db")
    client = PoliteHttpClient(cache, delay_ms=0)
    client._client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers=client._client.headers,
    )
    return client


# ---------------------------------------------------------------------------
# Unit tests for _extract_collection_ids
# ---------------------------------------------------------------------------


class TestExtractCollectionIds:
    """Direct unit tests for the regex extraction helper."""

    def test_extracts_static_collection_ids(self) -> None:
        html = (FIXTURES / "abc_section_page.html").read_text()
        results = _extract_collection_ids(html)
        ids = [cid for _, cid in results]
        assert "10719986" in ids
        assert "104217372" in ids
        assert "104217374" in ids

    def test_all_static_ids_marked_not_dynamic(self) -> None:
        html = (FIXTURES / "abc_section_page.html").read_text()
        results = _extract_collection_ids(html)
        for is_dynamic, _ in results:
            assert is_dynamic is False

    def test_extracts_dynamic_collection_ids(self) -> None:
        html = (FIXTURES / "abc_section_page_dynamic.html").read_text()
        results = _extract_collection_ids(html)
        id_map = {cid: is_dynamic for is_dynamic, cid in results}
        assert id_map["10719986"] is False
        assert id_map["105026656"] is True
        assert id_map["105060106"] is True

    def test_empty_page_extracts_nothing(self) -> None:
        html = (FIXTURES / "abc_section_page_empty.html").read_text()
        results = _extract_collection_ids(html)
        assert results == []

    def test_deduplicates_by_id(self) -> None:
        """Same ID appearing multiple times yields only one entry."""
        html = "coremedia://collection/123 coremedia://collection/123"
        results = _extract_collection_ids(html)
        assert len(results) == 1
        assert results[0] == (False, "123")


# ---------------------------------------------------------------------------
# AC1.1: Collection ID extraction and feed URL construction
# ---------------------------------------------------------------------------


def test_extracts_collection_id_and_constructs_feed_url(tmp_path: Path) -> None:
    """Given fixture HTML containing coremedia://collection/10719986,
    discovery extracts the ID and converts it to feed URL
    https://www.abc.net.au/news/feed/10719986/rss.xml.
    When HEAD probe returns 200, feed is recorded as active."""
    client = _make_mock_client(tmp_path, "abc_section_page.html")
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    expected_url = FEED_URL_TEMPLATE.format(id="10719986")
    feed_urls = [f.url for f in feeds]
    assert expected_url in feed_urls

    feed = next(f for f in feeds if f.url == expected_url)
    assert feed.status == "active"
    assert feed.publisher == "abc"
    assert feed.feed_id == "10719986"


def test_all_collection_ids_produce_feed_urls(tmp_path: Path) -> None:
    """All three collection IDs from the fixture produce feed URLs."""
    client = _make_mock_client(tmp_path, "abc_section_page.html")
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_urls = {f.url for f in feeds}
    for cid in ["10719986", "104217372", "104217374"]:
        assert FEED_URL_TEMPLATE.format(id=cid) in feed_urls


# ---------------------------------------------------------------------------
# AC1.2: Both collection types extracted
# ---------------------------------------------------------------------------


def test_extracts_both_static_and_dynamic_collections(tmp_path: Path) -> None:
    """Given fixture HTML containing both coremedia://collection/{ID}
    and coremedia://dynamiccollection/{ID}, discovery extracts both types."""
    client = _make_mock_client(tmp_path, "abc_section_page_dynamic.html")
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed_ids = {f.feed_id for f in feeds}
    # Static
    assert "10719986" in feed_ids
    # Dynamic
    assert "105026656" in feed_ids
    assert "105060106" in feed_ids


# ---------------------------------------------------------------------------
# AC1.5: Dead feeds recorded (not dropped)
# ---------------------------------------------------------------------------


def test_dead_feed_recorded_not_dropped_404(tmp_path: Path) -> None:
    """When HEAD probe returns 404, feed is recorded with status='dead'."""
    target_url = FEED_URL_TEMPLATE.format(id="10719986")
    client = _make_mock_client(
        tmp_path,
        "abc_section_page.html",
        head_responses={target_url: 404},
    )
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed = next(f for f in feeds if f.feed_id == "10719986")
    assert feed.status == "dead"

    # Verify it's in the registry, not silently dropped
    stored = registry.get_feeds(publisher="abc")
    stored_urls = {f.url for f in stored}
    assert target_url in stored_urls


def test_dead_feed_recorded_not_dropped_500(tmp_path: Path) -> None:
    """When HEAD probe returns 500, feed is recorded with status='dead'."""
    target_url = FEED_URL_TEMPLATE.format(id="10719986")
    client = _make_mock_client(
        tmp_path,
        "abc_section_page.html",
        head_responses={target_url: 500},
    )
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    feed = next(f for f in feeds if f.feed_id == "10719986")
    assert feed.status == "dead"

    stored = registry.get_feeds(publisher="abc")
    stored_urls = {f.url for f in stored}
    assert target_url in stored_urls


# ---------------------------------------------------------------------------
# AC1.6: Dynamic collection tracking
# ---------------------------------------------------------------------------


def test_dynamic_collection_type_recorded(tmp_path: Path) -> None:
    """Dynamic collection feeds have their category_hint set to 'dynamic'."""
    client = _make_mock_client(tmp_path, "abc_section_page_dynamic.html")
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    dynamic_feed = next(f for f in feeds if f.feed_id == "105026656")
    assert dynamic_feed.category_hint == "dynamic"

    static_feed = next(f for f in feeds if f.feed_id == "10719986")
    assert static_feed.category_hint == "collection"


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------


def test_empty_page_produces_no_feeds(tmp_path: Path) -> None:
    """Empty section page (no CoreMedia references) produces no new feeds."""
    client = _make_mock_client(tmp_path, "abc_section_page_empty.html")
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    assert feeds == []
    assert registry.get_feeds(publisher="abc") == []


def test_duplicate_ids_deduplicated(tmp_path: Path) -> None:
    """Duplicate collection IDs across pages are deduplicated.

    All 15 seed URLs return the same fixture HTML, so the same 3 IDs
    appear 15 times. Discovery should still produce only 3 unique feeds.
    """
    client = _make_mock_client(tmp_path, "abc_section_page.html")
    registry = FeedRegistry(tmp_path / "state")

    feeds = discover_feeds(client, registry)

    assert len(feeds) == 3
    feed_ids = {f.feed_id for f in feeds}
    assert feed_ids == {"10719986", "104217372", "104217374"}


def test_discovery_updates_existing_feed_timestamps(tmp_path: Path) -> None:
    """Discovery updates last_seen/last_checked on existing feeds.

    Run discovery twice. The second run should update timestamps on
    the feeds that were already in the registry.
    """
    client = _make_mock_client(tmp_path, "abc_section_page.html")
    registry = FeedRegistry(tmp_path / "state")

    discover_feeds(client, registry)
    first_by_id = {f.feed_id: f for f in registry.get_feeds(publisher="abc")}

    # Run again -- timestamps should be updated
    client2 = _make_mock_client(tmp_path, "abc_section_page.html")
    discover_feeds(client2, registry)
    second_by_id = {f.feed_id: f for f in registry.get_feeds(publisher="abc")}

    for cid in ["10719986", "104217372", "104217374"]:
        first = first_by_id[cid]
        second = second_by_id[cid]
        # first_seen is preserved from original discovery
        assert second.first_seen == first.first_seen
        # last_seen and last_checked are updated
        assert second.last_seen is not None
        assert first.last_seen is not None
        assert second.last_seen >= first.last_seen
        assert second.last_checked is not None
        assert first.last_checked is not None
        assert second.last_checked >= first.last_checked
