"""Pydantic models for all pipeline data types."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class DiscoveredFeed(BaseModel):
    """Feed found during discovery."""

    publisher: Literal["abc", "sbs", "smh"]
    url: str
    title: str
    category_hint: str
    feed_id: str
    status: Literal["active", "dead", "stale", "degraded"]
    first_seen: AwareDatetime
    last_seen: AwareDatetime | None = None
    last_checked: AwareDatetime | None = None


class FeedItem(BaseModel):
    """Raw item from a parsed feed."""

    url: str
    title: str
    description: str
    published: AwareDatetime | None = None
    guid: str
    author: str | None = None
    categories: list[str] = Field(default_factory=list)
    image_url: str | None = None
    source_feed_url: str


class FetchedFeed(BaseModel):
    """Feed after fetching, bundling metadata with parsed items."""

    feed: DiscoveredFeed
    items: list[FeedItem]
    was_cached: bool


class NormalisedArticle(BaseModel):
    """Deduplicated article for output. Frozen for hashability."""

    model_config = ConfigDict(frozen=True)

    canonical_url: str
    url: str
    title: str
    description: str
    published: AwareDatetime | None = None
    guid: str
    author: str | None = None
    categories: tuple[str, ...] = ()
    image_url: str | None = None


class PublisherConfig(BaseModel):
    """Publisher configuration."""

    model_config = ConfigDict(frozen=True)

    slug: str
    name: str
    base_url: str
    seed_urls: tuple[str, ...]
    feed_url_template: str | None = None


class EnrichmentRule(BaseModel):
    """Pattern-based tag rule for enriching articles with categories."""

    model_config = ConfigDict(frozen=True)

    publisher: str
    pattern_type: Literal["url", "title", "author"]
    pattern: str
    add_categories: tuple[str, ...]
