"""Publisher registry mapping slug to discovery config and functions."""

from collections.abc import Callable

from australianewsrss.discovery import abc, sbs, smh
from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.models import DiscoveredFeed, PublisherConfig
from australianewsrss.state import FeedRegistry

# Data: PublisherConfig instances (frozen Pydantic models — no callables)
PUBLISHERS: dict[str, PublisherConfig] = {
    "abc": PublisherConfig(
        slug="abc",
        name="ABC News",
        base_url="https://www.abc.net.au",
        seed_urls=tuple(abc.SEED_URLS),
        feed_url_template=abc.FEED_URL_TEMPLATE,
    ),
    "sbs": PublisherConfig(
        slug="sbs",
        name="SBS News",
        base_url="https://www.sbs.com.au",
        seed_urls=(sbs.FEEDS_PAGE_URL, *sbs.SECTION_SEED_URLS),
    ),
    "smh": PublisherConfig(
        slug="smh",
        name="Sydney Morning Herald",
        base_url="https://www.smh.com.au",
        seed_urls=(
            smh.HOMEPAGE_URL,
            *(f"{smh.BASE_URL}{p}" for p in smh.STATIC_FEED_PATHS),
        ),
    ),
}

# Type alias for discovery function signature
DiscoveryFunc = Callable[[PoliteHttpClient, FeedRegistry], list[DiscoveredFeed]]

# Behaviour: maps slug to discovery module's discover_feeds function
DISCOVERY_FUNCTIONS: dict[str, DiscoveryFunc] = {
    "abc": abc.discover_feeds,
    "sbs": sbs.discover_feeds,
    "smh": smh.discover_feeds,
}


def get_publisher(slug: str) -> PublisherConfig:
    """Look up publisher config by slug. Raises KeyError if not found."""
    return PUBLISHERS[slug]


def get_all_publishers() -> list[PublisherConfig]:
    """Return all publisher configs."""
    return list(PUBLISHERS.values())


def get_discovery_function(slug: str) -> DiscoveryFunc:
    """Return the discovery function for a publisher slug."""
    return DISCOVERY_FUNCTIONS[slug]
