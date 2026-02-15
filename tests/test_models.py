"""Tests for australianewsrss.models Pydantic data models."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from australianewsrss.models import (
    DiscoveredFeed,
    EnrichmentRule,
    FeedItem,
    FetchedFeed,
    NormalisedArticle,
    PublisherConfig,
)

NOW = datetime(2026, 2, 14, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# DiscoveredFeed
# ---------------------------------------------------------------------------


class TestDiscoveredFeed:
    """DiscoveredFeed construction, defaults, and validation."""

    def test_minimal_construction(self) -> None:
        feed = DiscoveredFeed(
            publisher="abc",
            url="https://abc.net.au/news/feed/rss.xml",
            title="ABC News",
            category_hint="news",
            feed_id="abc-news",
            status="active",
            first_seen=NOW,
        )
        assert feed.publisher == "abc"
        assert feed.url == "https://abc.net.au/news/feed/rss.xml"
        assert feed.title == "ABC News"
        assert feed.category_hint == "news"
        assert feed.feed_id == "abc-news"
        assert feed.status == "active"
        assert feed.first_seen == NOW
        assert feed.last_seen is None
        assert feed.last_checked is None

    def test_optional_fields_populated(self) -> None:
        feed = DiscoveredFeed(
            publisher="sbs",
            url="https://sbs.com.au/feed",
            title="SBS Feed",
            category_hint="world",
            feed_id="sbs-world",
            status="stale",
            first_seen=NOW,
            last_seen=NOW,
            last_checked=NOW,
        )
        assert feed.last_seen == NOW
        assert feed.last_checked == NOW

    def test_invalid_publisher_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DiscoveredFeed(
                publisher="bbc",  # type: ignore[arg-type]
                url="https://bbc.co.uk/feed",
                title="BBC",
                category_hint="news",
                feed_id="bbc-news",
                status="active",
                first_seen=NOW,
            )

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DiscoveredFeed(
                publisher="abc",
                url="https://abc.net.au/feed",
                title="ABC",
                category_hint="news",
                feed_id="abc-news",
                status="unknown",  # type: ignore[arg-type]
                first_seen=NOW,
            )

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DiscoveredFeed(
                publisher="abc",
                url="https://abc.net.au/feed",
                title="ABC",
                category_hint="news",
                feed_id="abc-news",
                status="active",
                first_seen=datetime(2026, 1, 1),  # noqa: DTZ001
            )

    def test_all_statuses_accepted(self) -> None:
        for status in ("active", "dead", "stale", "degraded"):
            feed = DiscoveredFeed(
                publisher="smh",
                url="https://smh.com.au/rss",
                title="SMH",
                category_hint="news",
                feed_id="smh-news",
                status=status,
                first_seen=NOW,
            )
            assert feed.status == status


# ---------------------------------------------------------------------------
# FeedItem
# ---------------------------------------------------------------------------


class TestFeedItem:
    """FeedItem construction, defaults, and validation."""

    def test_minimal_construction(self) -> None:
        item = FeedItem(
            url="https://abc.net.au/news/article-1",
            title="Test Article",
            description="A test article.",
            guid="abc-12345",
            source_feed_url="https://abc.net.au/news/feed/rss.xml",
        )
        assert item.url == "https://abc.net.au/news/article-1"
        assert item.title == "Test Article"
        assert item.description == "A test article."
        assert item.published is None
        assert item.guid == "abc-12345"
        assert item.author is None
        assert item.categories == []
        assert item.image_url is None
        assert item.source_feed_url == "https://abc.net.au/news/feed/rss.xml"

    def test_all_fields_populated(self) -> None:
        item = FeedItem(
            url="https://abc.net.au/news/article-1",
            title="Test Article",
            description="A test article.",
            published=NOW,
            guid="abc-12345",
            author="Jane Doe",
            categories=["politics", "australia"],
            image_url="https://abc.net.au/image.jpg",
            source_feed_url="https://abc.net.au/news/feed/rss.xml",
        )
        assert item.published == NOW
        assert item.author == "Jane Doe"
        assert item.categories == ["politics", "australia"]
        assert item.image_url == "https://abc.net.au/image.jpg"

    def test_categories_default_is_independent(self) -> None:
        """Default list must not be shared between instances."""
        item_a = FeedItem(
            url="https://a.com/1",
            title="A",
            description="",
            guid="a",
            source_feed_url="https://a.com/feed",
        )
        item_b = FeedItem(
            url="https://b.com/2",
            title="B",
            description="",
            guid="b",
            source_feed_url="https://b.com/feed",
        )
        item_a.categories.append("mutated")
        assert item_b.categories == []


# ---------------------------------------------------------------------------
# FetchedFeed
# ---------------------------------------------------------------------------


class TestFetchedFeed:
    """FetchedFeed composition and defaults."""

    def test_construction(self) -> None:
        feed = DiscoveredFeed(
            publisher="abc",
            url="https://abc.net.au/feed",
            title="ABC",
            category_hint="news",
            feed_id="abc-news",
            status="active",
            first_seen=NOW,
        )
        item = FeedItem(
            url="https://abc.net.au/article",
            title="Article",
            description="Desc",
            guid="g1",
            source_feed_url="https://abc.net.au/feed",
        )
        fetched = FetchedFeed(feed=feed, items=[item], was_cached=False)
        assert fetched.feed is feed
        assert len(fetched.items) == 1
        assert fetched.was_cached is False


# ---------------------------------------------------------------------------
# NormalisedArticle
# ---------------------------------------------------------------------------


class TestNormalisedArticle:
    """NormalisedArticle frozen behaviour, hashability, and fields."""

    def test_construction(self) -> None:
        article = NormalisedArticle(
            canonical_url="https://abc.net.au/news/article-1",
            url="https://abc.net.au/news/article-1?ref=rss",
            title="Article",
            description="Desc",
            guid="g1",
        )
        assert article.canonical_url == "https://abc.net.au/news/article-1"
        assert article.url == "https://abc.net.au/news/article-1?ref=rss"
        assert article.published is None
        assert article.author is None
        assert article.categories == ()
        assert article.image_url is None

    def test_frozen_rejects_mutation(self) -> None:
        article = NormalisedArticle(
            canonical_url="https://abc.net.au/news/1",
            url="https://abc.net.au/news/1",
            title="A",
            description="D",
            guid="g",
        )
        with pytest.raises(ValidationError):
            article.title = "Changed"

    def test_hashable_for_set_dedup(self) -> None:
        kwargs = dict(
            canonical_url="https://abc.net.au/news/1",
            url="https://abc.net.au/news/1",
            title="A",
            description="D",
            guid="g",
            categories=("news",),
        )
        a = NormalisedArticle(**kwargs)  # type: ignore[arg-type]
        b = NormalisedArticle(**kwargs)  # type: ignore[arg-type]
        assert a == b
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_different_articles_not_equal(self) -> None:
        a = NormalisedArticle(
            canonical_url="https://abc.net.au/1",
            url="https://abc.net.au/1",
            title="A",
            description="D",
            guid="g1",
        )
        b = NormalisedArticle(
            canonical_url="https://abc.net.au/2",
            url="https://abc.net.au/2",
            title="B",
            description="D",
            guid="g2",
        )
        assert a != b
        assert len({a, b}) == 2

    def test_categories_is_tuple(self) -> None:
        article = NormalisedArticle(
            canonical_url="https://abc.net.au/1",
            url="https://abc.net.au/1",
            title="A",
            description="D",
            guid="g",
            categories=("news", "politics"),
        )
        assert isinstance(article.categories, tuple)


# ---------------------------------------------------------------------------
# PublisherConfig
# ---------------------------------------------------------------------------


class TestPublisherConfig:
    """PublisherConfig frozen behaviour and fields."""

    def test_construction(self) -> None:
        config = PublisherConfig(
            slug="abc",
            name="Australian Broadcasting Corporation",
            base_url="https://abc.net.au",
            seed_urls=("https://abc.net.au/news/feed/rss.xml",),
        )
        assert config.slug == "abc"
        assert config.name == "Australian Broadcasting Corporation"
        assert config.base_url == "https://abc.net.au"
        assert config.seed_urls == ("https://abc.net.au/news/feed/rss.xml",)
        assert config.feed_url_template is None

    def test_with_template(self) -> None:
        config = PublisherConfig(
            slug="abc",
            name="ABC",
            base_url="https://abc.net.au",
            seed_urls=(),
            feed_url_template="https://abc.net.au/{}/feed/rss.xml",
        )
        assert config.feed_url_template == "https://abc.net.au/{}/feed/rss.xml"

    def test_frozen_rejects_mutation(self) -> None:
        config = PublisherConfig(
            slug="abc",
            name="ABC",
            base_url="https://abc.net.au",
            seed_urls=(),
        )
        with pytest.raises(ValidationError):
            config.slug = "sbs"

    def test_hashable(self) -> None:
        kwargs = dict(
            slug="abc",
            name="ABC",
            base_url="https://abc.net.au",
            seed_urls=("https://abc.net.au/feed",),
        )
        a = PublisherConfig(**kwargs)  # type: ignore[arg-type]
        b = PublisherConfig(**kwargs)  # type: ignore[arg-type]
        assert hash(a) == hash(b)


# ---------------------------------------------------------------------------
# EnrichmentRule
# ---------------------------------------------------------------------------


class TestEnrichmentRule:
    """EnrichmentRule frozen behaviour, fields, and validation."""

    def test_construction(self) -> None:
        rule = EnrichmentRule(
            publisher="abc",
            pattern_type="url",
            pattern=r"/news/sport/",
            add_categories=("sport",),
        )
        assert rule.publisher == "abc"
        assert rule.pattern_type == "url"
        assert rule.pattern == "/news/sport/"
        assert rule.add_categories == ("sport",)

    def test_invalid_pattern_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EnrichmentRule(
                publisher="abc",
                pattern_type="body",  # type: ignore[arg-type]
                pattern=".*",
                add_categories=("misc",),
            )

    def test_frozen_rejects_mutation(self) -> None:
        rule = EnrichmentRule(
            publisher="abc",
            pattern_type="title",
            pattern=".*",
            add_categories=(),
        )
        with pytest.raises(ValidationError):
            rule.publisher = "sbs"

    def test_hashable(self) -> None:
        kwargs = dict(
            publisher="abc",
            pattern_type="author",
            pattern="Jane.*",
            add_categories=("opinion",),
        )
        a = EnrichmentRule(**kwargs)  # type: ignore[arg-type]
        b = EnrichmentRule(**kwargs)  # type: ignore[arg-type]
        assert hash(a) == hash(b)
        assert len({a, b}) == 1


# ---------------------------------------------------------------------------
# Serialisation round-trip
# ---------------------------------------------------------------------------


class TestSerialisation:
    """Verify models serialise to JSON-compatible dicts and round-trip."""

    def test_discovered_feed_round_trip(self) -> None:
        feed = DiscoveredFeed(
            publisher="abc",
            url="https://abc.net.au/feed",
            title="ABC",
            category_hint="news",
            feed_id="abc-news",
            status="active",
            first_seen=NOW,
            last_seen=NOW,
        )
        data = feed.model_dump(mode="json")
        assert isinstance(data["first_seen"], str)
        restored = DiscoveredFeed.model_validate(data)
        assert restored == feed

    def test_normalised_article_round_trip(self) -> None:
        article = NormalisedArticle(
            canonical_url="https://abc.net.au/1",
            url="https://abc.net.au/1?ref=rss",
            title="A",
            description="D",
            guid="g",
            published=NOW,
            categories=("news", "politics"),
        )
        data = article.model_dump(mode="json")
        assert isinstance(data["published"], str)
        assert isinstance(data["categories"], list)  # JSON has no tuple
        restored = NormalisedArticle.model_validate(data)
        assert restored == article

    def test_feed_item_round_trip(self) -> None:
        item = FeedItem(
            url="https://abc.net.au/article",
            title="Article",
            description="Desc",
            published=NOW,
            guid="g1",
            author="Author",
            categories=["cat1"],
            image_url="https://img.com/1.jpg",
            source_feed_url="https://abc.net.au/feed",
        )
        data = item.model_dump(mode="json")
        restored = FeedItem.model_validate(data)
        assert restored == item
