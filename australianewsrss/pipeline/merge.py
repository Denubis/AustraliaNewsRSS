"""Article merge and deduplication pipeline stage."""

from datetime import UTC, datetime
from urllib.parse import urlparse, urlunparse

from australianewsrss.models import FeedItem, FetchedFeed, NormalisedArticle

# Timezone-aware sentinels for sorting None-published items.
_DT_MAX = datetime.max.replace(tzinfo=UTC)
_DT_MIN = datetime.min.replace(tzinfo=UTC)


def canonicalise_url(url: str) -> str:
    """Normalise URL for deduplication.

    - Normalise http:// to https://
    - Strip query parameters
    - Strip fragment
    - Strip trailing slashes from path
    """
    parsed = urlparse(url)
    scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
    path = parsed.path.rstrip("/")
    return urlunparse((scheme, parsed.netloc, path, "", "", ""))


def merge_and_dedup(
    fetched: list[FetchedFeed],
) -> list[NormalisedArticle]:
    """Merge items from all feeds, deduplicate by canonical URL.

    Duplicate articles retain the union of all category tags (AC2.3).
    Output sorted by published date, newest first.
    """
    # Group items by canonical URL
    groups: dict[str, list[tuple[FetchedFeed, FeedItem]]] = {}
    for ff in fetched:
        for item in ff.items:
            canonical = canonicalise_url(item.url)
            if canonical not in groups:
                groups[canonical] = []
            groups[canonical].append((ff, item))

    # Merge each group into a NormalisedArticle
    articles: list[NormalisedArticle] = []
    for canonical_url, group in groups.items():
        # Keep the item with earliest published date;
        # items without published go last so dated items are preferred.
        group.sort(
            key=lambda x: x[1].published or _DT_MAX,
        )
        _primary_ff, primary_item = group[0]

        # Union all categories from all copies, preserving insertion order
        all_categories: list[str] = []
        seen_categories: set[str] = set()
        for _, item in group:
            for cat in item.categories:
                if cat not in seen_categories:
                    seen_categories.add(cat)
                    all_categories.append(cat)

        article = NormalisedArticle(
            canonical_url=canonical_url,
            url=primary_item.url,
            title=primary_item.title,
            description=primary_item.description,
            published=primary_item.published,
            guid=primary_item.guid,
            author=primary_item.author,
            categories=tuple(all_categories),
            image_url=primary_item.image_url,
        )
        articles.append(article)

    # Sort by published date, newest first.
    # Articles without published date sort last.
    articles.sort(
        key=lambda a: a.published if a.published else _DT_MIN,
        reverse=True,
    )

    return articles
