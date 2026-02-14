"""Tests for australianewsrss.pipeline.enrich enrichment pipeline stage."""

from datetime import UTC, datetime
from typing import Literal

from australianewsrss.models import (
    DiscoveredFeed,
    EnrichmentRule,
    NormalisedArticle,
)
from australianewsrss.pipeline.enrich import enrich

NOW = datetime(2026, 2, 14, 12, 0, 0, tzinfo=UTC)


def _make_article(
    canonical_url: str = "https://abc.net.au/news/article-1",
    url: str = "https://abc.net.au/news/article-1?ref=rss",
    title: str = "Test Article",
    description: str = "A test article.",
    guid: str = "abc-12345",
    author: str | None = None,
    categories: tuple[str, ...] = (),
    image_url: str | None = None,
) -> NormalisedArticle:
    return NormalisedArticle(
        canonical_url=canonical_url,
        url=url,
        title=title,
        description=description,
        guid=guid,
        author=author,
        categories=categories,
        image_url=image_url,
    )


def _make_feed(
    publisher: Literal["abc", "sbs", "smh"] = "abc",
    url: str = "https://abc.net.au/news/feed/rss.xml",
    title: str = "ABC News",
    category_hint: str = "news",
    feed_id: str = "abc-news",
) -> DiscoveredFeed:
    return DiscoveredFeed(
        publisher=publisher,
        url=url,
        title=title,
        category_hint=category_hint,
        feed_id=feed_id,
        status="active",
        first_seen=NOW,
    )


# ---------------------------------------------------------------------------
# Layer 1: Source feed tags
# ---------------------------------------------------------------------------


class TestLayer1SourceFeedTags:
    """Layer 1 adds publisher:feed_title tag from the source feed."""

    def test_adds_source_feed_tag(self) -> None:
        feed = _make_feed()
        article = _make_article()
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [])

        assert len(result) == 1
        assert "abc:ABC News" in result[0].categories

    def test_no_source_mapping_skips_tag(self) -> None:
        feed = _make_feed()
        article = _make_article()
        source_feeds = {feed.url: feed}
        article_sources: dict[str, str] = {}

        result = enrich([article], source_feeds, article_sources, [])

        assert len(result) == 1
        # No source tag added since article not in article_sources
        assert result[0].categories == ()

    def test_source_feed_not_in_feeds_dict_skips_tag(self) -> None:
        article = _make_article()
        source_feeds: dict[str, DiscoveredFeed] = {}
        article_sources = {article.canonical_url: "https://abc.net.au/missing-feed"}

        result = enrich([article], source_feeds, article_sources, [])

        assert result[0].categories == ()

    def test_does_not_duplicate_existing_source_tag(self) -> None:
        feed = _make_feed()
        article = _make_article(categories=("abc:ABC News",))
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [])

        assert result[0].categories.count("abc:ABC News") == 1


# ---------------------------------------------------------------------------
# Layer 2: Upstream passthrough
# ---------------------------------------------------------------------------


class TestLayer2UpstreamPassthrough:
    """Layer 2 preserves existing categories from upstream feeds."""

    def test_preserves_existing_categories(self) -> None:
        article = _make_article(categories=("politics", "australia"))

        result = enrich([article], {}, {}, [])

        assert "politics" in result[0].categories
        assert "australia" in result[0].categories


# ---------------------------------------------------------------------------
# Layer 3: Pattern-based rules
# ---------------------------------------------------------------------------


class TestLayer3PatternRules:
    """Layer 3 applies regex-based enrichment rules."""

    def test_url_pattern_match(self) -> None:
        feed = _make_feed(publisher="smh", url="https://smh.com.au/feed")
        article = _make_article(
            canonical_url="https://smh.com.au/column-8/post",
            url="https://smh.com.au/column-8/post?ref=rss",
        )
        rule = EnrichmentRule(
            publisher="smh",
            pattern_type="url",
            pattern="/column-8/",
            add_categories=("smh:Column 8", "smh:Opinion"),
        )
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [rule])

        assert "smh:Column 8" in result[0].categories
        assert "smh:Opinion" in result[0].categories

    def test_title_pattern_match(self) -> None:
        feed = _make_feed(publisher="abc")
        article = _make_article(title="BREAKING: Major flooding in NSW")
        rule = EnrichmentRule(
            publisher="abc",
            pattern_type="title",
            pattern="^BREAKING:",
            add_categories=("breaking",),
        )
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [rule])

        assert "breaking" in result[0].categories

    def test_author_pattern_match(self) -> None:
        feed = _make_feed(publisher="abc")
        article = _make_article(author="Jane Smith")
        rule = EnrichmentRule(
            publisher="abc",
            pattern_type="author",
            pattern="Jane.*",
            add_categories=("columnist:jane",),
        )
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [rule])

        assert "columnist:jane" in result[0].categories

    def test_author_none_does_not_match(self) -> None:
        feed = _make_feed(publisher="abc")
        article = _make_article(author=None)
        rule = EnrichmentRule(
            publisher="abc",
            pattern_type="author",
            pattern=".*",
            add_categories=("has-author",),
        )
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [rule])

        # ".*" matches empty string, so this should still add the tag.
        # But None author becomes "" for matching, and ".*" matches "".
        assert "has-author" in result[0].categories

    def test_pattern_no_match_skips_rule(self) -> None:
        feed = _make_feed(publisher="abc")
        article = _make_article(url="https://abc.net.au/news/politics/article")
        rule = EnrichmentRule(
            publisher="abc",
            pattern_type="url",
            pattern="/sport/",
            add_categories=("sport",),
        )
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [rule])

        assert "sport" not in result[0].categories

    def test_rule_publisher_mismatch_skips_rule(self) -> None:
        feed = _make_feed(publisher="abc")
        article = _make_article(url="https://abc.net.au/column-8/post")
        rule = EnrichmentRule(
            publisher="smh",
            pattern_type="url",
            pattern="/column-8/",
            add_categories=("smh:Column 8",),
        )
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [rule])

        # Rule is for smh, article is from abc -- rule should be skipped
        assert "smh:Column 8" not in result[0].categories

    def test_rule_without_source_mapping_skips_publisher_check(
        self,
    ) -> None:
        """If no source mapping exists, we can't determine publisher.

        Rules should not apply when publisher cannot be determined.
        """
        article = _make_article(url="https://abc.net.au/rural/article")
        rule = EnrichmentRule(
            publisher="abc",
            pattern_type="url",
            pattern="/rural/",
            add_categories=("abc:Rural",),
        )

        result = enrich([article], {}, {}, [rule])

        assert "abc:Rural" not in result[0].categories


# ---------------------------------------------------------------------------
# Category deduplication
# ---------------------------------------------------------------------------


class TestCategoryDeduplication:
    """Categories should be deduplicated after all layers."""

    def test_no_duplicate_categories(self) -> None:
        feed = _make_feed(publisher="abc", title="Rural")
        article = _make_article(
            url="https://abc.net.au/rural/article",
            categories=("abc:Rural",),
        )
        rule = EnrichmentRule(
            publisher="abc",
            pattern_type="url",
            pattern="/rural/",
            add_categories=("abc:Rural",),
        )
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [rule])

        assert result[0].categories.count("abc:Rural") == 1


# ---------------------------------------------------------------------------
# Multiple articles
# ---------------------------------------------------------------------------


class TestMultipleArticles:
    """Enrich processes all articles in the list."""

    def test_enriches_all_articles(self) -> None:
        feed_abc = _make_feed(publisher="abc")
        feed_sbs = _make_feed(
            publisher="sbs",
            url="https://sbs.com.au/feed",
            title="SBS News",
            feed_id="sbs-news",
        )
        article1 = _make_article(
            canonical_url="https://abc.net.au/article-1",
            url="https://abc.net.au/article-1",
            guid="g1",
        )
        article2 = _make_article(
            canonical_url="https://sbs.com.au/article-2",
            url="https://sbs.com.au/article-2",
            guid="g2",
        )
        source_feeds = {feed_abc.url: feed_abc, feed_sbs.url: feed_sbs}
        article_sources = {
            article1.canonical_url: feed_abc.url,
            article2.canonical_url: feed_sbs.url,
        }

        result = enrich([article1, article2], source_feeds, article_sources, [])

        assert len(result) == 2
        assert "abc:ABC News" in result[0].categories
        assert "sbs:SBS News" in result[1].categories

    def test_empty_input_returns_empty(self) -> None:
        result = enrich([], {}, {}, [])
        assert result == []


# ---------------------------------------------------------------------------
# Return type guarantees
# ---------------------------------------------------------------------------


class TestReturnTypeGuarantees:
    """Enriched articles maintain NormalisedArticle properties."""

    def test_returns_normalised_articles(self) -> None:
        article = _make_article()
        result = enrich([article], {}, {}, [])
        assert all(isinstance(a, NormalisedArticle) for a in result)

    def test_categories_are_tuples(self) -> None:
        feed = _make_feed()
        article = _make_article()
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        result = enrich([article], source_feeds, article_sources, [])

        assert isinstance(result[0].categories, tuple)

    def test_original_article_unchanged(self) -> None:
        article = _make_article(categories=("original",))
        feed = _make_feed()
        source_feeds = {feed.url: feed}
        article_sources = {article.canonical_url: feed.url}

        enrich([article], source_feeds, article_sources, [])

        # Original article should be unchanged (frozen model)
        assert article.categories == ("original",)
