"""ABC News feed discovery via CoreMedia collection IDs."""

import re
from datetime import UTC, datetime

from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.models import DiscoveredFeed
from australianewsrss.state import FeedRegistry

SEED_URLS = [
    "https://www.abc.net.au/news",
    "https://www.abc.net.au/news/politics",
    "https://www.abc.net.au/news/business",
    "https://www.abc.net.au/news/world",
    "https://www.abc.net.au/news/sport",
    "https://www.abc.net.au/news/entertainment",
    "https://www.abc.net.au/news/lifestyle",
    "https://www.abc.net.au/news/health",
    "https://www.abc.net.au/news/science",
    "https://www.abc.net.au/news/technology",
    "https://www.abc.net.au/news/environment",
    "https://www.abc.net.au/news/education",
    "https://www.abc.net.au/news/rural",
    "https://www.abc.net.au/news/indigenous",
    "https://www.abc.net.au/news/arts-culture",
]

FEED_URL_TEMPLATE = "https://www.abc.net.au/news/feed/{id}/rss.xml"

_COLLECTION_RE = re.compile(r"coremedia://(dynamic)?collection/(\d+)")


def _extract_collection_ids(html: str) -> list[tuple[bool, str]]:
    """Extract CoreMedia collection IDs from HTML source.

    Returns list of (is_dynamic, id) tuples. Deduplicates by ID.
    """
    seen: set[str] = set()
    results: list[tuple[bool, str]] = []
    for match in _COLLECTION_RE.finditer(html):
        is_dynamic = match.group(1) is not None
        collection_id = match.group(2)
        if collection_id not in seen:
            seen.add(collection_id)
            results.append((is_dynamic, collection_id))
    return results


def discover_feeds(
    client: PoliteHttpClient, registry: FeedRegistry
) -> list[DiscoveredFeed]:
    """Discover ABC RSS feeds from CoreMedia collection IDs in section pages."""
    now = datetime.now(UTC)
    all_collections: dict[str, bool] = {}  # id -> is_dynamic

    # Step 1: Fetch each seed URL and extract collection IDs
    for seed_url in SEED_URLS:
        try:
            html, _cached = client.get(seed_url)
        except Exception:
            continue  # Skip failed pages
        for is_dynamic, collection_id in _extract_collection_ids(html):
            # Keep track of dynamic status (dynamic wins if seen as both)
            if collection_id not in all_collections:
                all_collections[collection_id] = is_dynamic
            elif is_dynamic:
                all_collections[collection_id] = True

    # Step 2: Probe each feed URL and record in registry
    discovered: list[DiscoveredFeed] = []
    for collection_id, is_dynamic in all_collections.items():
        feed_url = FEED_URL_TEMPLATE.format(id=collection_id)

        # Derive category hint from whether it's dynamic
        category_hint = "dynamic" if is_dynamic else "collection"

        try:
            status_code = client.head(feed_url)
        except Exception:
            status_code = 0

        if status_code == 200:
            status = "active"
        else:
            status = "dead"

        feed = DiscoveredFeed(
            publisher="abc",
            url=feed_url,
            title=f"ABC News Feed {collection_id}",
            category_hint=category_hint,
            feed_id=collection_id,
            status=status,
            first_seen=now,
            last_seen=now,
            last_checked=now,
        )
        registry.upsert(feed)
        discovered.append(feed)

    return discovered
