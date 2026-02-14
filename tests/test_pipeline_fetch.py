"""Tests for feed fetching and RSS parsing pipeline stage."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock

import pytest

from australianewsrss.models import DiscoveredFeed, FeedItem, FetchedFeed
from australianewsrss.pipeline.fetch import (
    _extract_image_url,
    _extract_published,
    _parse_feed,
    fetch_feeds,
)

# --- Helpers ---


def _make_feed(
    url: str = "https://example.com/feed.xml",
    publisher: Literal["abc", "sbs", "smh"] = "abc",
    title: str = "Test Feed",
    feed_id: str = "test-feed",
) -> DiscoveredFeed:
    return DiscoveredFeed(
        publisher=publisher,
        url=url,
        title=title,
        category_hint="general",
        feed_id=feed_id,
        status="active",
        first_seen=datetime(2025, 1, 1, tzinfo=UTC),
    )


MINIMAL_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Article One</title>
      <link>https://example.com/article-1</link>
      <description>First article description</description>
      <guid>guid-1</guid>
      <pubDate>Mon, 01 Jan 2025 12:00:00 +0000</pubDate>
      <author>Jane Doe</author>
      <category>Politics</category>
      <category>Australia</category>
    </item>
    <item>
      <title>Article Two</title>
      <link>https://example.com/article-2</link>
      <description>Second article description</description>
      <guid>guid-2</guid>
    </item>
  </channel>
</rss>
"""

RSS_WITH_MEDIA = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
  <channel>
    <title>Media Feed</title>
    <item>
      <title>Media Article</title>
      <link>https://example.com/media-1</link>
      <description>Has media content</description>
      <guid>media-guid-1</guid>
      <media:content url="https://example.com/image.jpg"
                     medium="image" type="image/jpeg" />
    </item>
  </channel>
</rss>
"""

RSS_WITH_ENCLOSURE = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Enclosure Feed</title>
    <item>
      <title>Enclosure Article</title>
      <link>https://example.com/enc-1</link>
      <description>Has enclosure</description>
      <guid>enc-guid-1</guid>
      <enclosure url="https://example.com/photo.png"
                 type="image/png" length="12345" />
    </item>
  </channel>
</rss>
"""

MALFORMED_XML = "<this is not valid xml at all<<<>>>"


# --- Tests for _extract_published ---


class TestExtractPublished:
    def test_extracts_published_parsed(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "published_parsed": (2025, 1, 15, 10, 30, 0, 0, 0, 0),
            "updated_parsed": None,
        }.get(key, default)

        result = _extract_published(entry)

        assert result == datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)

    def test_falls_back_to_updated_parsed(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "published_parsed": None,
            "updated_parsed": (2025, 6, 1, 8, 0, 0, 0, 0, 0),
        }.get(key, default)

        result = _extract_published(entry)

        assert result == datetime(2025, 6, 1, 8, 0, 0, tzinfo=UTC)

    def test_returns_none_when_neither_present(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: default

        result = _extract_published(entry)

        assert result is None

    def test_returns_none_on_invalid_parsed_time(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "published_parsed": "not-a-tuple",
        }.get(key, default)

        result = _extract_published(entry)

        assert result is None


# --- Tests for _extract_image_url ---


class TestExtractImageUrl:
    def test_extracts_from_media_content_by_medium(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "media_content": [
                {"medium": "image", "url": "https://example.com/img.jpg"}
            ],
            "enclosures": [],
        }.get(key, default if default is not None else [])

        result = _extract_image_url(entry)

        assert result == "https://example.com/img.jpg"

    def test_extracts_from_media_content_by_type(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "media_content": [
                {"type": "image/jpeg", "url": "https://example.com/photo.jpg"}
            ],
            "enclosures": [],
        }.get(key, default if default is not None else [])

        result = _extract_image_url(entry)

        assert result == "https://example.com/photo.jpg"

    def test_extracts_from_enclosures(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "media_content": [],
            "enclosures": [
                {
                    "type": "image/png",
                    "href": "https://example.com/enc.png",
                }
            ],
        }.get(key, default if default is not None else [])

        result = _extract_image_url(entry)

        assert result == "https://example.com/enc.png"

    def test_enclosure_falls_back_to_url_key(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "media_content": [],
            "enclosures": [
                {
                    "type": "image/png",
                    "url": "https://example.com/enc-url.png",
                }
            ],
        }.get(key, default if default is not None else [])

        result = _extract_image_url(entry)

        assert result == "https://example.com/enc-url.png"

    def test_returns_none_when_no_image(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "media_content": [],
            "enclosures": [],
        }.get(key, default if default is not None else [])

        result = _extract_image_url(entry)

        assert result is None

    def test_skips_non_image_media_content(self):
        entry = MagicMock()
        entry.get = lambda key, default=None: {
            "media_content": [
                {"medium": "video", "url": "https://example.com/vid.mp4"}
            ],
            "enclosures": [],
        }.get(key, default if default is not None else [])

        result = _extract_image_url(entry)

        assert result is None


# --- Tests for _parse_feed ---


class TestParseFeed:
    def test_parses_valid_rss_into_feed_items(self):
        items = _parse_feed(MINIMAL_RSS, "https://example.com/feed.xml")

        assert len(items) == 2
        assert all(isinstance(item, FeedItem) for item in items)

    def test_first_item_has_correct_fields(self):
        items = _parse_feed(MINIMAL_RSS, "https://example.com/feed.xml")
        first = items[0]

        assert first.url == "https://example.com/article-1"
        assert first.title == "Article One"
        assert first.description == "First article description"
        assert first.guid == "guid-1"
        assert first.author == "Jane Doe"
        assert first.source_feed_url == "https://example.com/feed.xml"

    def test_first_item_has_published_datetime(self):
        items = _parse_feed(MINIMAL_RSS, "https://example.com/feed.xml")
        first = items[0]

        assert first.published is not None
        assert first.published.year == 2025
        assert first.published.month == 1
        assert first.published.day == 1

    def test_first_item_has_categories(self):
        items = _parse_feed(MINIMAL_RSS, "https://example.com/feed.xml")
        first = items[0]

        assert "Politics" in first.categories
        assert "Australia" in first.categories

    def test_second_item_has_no_author(self):
        items = _parse_feed(MINIMAL_RSS, "https://example.com/feed.xml")
        second = items[1]

        assert second.author is None

    def test_second_item_has_no_published(self):
        items = _parse_feed(MINIMAL_RSS, "https://example.com/feed.xml")
        second = items[1]

        assert second.published is None

    def test_malformed_xml_with_no_entries_returns_empty(self):
        items = _parse_feed(MALFORMED_XML, "https://example.com/bad.xml")

        assert items == []

    def test_extracts_media_content_image(self):
        items = _parse_feed(RSS_WITH_MEDIA, "https://example.com/media.xml")

        assert len(items) == 1
        assert items[0].image_url == "https://example.com/image.jpg"

    def test_extracts_enclosure_image(self):
        items = _parse_feed(RSS_WITH_ENCLOSURE, "https://example.com/enc.xml")

        assert len(items) == 1
        assert items[0].image_url == "https://example.com/photo.png"


# --- Tests for fetch_feeds ---


class TestFetchFeeds:
    def test_fetches_and_parses_single_feed(self, tmp_path: Path):
        from tests.conftest import make_mock_client

        feed = _make_feed(url="https://example.com/rss.xml")
        client = make_mock_client(
            tmp_path,
            responses={"https://example.com/rss.xml": (200, MINIMAL_RSS)},
        )

        results = fetch_feeds(client, [feed])

        assert len(results) == 1
        assert isinstance(results[0], FetchedFeed)
        assert results[0].feed == feed
        assert results[0].was_cached is False
        assert len(results[0].items) == 2

    def test_fetches_multiple_feeds(self, tmp_path: Path):
        from tests.conftest import make_mock_client

        feed1 = _make_feed(url="https://example.com/feed1.xml", feed_id="feed-1")
        feed2 = _make_feed(url="https://example.com/feed2.xml", feed_id="feed-2")
        client = make_mock_client(
            tmp_path,
            responses={
                "https://example.com/feed1.xml": (200, MINIMAL_RSS),
                "https://example.com/feed2.xml": (200, RSS_WITH_MEDIA),
            },
        )

        results = fetch_feeds(client, [feed1, feed2])

        assert len(results) == 2

    def test_skips_failed_fetches_and_continues(self, tmp_path: Path):
        from tests.conftest import make_mock_client

        feed_ok = _make_feed(url="https://example.com/good.xml", feed_id="good")
        feed_bad = _make_feed(url="https://example.com/bad.xml", feed_id="bad")
        client = make_mock_client(
            tmp_path,
            responses={
                "https://example.com/good.xml": (200, MINIMAL_RSS),
                "https://example.com/bad.xml": (500, "Server Error"),
            },
        )

        results = fetch_feeds(client, [feed_ok, feed_bad])

        # Only the successful feed should be in results
        assert len(results) == 1
        assert results[0].feed.url == "https://example.com/good.xml"

    def test_returns_empty_list_for_no_feeds(self, tmp_path: Path):
        from tests.conftest import make_mock_client

        client = make_mock_client(tmp_path)

        results = fetch_feeds(client, [])

        assert results == []

    def test_logs_warning_on_fetch_failure(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ):
        from tests.conftest import make_mock_client

        feed = _make_feed(url="https://example.com/fail.xml")
        client = make_mock_client(
            tmp_path,
            responses={
                "https://example.com/fail.xml": (500, "Server Error"),
            },
        )

        import logging

        with caplog.at_level(logging.WARNING):
            fetch_feeds(client, [feed])

        assert any(
            "https://example.com/fail.xml" in record.message
            for record in caplog.records
        )
