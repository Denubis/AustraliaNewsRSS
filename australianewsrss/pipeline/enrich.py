"""Three-layer tag enrichment pipeline stage."""

import re

from australianewsrss.models import (
    DiscoveredFeed,
    EnrichmentRule,
    NormalisedArticle,
)


def enrich(
    articles: list[NormalisedArticle],
    source_feeds: dict[str, DiscoveredFeed],
    article_sources: dict[str, str],
    rules: list[EnrichmentRule],
) -> list[NormalisedArticle]:
    """Apply three enrichment layers to articles.

    Layer 1: Source feed tags -- adds ``publisher:feed_title`` from the
        source feed that originally contained the article (AC2.4).
    Layer 2: Upstream passthrough -- categories already present on the
        article from the upstream feed are preserved (AC2.5).
    Layer 3: Pattern-based rules -- regex rules matched against URL,
        title, or author fields add extra categories (AC2.6).

    Args:
        articles: Articles to enrich.
        source_feeds: Mapping of source feed URL to DiscoveredFeed.
        article_sources: Mapping of article canonical_url to the source
            feed URL it came from (built during merge/dedup).
        rules: Pattern-based enrichment rules to apply.

    Returns:
        New list of NormalisedArticle instances with enriched categories.
    """
    enriched: list[NormalisedArticle] = []

    for article in articles:
        categories = list(article.categories)

        # Determine article publisher from source feed
        source_url = article_sources.get(article.canonical_url)
        feed = (
            source_feeds[source_url]
            if source_url and source_url in source_feeds
            else None
        )

        # Layer 1: Source feed tag
        if feed is not None:
            tag = f"{feed.publisher}:{feed.title}"
            if tag not in categories:
                categories.append(tag)

        # Layer 2: Upstream passthrough -- already in categories, no-op.

        # Layer 3: Pattern-based rules
        article_publisher = feed.publisher if feed is not None else None

        for rule in rules:
            # Only apply rules for matching publisher
            if article_publisher is None:
                continue
            if rule.publisher != article_publisher:
                continue

            # Get the field to match against
            if rule.pattern_type == "url":
                field_value = article.url
            elif rule.pattern_type == "title":
                field_value = article.title
            elif rule.pattern_type == "author":
                field_value = article.author or ""
            else:  # pragma: no cover
                continue

            if re.search(rule.pattern, field_value):
                for cat in rule.add_categories:
                    if cat not in categories:
                        categories.append(cat)

        enriched.append(article.model_copy(update={"categories": tuple(categories)}))

    return enriched
