"""Feed fetching and RSS parsing pipeline stage."""

import logging
from datetime import UTC, datetime
from typing import Any

import feedparser

from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.models import DiscoveredFeed, FeedItem, FetchedFeed

logger = logging.getLogger(__name__)


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

        items = _parse_feed(xml_string, feed.url)
        results.append(FetchedFeed(feed=feed, items=items, was_cached=was_cached))

    return results


def _parse_feed(xml_string: str, source_feed_url: str) -> list[FeedItem]:
    """Parse RSS XML into FeedItem objects."""
    d = feedparser.parse(xml_string)

    if d.bozo and len(d.entries) == 0:
        logger.warning(
            "Feed %s is malformed with no entries: %s",
            source_feed_url,
            d.bozo_exception,
        )
        return []

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

    return items


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
