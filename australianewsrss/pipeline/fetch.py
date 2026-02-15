"""Feed fetching and RSS parsing pipeline stage."""

import logging
import re
from datetime import UTC, datetime
from typing import Any

import feedparser

from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.models import DiscoveredFeed, FeedItem, FeedMetadata, FetchedFeed

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def fetch_feeds(
    client: PoliteHttpClient, feeds: list[DiscoveredFeed]
) -> list[FetchedFeed]:
    """Fetch and parse RSS feeds into FetchedFeed objects."""
    results: list[FetchedFeed] = []
    for feed in feeds:
        try:
            xml_string, was_cached = client.get(feed.url)
        except Exception:
            logger.warning("Failed to fetch feed %s", feed.url, exc_info=True)
            continue

        metadata, items = _parse_feed_document(xml_string, feed.url)
        hydrated_feed = _merge_feed_metadata(feed, metadata)
        results.append(
            FetchedFeed(
                feed=hydrated_feed,
                items=items,
                was_cached=was_cached,
            )
        )

    return results


def _parse_feed(xml_string: str, source_feed_url: str) -> list[FeedItem]:
    """Parse RSS XML into FeedItem objects."""
    _, items = _parse_feed_document(xml_string, source_feed_url)
    return items


def _parse_feed_document(
    xml_string: str, source_feed_url: str
) -> tuple[FeedMetadata, list[FeedItem]]:
    """Parse RSS XML into channel metadata and feed items."""
    d = feedparser.parse(xml_string)
    metadata = _extract_feed_metadata(d.feed)

    if d.bozo and len(d.entries) == 0:
        logger.warning(
            "Feed %s is malformed with no entries: %s",
            source_feed_url,
            d.bozo_exception,
        )
        return metadata, []

    items: list[FeedItem] = []
    for entry in d.entries:
        link = entry.get("link", "").strip()
        if not link or not link.startswith(("http://", "https://")):
            logger.debug(
                "Skipping entry with empty link in %s: %s",
                source_feed_url,
                entry.get("title", "(no title)"),
            )
            continue

        published = _extract_published(entry)
        image_url = _extract_image_url(entry)
        categories = [tag["term"] for tag in entry.get("tags", [])]

        item = FeedItem(
            url=link,
            title=entry.get("title", ""),
            description=entry.get("summary", entry.get("description", "")),
            published=published,
            guid=entry.get("id", link),
            author=entry.get("author") or None,
            categories=categories,
            image_url=image_url,
            source_feed_url=source_feed_url,
        )
        items.append(item)

    return metadata, items


def _extract_feed_metadata(feed: Any) -> FeedMetadata:
    """Extract channel-level metadata from a parsed feed."""
    title = _clean_text(feed.get("title"))
    description = _clean_text(feed.get("subtitle")) or _clean_text(
        feed.get("description")
    )
    link = _clean_text(feed.get("link"))
    language = _clean_text(feed.get("language"))

    categories: list[str] = []
    seen_categories: set[str] = set()
    for tag in feed.get("tags", []):
        term = _clean_text(tag.get("term"))
        if term and term not in seen_categories:
            seen_categories.add(term)
            categories.append(term)

    return FeedMetadata(
        title=title,
        description=description,
        link=link,
        language=language,
        categories=tuple(categories),
    )


def _merge_feed_metadata(
    feed: DiscoveredFeed, metadata: FeedMetadata
) -> DiscoveredFeed:
    """Merge parsed metadata into a discovered feed."""
    if metadata == FeedMetadata():
        return feed

    title = metadata.title or feed.title
    category_hint = _derive_category_hint(feed.category_hint, metadata)

    merged_metadata = feed.metadata.model_copy(
        update={
            "title": metadata.title or feed.metadata.title,
            "description": metadata.description or feed.metadata.description,
            "link": metadata.link or feed.metadata.link,
            "language": metadata.language or feed.metadata.language,
            "categories": (
                metadata.categories
                if metadata.categories
                else feed.metadata.categories
            ),
        }
    )

    return feed.model_copy(
        update={
            "title": title,
            "category_hint": category_hint,
            "metadata": merged_metadata,
        }
    )


def _derive_category_hint(existing_hint: str, metadata: FeedMetadata) -> str:
    """Derive a filter-friendly category hint from channel metadata."""
    if not _is_generic_hint(existing_hint):
        return existing_hint

    for candidate in (*metadata.categories, metadata.title):
        if not candidate:
            continue
        slug = _slugify(candidate)
        if slug:
            return slug
    return existing_hint


def _is_generic_hint(hint: str) -> bool:
    """Return True when the hint is a low-signal placeholder."""
    return hint in {"collection", "dynamic", "general"} or hint.isdigit()


def _slugify(value: str) -> str:
    """Normalise a free-text value into a lowercase slug."""
    return _SLUG_RE.sub("-", value.lower()).strip("-")


def _clean_text(value: Any) -> str | None:
    """Trim textual values and normalise empty strings to None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_published(entry: Any) -> datetime | None:
    """Extract published datetime from feedparser entry."""
    parsed = entry.get("published_parsed")
    if parsed is None:
        parsed = entry.get("updated_parsed")
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=UTC)
    except ValueError, TypeError:
        return None


def _extract_image_url(entry: Any) -> str | None:
    """Extract image URL from media:content or enclosures."""
    # Try media_content first
    for media in entry.get("media_content", []):
        medium = media.get("medium", "")
        content_type = media.get("type", "")
        if medium == "image" or content_type.startswith("image/"):
            return media.get("url")

    # Try enclosures
    for enclosure in entry.get("enclosures", []):
        if enclosure.get("type", "").startswith("image/"):
            return enclosure.get("href") or enclosure.get("url")

    return None
