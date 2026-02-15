"""SBS News feed discovery via Brightspot CMS feeds page and section link tags."""

import logging
import re
from datetime import UTC, datetime

from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.models import DiscoveredFeed
from australianewsrss.state import FeedRegistry

FEEDS_PAGE_URL = "https://www.sbs.com.au/news/feeds"

SECTION_SEED_URLS = [
    "https://www.sbs.com.au/news",
    "https://www.sbs.com.au/news/topic/latest",
    "https://www.sbs.com.au/news/topic/australia",
    "https://www.sbs.com.au/news/topic/world",
    "https://www.sbs.com.au/news/topic/business",
    "https://www.sbs.com.au/news/topic/sport",
    "https://www.sbs.com.au/news/topic/technology",
    "https://www.sbs.com.au/news/topic/environment",
]

# Regex to find RSS feed URLs in href attributes on the SBS feeds page
_FEED_LINK_RE = re.compile(
    r'href=["\']([^"\']*(?:/feed|\.rss|/rss)[^"\']*)["\']', re.IGNORECASE
)

# Regex to find <link rel="alternate" type="application/rss+xml" href="...">
_ALTERNATE_LINK_RE = re.compile(
    r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/rss\+xml["\']'
    r'[^>]+href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
# Also match when attributes are in different order
_ALTERNATE_LINK_RE2 = re.compile(
    r'<link[^>]+href=["\']([^"\']+)["\'][^>]+type=["\']application/rss\+xml["\']',
    re.IGNORECASE,
)

# Extract topic slugs from navigation links like /news/topic/{slug}
_TOPIC_SLUG_RE = re.compile(r"/news/topic/([a-z0-9-]+)", re.IGNORECASE)

logger = logging.getLogger(__name__)


def _extract_feed_urls_from_feeds_page(html: str) -> set[str]:
    """Extract RSS feed URLs from the SBS feeds page."""
    urls: set[str] = set()
    for match in _FEED_LINK_RE.finditer(html):
        url = match.group(1)
        if url.startswith("/"):
            url = f"https://www.sbs.com.au{url}"
        urls.add(url)
    return urls


def _extract_alternate_links(html: str) -> set[str]:
    """Extract feed URLs from <link rel="alternate" type="application/rss+xml"> tags."""
    urls: set[str] = set()
    for pattern in [_ALTERNATE_LINK_RE, _ALTERNATE_LINK_RE2]:
        for match in pattern.finditer(html):
            url = match.group(1)
            if url.startswith("/"):
                url = f"https://www.sbs.com.au{url}"
            urls.add(url)
    return urls


def _extract_topic_slugs(html: str) -> set[str]:
    """Extract topic slugs from navigation links."""
    return {match.group(1) for match in _TOPIC_SLUG_RE.finditer(html)}


def discover_feeds(
    client: PoliteHttpClient, registry: FeedRegistry
) -> list[DiscoveredFeed]:
    """Discover SBS RSS feeds from feeds page and section pages."""
    now = datetime.now(UTC)
    feed_urls: set[str] = set()
    topic_slugs: set[str] = set()

    # Step 1: Crawl the SBS feeds page
    try:
        html, _cached = client.get(FEEDS_PAGE_URL)
        feed_urls.update(_extract_feed_urls_from_feeds_page(html))
    except Exception:
        logger.warning(
            "Failed to fetch SBS feeds page %s", FEEDS_PAGE_URL, exc_info=True
        )

    # Step 2: Crawl section pages for <link rel="alternate"> and topic slugs
    for section_url in SECTION_SEED_URLS:
        try:
            html, _cached = client.get(section_url)
            feed_urls.update(_extract_alternate_links(html))
            topic_slugs.update(_extract_topic_slugs(html))
        except Exception:
            logger.warning(
                "Failed to fetch SBS section URL %s", section_url, exc_info=True
            )
            continue

    # Step 3: Construct topic feed URLs from discovered slugs
    for slug in topic_slugs:
        feed_urls.add(f"https://www.sbs.com.au/news/topic/{slug}/feed")

    # Step 4: Probe each feed URL
    discovered: list[DiscoveredFeed] = []
    for feed_url in sorted(feed_urls):
        try:
            status_code = client.head(feed_url)
        except Exception:
            logger.warning("Failed to probe feed URL %s", feed_url, exc_info=True)
            status_code = 0

        status = "active" if status_code == 200 else "dead"

        # Derive feed_id from the URL path, extracting the meaningful segment
        path = feed_url.replace("https://www.sbs.com.au/news/", "").rstrip("/")
        if path == "feed":
            feed_id = "main"
        elif path.startswith("topic/") and path.endswith("/feed"):
            feed_id = path.split("/")[1]
        else:
            feed_id = path.replace("/", "-")
        title = f"SBS News - {feed_id.replace('-', ' ').title()}"

        feed = DiscoveredFeed(
            publisher="sbs",
            url=feed_url,
            title=title,
            category_hint=feed_id,
            feed_id=feed_id,
            status=status,
            first_seen=now,
            last_seen=now,
            last_checked=now,
        )
        registry.upsert(feed)
        discovered.append(feed)

    return discovered
