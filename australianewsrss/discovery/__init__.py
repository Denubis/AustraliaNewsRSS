"""Publisher-specific feed discovery modules."""

from typing import Protocol

from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.models import DiscoveredFeed
from australianewsrss.state import FeedRegistry


class DiscoveryFunction(Protocol):
    def __call__(
        self, client: PoliteHttpClient, registry: FeedRegistry
    ) -> list[DiscoveredFeed]: ...
