"""Tests for australianewsrss.state FeedRegistry and HttpCache."""

import json
from datetime import UTC, datetime, timedelta

from australianewsrss.models import DiscoveredFeed
from australianewsrss.state import FeedRegistry, HttpCache


def make_feed(**overrides: object) -> DiscoveredFeed:
    """Create a DiscoveredFeed with sensible defaults for testing."""
    defaults: dict[str, object] = {
        "publisher": "abc",
        "url": "https://www.abc.net.au/news/feed/1234/rss.xml",
        "title": "ABC News",
        "category_hint": "news",
        "feed_id": "1234",
        "status": "active",
        "first_seen": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    return DiscoveredFeed(**defaults)


# ---------------------------------------------------------------------------
# FeedRegistry
# ---------------------------------------------------------------------------


class TestFeedRegistryPersistence:
    """Save/load round-trips and empty-state behaviour."""

    def test_save_then_load_round_trips(self, tmp_path: object) -> None:
        feeds = [
            make_feed(url="https://abc.net.au/feed/1", feed_id="1"),
            make_feed(url="https://abc.net.au/feed/2", feed_id="2"),
        ]
        registry = FeedRegistry(tmp_path)
        registry.save(feeds)

        loaded = registry.load()
        assert len(loaded) == 2
        urls = {f.url for f in loaded}
        assert urls == {"https://abc.net.au/feed/1", "https://abc.net.au/feed/2"}

    def test_load_returns_empty_list_when_file_missing(
        self, tmp_path: object
    ) -> None:
        registry = FeedRegistry(tmp_path)
        loaded = registry.load()
        assert loaded == []

    def test_feeds_json_sorted_by_publisher_then_url(
        self, tmp_path: object
    ) -> None:
        feeds = [
            make_feed(
                publisher="sbs",
                url="https://sbs.com.au/feed/z",
                feed_id="z",
            ),
            make_feed(
                publisher="abc",
                url="https://abc.net.au/feed/b",
                feed_id="b",
            ),
            make_feed(
                publisher="abc",
                url="https://abc.net.au/feed/a",
                feed_id="a",
            ),
        ]
        registry = FeedRegistry(tmp_path)
        registry.save(feeds)

        raw = json.loads((tmp_path / "feeds.json").read_text())
        publishers = [entry["publisher"] for entry in raw]
        urls = [entry["url"] for entry in raw]
        assert publishers == ["abc", "abc", "sbs"]
        assert urls == [
            "https://abc.net.au/feed/a",
            "https://abc.net.au/feed/b",
            "https://sbs.com.au/feed/z",
        ]


class TestFeedRegistryUpsert:
    """Upsert adds new feeds and updates existing ones."""

    def test_upsert_adds_new_feed_with_first_seen(
        self, tmp_path: object
    ) -> None:
        registry = FeedRegistry(tmp_path)
        feed = make_feed()
        before = datetime.now(UTC)
        registry.upsert(feed)
        after = datetime.now(UTC)

        stored = registry.get_feeds()
        assert len(stored) == 1
        assert stored[0].url == feed.url
        assert stored[0].first_seen is not None
        assert before <= stored[0].first_seen <= after

    def test_upsert_updates_last_seen_without_changing_first_seen(
        self, tmp_path: object
    ) -> None:
        registry = FeedRegistry(tmp_path)

        original_first_seen = datetime(2026, 1, 1, tzinfo=UTC)
        feed = make_feed(first_seen=original_first_seen)
        registry.upsert(feed)

        stored_first_seen = registry.get_feeds()[0].first_seen

        # Upsert again with the same URL
        registry.upsert(feed)

        updated = registry.get_feeds()[0]
        assert updated.first_seen == stored_first_seen
        assert updated.last_seen is not None
        assert updated.last_seen >= updated.first_seen


class TestFeedRegistryQuery:
    """Filtering and status management."""

    def test_get_feeds_filters_by_publisher(self, tmp_path: object) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(
            make_feed(
                publisher="abc",
                url="https://abc.net.au/feed/1",
                feed_id="1",
            )
        )
        registry.upsert(
            make_feed(
                publisher="sbs",
                url="https://sbs.com.au/feed/1",
                feed_id="s1",
            )
        )

        abc_feeds = registry.get_feeds(publisher="abc")
        assert len(abc_feeds) == 1
        assert abc_feeds[0].publisher == "abc"

        sbs_feeds = registry.get_feeds(publisher="sbs")
        assert len(sbs_feeds) == 1
        assert sbs_feeds[0].publisher == "sbs"

        all_feeds = registry.get_feeds()
        assert len(all_feeds) == 2

    def test_mark_status_changes_feed_status(self, tmp_path: object) -> None:
        registry = FeedRegistry(tmp_path)
        feed = make_feed()
        registry.upsert(feed)

        registry.mark_status(feed.url, "dead")

        updated = registry.get_feeds()[0]
        assert updated.status == "dead"


class TestFeedRegistryStaleness:
    """Staleness marking per AC1.6."""

    def test_mark_stale_feeds_marks_old_feeds_as_stale(
        self, tmp_path: object
    ) -> None:
        registry = FeedRegistry(tmp_path)

        old_feed = make_feed(
            url="https://abc.net.au/feed/old",
            feed_id="old",
        )
        registry.upsert(old_feed)

        # Manually set last_seen to >14 days ago
        stored = registry._feeds[old_feed.url]
        stale_date = datetime.now(UTC) - timedelta(days=15)
        registry._feeds[old_feed.url] = stored.model_copy(
            update={"last_seen": stale_date}
        )
        registry.save(list(registry._feeds.values()))

        affected = registry.mark_stale_feeds()
        assert len(affected) == 1
        assert affected[0].status == "stale"
        assert affected[0].url == old_feed.url

        # Verify persisted state matches
        reloaded = registry.load()
        stale_feed = [f for f in reloaded if f.url == old_feed.url][0]
        assert stale_feed.status == "stale"

    def test_mark_stale_feeds_does_not_affect_dead_feeds(
        self, tmp_path: object
    ) -> None:
        registry = FeedRegistry(tmp_path)

        dead_feed = make_feed(
            url="https://abc.net.au/feed/dead",
            feed_id="dead",
        )
        registry.upsert(dead_feed)

        # Set status to dead and last_seen to >14 days ago
        stored = registry._feeds[dead_feed.url]
        stale_date = datetime.now(UTC) - timedelta(days=15)
        registry._feeds[dead_feed.url] = stored.model_copy(
            update={"last_seen": stale_date, "status": "dead"}
        )
        registry.save(list(registry._feeds.values()))

        affected = registry.mark_stale_feeds()
        assert len(affected) == 0

        reloaded = registry.load()
        feed = [f for f in reloaded if f.url == dead_feed.url][0]
        assert feed.status == "dead"


# ---------------------------------------------------------------------------
# HttpCache
# ---------------------------------------------------------------------------


class TestHttpCacheOperations:
    """Core put/get/clear operations."""

    def test_put_then_get_returns_stored_data(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path / "cache.db")
        cache.put("https://example.com/feed", '"etag-123"', "<rss>data</rss>")

        etag, data = cache.get("https://example.com/feed")
        assert etag == '"etag-123"'
        assert data == "<rss>data</rss>"

    def test_get_returns_none_for_unknown_url(
        self, tmp_path: object
    ) -> None:
        cache = HttpCache(tmp_path / "cache.db")
        etag, data = cache.get("https://example.com/nonexistent")
        assert etag is None
        assert data is None

    def test_put_overwrites_existing_entry(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path / "cache.db")
        url = "https://example.com/feed"

        cache.put(url, '"etag-1"', "data-1")
        cache.put(url, '"etag-2"', "data-2")

        etag, data = cache.get(url)
        assert etag == '"etag-2"'
        assert data == "data-2"

    def test_clear_removes_all_entries(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path / "cache.db")
        cache.put("https://example.com/a", '"e1"', "d1")
        cache.put("https://example.com/b", '"e2"', "d2")

        cache.clear()

        assert cache.get("https://example.com/a") == (None, None)
        assert cache.get("https://example.com/b") == (None, None)


class TestHttpCacheConfiguration:
    """Database configuration checks."""

    def test_database_uses_wal_mode(self, tmp_path: object) -> None:
        cache = HttpCache(tmp_path / "cache.db")
        conn = cache._connect()
        try:
            row = conn.execute("PRAGMA journal_mode").fetchone()
            assert row[0] == "wal"
        finally:
            conn.close()
