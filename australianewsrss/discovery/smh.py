"""SMH feed discovery via static feed paths and navigation crawl."""

import re
from datetime import UTC, datetime

from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.models import DiscoveredFeed
from australianewsrss.state import FeedRegistry

HOMEPAGE_URL = "https://www.smh.com.au/"

# Known static feed paths (confirmed working)
STATIC_FEED_PATHS = [
    "/rss/feed.xml",  # Main/Latest
    "/rss/national.xml",
    "/rss/politics/federal.xml",
    "/rss/nsw.xml",
    "/rss/business.xml",
    "/rss/world.xml",
    "/rss/technology.xml",
    "/rss/culture.xml",
    "/rss/lifestyle.xml",
    "/rss/environment.xml",
    "/rss/property.xml",
    "/rss/goodfood.xml",
    "/rss/traveller.xml",
    "/rss/sport.xml",
    "/rss/sport/rugby-league.xml",
    "/rss/sport/rugby-union.xml",
    "/rss/sport/afl.xml",
]

BASE_URL = "https://www.smh.com.au"

# Extract section slugs from navigation links
# e.g. href="/section-name" or href="/section-name/"
_NAV_SLUG_RE = re.compile(r'href=["\']/([\w-]+)/?["\']', re.IGNORECASE)

# Slugs to exclude from feed URL construction (not content sections)
_EXCLUDED_SLUGS = frozenset(
    {
        "login",
        "signup",
        "subscribe",
        "about",
        "contact",
        "privacy",
        "terms",
        "sitemap",
        "search",
        "newsletters",
        "app",
        "mysmh",
        "video",
        "podcast",
        "podcasts",
        "photos",
        "interactive",
        "masthead",
        "advertising",
        "careers",
        "help",
    }
)


def _extract_nav_slugs(html: str) -> set[str]:
    """Extract section slugs from homepage navigation links."""
    slugs: set[str] = set()
    for match in _NAV_SLUG_RE.finditer(html):
        slug = match.group(1).lower()
        if slug not in _EXCLUDED_SLUGS and len(slug) > 1:
            slugs.add(slug)
    return slugs


def discover_feeds(
    client: PoliteHttpClient, registry: FeedRegistry
) -> list[DiscoveredFeed]:
    """Discover SMH RSS feeds from static paths and navigation crawl."""
    now = datetime.now(UTC)
    feed_urls: set[str] = set()

    # Step 1: Add all known static feed URLs
    for path in STATIC_FEED_PATHS:
        feed_urls.add(f"{BASE_URL}{path}")

    # Step 2: Crawl homepage for navigation section slugs
    try:
        html, _cached = client.get(HOMEPAGE_URL)
        nav_slugs = _extract_nav_slugs(html)
        # Construct feed URLs for discovered sections
        # Skip slugs that are already covered by static paths
        static_slugs = {
            path.split("/")[2].replace(".xml", "")
            for path in STATIC_FEED_PATHS
            if len(path.split("/")) > 2
        }
        for slug in nav_slugs:
            if slug not in static_slugs:
                feed_urls.add(f"{BASE_URL}/rss/{slug}.xml")
    except Exception:
        pass

    # Step 3: Probe each feed URL
    discovered: list[DiscoveredFeed] = []
    for feed_url in sorted(feed_urls):
        try:
            status_code = client.head(feed_url)
        except Exception:
            status_code = 0

        status = "active" if status_code == 200 else "dead"

        # Derive feed_id and title from URL path
        path = feed_url.replace(f"{BASE_URL}/rss/", "").replace(".xml", "")
        feed_id = path.replace("/", "-")
        title = f"SMH - {path.replace('/', ' > ').replace('-', ' ').title()}"

        feed = DiscoveredFeed(
            publisher="smh",
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
