"""Tests for catalogue JSON and index HTML generation."""

import json
from datetime import UTC, datetime
from pathlib import Path

from australianewsrss.models import DiscoveredFeed, FeedMetadata
from australianewsrss.pipeline.generate import generate_catalogue, generate_index
from australianewsrss.state import FeedRegistry


def _make_feed(**overrides: object) -> DiscoveredFeed:
    """Create a DiscoveredFeed with sensible defaults for testing."""
    defaults: dict[str, object] = {
        "publisher": "abc",
        "url": "https://www.abc.net.au/news/feed/1234/rss.xml",
        "title": "ABC Top Stories",
        "category_hint": "news",
        "feed_id": "1234",
        "status": "active",
        "first_seen": datetime(2026, 1, 1, tzinfo=UTC),
        "last_seen": datetime(2026, 2, 14, 10, 0, tzinfo=UTC),
        "last_checked": datetime(2026, 2, 14, 10, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return DiscoveredFeed(**defaults)  # type: ignore[arg-type]


class TestGenerateCatalogue:
    """AC4.1: Catalogue JSON contains all feeds with correct fields."""

    def test_catalogue_json_parses_and_has_generated_at(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(_make_feed())

        result = generate_catalogue(registry)
        data = json.loads(result)

        assert "generated_at" in data
        assert "feeds" in data

    def test_catalogue_json_contains_correct_feed_fields(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(_make_feed())

        result = generate_catalogue(registry)
        data = json.loads(result)

        assert len(data["feeds"]) == 1
        feed = data["feeds"][0]
        assert feed["publisher"] == "abc"
        assert feed["title"] == "ABC Top Stories"
        assert feed["url"] == "https://www.abc.net.au/news/feed/1234/rss.xml"
        assert feed["status"] == "active"
        assert feed["feed_id"] == "1234"
        assert feed["category_hint"] == "news"
        assert "first_seen" in feed
        assert "last_seen" in feed
        assert "last_checked" in feed

    def test_catalogue_exposes_upstream_feed_metadata(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(
            _make_feed(
                metadata=FeedMetadata(
                    title="ABC Sport Podcasts",
                    description="Sport podcasts and interviews",
                    link="https://www.abc.net.au/listen/sport",
                    language="en-AU",
                    categories=("Sport", "Podcast"),
                )
            )
        )

        result = generate_catalogue(registry)
        data = json.loads(result)

        feed = data["feeds"][0]
        assert feed["metadata"]["title"] == "ABC Sport Podcasts"
        assert feed["metadata"]["description"] == "Sport podcasts and interviews"
        assert feed["metadata"]["link"] == "https://www.abc.net.au/listen/sport"
        assert feed["metadata"]["language"] == "en-AU"
        assert feed["metadata"]["categories"] == ["Sport", "Podcast"]

    def test_catalogue_feeds_sorted_by_publisher_then_url(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(
            _make_feed(
                publisher="sbs",
                url="https://sbs.com.au/feed/z",
                feed_id="z",
            )
        )
        registry.upsert(
            _make_feed(
                publisher="abc",
                url="https://abc.net.au/feed/b",
                feed_id="b",
            )
        )
        registry.upsert(
            _make_feed(
                publisher="abc",
                url="https://abc.net.au/feed/a",
                feed_id="a",
            )
        )

        result = generate_catalogue(registry)
        data = json.loads(result)

        urls = [f["url"] for f in data["feeds"]]
        assert urls == [
            "https://abc.net.au/feed/a",
            "https://abc.net.au/feed/b",
            "https://sbs.com.au/feed/z",
        ]


class TestCatalogueAllStatuses:
    """AC4.3: All feed statuses appear in catalogue."""

    def test_all_statuses_present_in_catalogue(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        statuses = ["active", "dead", "stale", "degraded"]
        for i, status in enumerate(statuses):
            registry.upsert(
                _make_feed(
                    url=f"https://abc.net.au/feed/{i}",
                    feed_id=str(i),
                    status=status,
                )
            )

        result = generate_catalogue(registry)
        data = json.loads(result)

        assert len(data["feeds"]) == 4
        found_statuses = {f["status"] for f in data["feeds"]}
        assert found_statuses == {"active", "dead", "stale", "degraded"}


class TestGenerateIndex:
    """AC4.2: Index HTML contains publisher names, feed titles, links."""

    def test_index_html_contains_publisher_and_feed_info(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(
            _make_feed(
                publisher="abc",
                url="https://abc.net.au/feed/1",
                feed_id="1",
                title="ABC Top Stories",
            )
        )
        registry.upsert(
            _make_feed(
                publisher="sbs",
                url="https://sbs.com.au/feed/1",
                feed_id="s1",
                title="SBS World News",
            )
        )

        output_feeds = {"abc": "feed/abc.xml", "sbs": "feed/sbs.xml"}
        result = generate_index(registry, output_feeds)

        assert "ABC" in result
        assert "SBS" in result
        assert "ABC Top Stories" in result
        assert "SBS World News" in result
        assert "https://abc.net.au/feed/1" in result
        assert "https://sbs.com.au/feed/1" in result

    def test_index_html_contains_generated_feed_links(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(_make_feed(publisher="abc"))

        output_feeds = {"abc": "feed/abc.xml"}
        result = generate_index(registry, output_feeds)

        assert "feed/abc.xml" in result

    def test_index_html_is_valid_html(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(_make_feed())

        result = generate_index(registry, {"abc": "feed/abc.xml"})

        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "</html>" in result
        assert "AustraliaNewsRSS" in result

    def test_index_html_shows_all_statuses(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        for i, status in enumerate(["active", "dead", "stale", "degraded"]):
            registry.upsert(
                _make_feed(
                    url=f"https://abc.net.au/feed/{i}",
                    feed_id=str(i),
                    status=status,
                )
            )

        result = generate_index(registry, {"abc": "feed/abc.xml"})

        assert "status-active" in result
        assert "status-dead" in result
        assert "status-stale" in result
        assert "status-degraded" in result

    def test_index_html_contains_generated_timestamp(self, tmp_path: Path) -> None:
        registry = FeedRegistry(tmp_path)
        registry.upsert(_make_feed())

        result = generate_index(registry, {"abc": "feed/abc.xml"})

        assert "Generated" in result
