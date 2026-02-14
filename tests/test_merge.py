"""Tests for australianewsrss.pipeline.merge module."""

from datetime import UTC, datetime

from australianewsrss.models import (
    DiscoveredFeed,
    FeedItem,
    FetchedFeed,
    NormalisedArticle,
)
from australianewsrss.pipeline.merge import canonicalise_url, merge_and_dedup

NOW = datetime(2026, 2, 14, 12, 0, 0, tzinfo=UTC)
EARLIER = datetime(2026, 2, 14, 10, 0, 0, tzinfo=UTC)
LATEST = datetime(2026, 2, 14, 14, 0, 0, tzinfo=UTC)


def _make_feed(
    publisher: str = "abc",
    url: str = "https://abc.net.au/feed",
) -> DiscoveredFeed:
    return DiscoveredFeed(
        publisher=publisher,
        url=url,
        title=f"{publisher.upper()} Feed",
        category_hint="news",
        feed_id=f"{publisher}-news",
        status="active",
        first_seen=NOW,
    )


def _make_item(
    url: str = "https://abc.net.au/news/article-1",
    title: str = "Article One",
    guid: str = "guid-1",
    published: datetime | None = NOW,
    categories: list[str] | None = None,
    source_feed_url: str = "https://abc.net.au/feed",
) -> FeedItem:
    return FeedItem(
        url=url,
        title=title,
        description="A test article.",
        published=published,
        guid=guid,
        categories=categories or [],
        source_feed_url=source_feed_url,
    )


def _make_fetched(
    items: list[FeedItem],
    publisher: str = "abc",
    feed_url: str = "https://abc.net.au/feed",
) -> FetchedFeed:
    return FetchedFeed(
        feed=_make_feed(publisher=publisher, url=feed_url),
        items=items,
        was_cached=False,
    )


# ---------------------------------------------------------------------------
# canonicalise_url
# ---------------------------------------------------------------------------


class TestCanonicaliseUrl:
    """Unit tests for URL canonicalisation."""

    def test_strips_query_parameters(self) -> None:
        result = canonicalise_url("https://abc.net.au/news/article?ref=rss&v=2")
        assert result == "https://abc.net.au/news/article"

    def test_normalises_http_to_https(self) -> None:
        result = canonicalise_url("http://abc.net.au/news/article")
        assert result == "https://abc.net.au/news/article"

    def test_strips_trailing_slash(self) -> None:
        result = canonicalise_url("https://abc.net.au/news/article/")
        assert result == "https://abc.net.au/news/article"

    def test_strips_fragment(self) -> None:
        result = canonicalise_url("https://abc.net.au/news/article#comments")
        assert result == "https://abc.net.au/news/article"

    def test_all_normalisations_combined(self) -> None:
        result = canonicalise_url("http://abc.net.au/news/article/?ref=rss#top")
        assert result == "https://abc.net.au/news/article"

    def test_preserves_path(self) -> None:
        result = canonicalise_url("https://abc.net.au/news/2026-02-14/some-slug/12345")
        assert result == "https://abc.net.au/news/2026-02-14/some-slug/12345"

    def test_preserves_https(self) -> None:
        result = canonicalise_url("https://abc.net.au/news/article")
        assert result == "https://abc.net.au/news/article"

    def test_preserves_non_http_scheme(self) -> None:
        """Non-HTTP schemes should not be changed to https."""
        result = canonicalise_url("ftp://example.com/file")
        assert result == "ftp://example.com/file"

    def test_root_path_becomes_empty(self) -> None:
        result = canonicalise_url("https://abc.net.au/")
        assert result == "https://abc.net.au"


# ---------------------------------------------------------------------------
# merge_and_dedup
# ---------------------------------------------------------------------------


class TestMergeAndDedup:
    """Integration tests for the merge-and-dedup pipeline stage."""

    def test_single_feed_single_item(self) -> None:
        item = _make_item()
        fetched = [_make_fetched([item])]

        result = merge_and_dedup(fetched)

        assert len(result) == 1
        assert isinstance(result[0], NormalisedArticle)
        assert result[0].title == "Article One"
        assert result[0].canonical_url == "https://abc.net.au/news/article-1"
        assert result[0].url == "https://abc.net.au/news/article-1"

    def test_deduplicates_by_canonical_url(self) -> None:
        """Same article URL with different query strings deduplicates."""
        item1 = _make_item(
            url="https://abc.net.au/news/article-1?ref=rss",
            guid="guid-1",
            published=EARLIER,
        )
        item2 = _make_item(
            url="https://abc.net.au/news/article-1?ref=homepage",
            guid="guid-2",
            published=NOW,
        )
        fetched = [
            _make_fetched([item1]),
            _make_fetched([item2], publisher="sbs", feed_url="https://sbs.com.au/feed"),
        ]

        result = merge_and_dedup(fetched)

        assert len(result) == 1
        assert result[0].canonical_url == "https://abc.net.au/news/article-1"

    def test_dedup_keeps_earliest_published(self) -> None:
        """When duplicates exist, keep the item with earliest published date."""
        item_later = _make_item(
            url="https://abc.net.au/news/article-1",
            guid="guid-later",
            published=LATEST,
        )
        item_earlier = _make_item(
            url="https://abc.net.au/news/article-1?ref=rss",
            guid="guid-earlier",
            published=EARLIER,
        )
        fetched = [
            _make_fetched([item_later]),
            _make_fetched(
                [item_earlier],
                publisher="sbs",
                feed_url="https://sbs.com.au/feed",
            ),
        ]

        result = merge_and_dedup(fetched)

        assert len(result) == 1
        assert result[0].published == EARLIER
        assert result[0].guid == "guid-earlier"

    def test_dedup_unions_categories(self) -> None:
        """Duplicate articles merge categories from all copies (AC2.3)."""
        item1 = _make_item(
            url="https://abc.net.au/news/article-1",
            guid="guid-1",
            categories=["politics", "australia"],
        )
        item2 = _make_item(
            url="https://abc.net.au/news/article-1?ref=rss",
            guid="guid-2",
            categories=["australia", "breaking"],
        )
        fetched = [
            _make_fetched([item1]),
            _make_fetched([item2], publisher="sbs", feed_url="https://sbs.com.au/feed"),
        ]

        result = merge_and_dedup(fetched)

        assert len(result) == 1
        cats = result[0].categories
        assert isinstance(cats, tuple)
        assert set(cats) == {"politics", "australia", "breaking"}
        # "australia" should appear only once (deduped)
        assert cats.count("australia") == 1

    def test_categories_preserve_insertion_order(self) -> None:
        """Category union preserves order of first encounter."""
        item1 = _make_item(
            url="https://abc.net.au/news/article-1",
            guid="guid-1",
            categories=["politics", "australia"],
        )
        item2 = _make_item(
            url="https://abc.net.au/news/article-1",
            guid="guid-2",
            categories=["breaking", "australia"],
        )
        fetched = [
            _make_fetched([item1]),
            _make_fetched([item2], publisher="sbs", feed_url="https://sbs.com.au/feed"),
        ]

        result = merge_and_dedup(fetched)

        assert result[0].categories == (
            "politics",
            "australia",
            "breaking",
        )

    def test_output_sorted_newest_first(self) -> None:
        """Output articles sorted by published date, newest first."""
        item_old = _make_item(
            url="https://abc.net.au/news/old",
            guid="old",
            published=EARLIER,
        )
        item_mid = _make_item(
            url="https://abc.net.au/news/mid",
            guid="mid",
            published=NOW,
        )
        item_new = _make_item(
            url="https://abc.net.au/news/new",
            guid="new",
            published=LATEST,
        )
        fetched = [_make_fetched([item_old, item_mid, item_new])]

        result = merge_and_dedup(fetched)

        assert len(result) == 3
        assert result[0].published == LATEST
        assert result[1].published == NOW
        assert result[2].published == EARLIER

    def test_unpublished_items_sort_last(self) -> None:
        """Articles without published date sort after all dated articles."""
        item_dated = _make_item(
            url="https://abc.net.au/news/dated",
            guid="dated",
            published=NOW,
        )
        item_undated = _make_item(
            url="https://abc.net.au/news/undated",
            guid="undated",
            published=None,
        )
        fetched = [_make_fetched([item_undated, item_dated])]

        result = merge_and_dedup(fetched)

        assert len(result) == 2
        assert result[0].published == NOW
        assert result[1].published is None

    def test_empty_input_returns_empty(self) -> None:
        result = merge_and_dedup([])
        assert result == []

    def test_multiple_feeds_no_duplicates(self) -> None:
        """Multiple feeds with distinct articles all appear in output."""
        item1 = _make_item(
            url="https://abc.net.au/news/article-1",
            guid="guid-1",
        )
        item2 = _make_item(
            url="https://sbs.com.au/news/article-2",
            guid="guid-2",
            source_feed_url="https://sbs.com.au/feed",
        )
        fetched = [
            _make_fetched([item1]),
            _make_fetched(
                [item2],
                publisher="sbs",
                feed_url="https://sbs.com.au/feed",
            ),
        ]

        result = merge_and_dedup(fetched)

        assert len(result) == 2

    def test_http_https_dedup(self) -> None:
        """http and https variants of same URL are treated as duplicate."""
        item1 = _make_item(
            url="http://abc.net.au/news/article-1",
            guid="guid-1",
        )
        item2 = _make_item(
            url="https://abc.net.au/news/article-1",
            guid="guid-2",
        )
        fetched = [_make_fetched([item1, item2])]

        result = merge_and_dedup(fetched)

        assert len(result) == 1

    def test_dedup_with_none_published_keeps_dated_item(self) -> None:
        """When deduplicating, prefer item with a published date."""
        item_dated = _make_item(
            url="https://abc.net.au/news/article-1",
            guid="guid-dated",
            published=NOW,
            categories=["from-dated"],
        )
        item_undated = _make_item(
            url="https://abc.net.au/news/article-1",
            guid="guid-undated",
            published=None,
            categories=["from-undated"],
        )
        fetched = [_make_fetched([item_undated, item_dated])]

        result = merge_and_dedup(fetched)

        assert len(result) == 1
        # The dated item should be the primary (earliest published)
        assert result[0].published == NOW
        assert result[0].guid == "guid-dated"
        # But categories from both should be merged
        assert "from-dated" in result[0].categories
        assert "from-undated" in result[0].categories
