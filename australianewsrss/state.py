"""Persistent state management for feed registry and HTTP cache."""

import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from australianewsrss.models import DiscoveredFeed


class FeedRegistry:
    """Manages discovered feeds via JSON file persistence.

    Feeds are stored internally as a dict keyed by URL for O(1) lookup.
    The on-disk format is a JSON array sorted by (publisher, url) for
    stable git diffs.
    """

    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._feeds_path = self._state_dir / "feeds.json"
        self._feeds: dict[str, DiscoveredFeed] = {}
        for feed in self.load():
            self._feeds[feed.url] = feed

    def load(self) -> list[DiscoveredFeed]:
        """Read and parse feeds.json. Return empty list if file missing."""
        if not self._feeds_path.exists():
            return []
        raw = json.loads(self._feeds_path.read_text())
        return [DiscoveredFeed.model_validate(entry) for entry in raw]

    def save(self, feeds: list[DiscoveredFeed]) -> None:
        """Write feeds to feeds.json, sorted by publisher then URL."""
        sorted_feeds = sorted(feeds, key=lambda f: (f.publisher, f.url))
        data = [f.model_dump(mode="json") for f in sorted_feeds]
        self._feeds_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    def upsert(self, feed: DiscoveredFeed) -> None:
        """Add or update a feed by URL.

        If the feed is new, set first_seen to now. Always update last_seen
        and last_checked. Saves to disk after upserting.
        """
        now = datetime.now(UTC)
        existing = self._feeds.get(feed.url)
        if existing is None:
            updated = feed.model_copy(
                update={
                    "first_seen": now,
                    "last_seen": now,
                    "last_checked": now,
                }
            )
        else:
            updated = feed.model_copy(
                update={
                    "first_seen": existing.first_seen,
                    "last_seen": now,
                    "last_checked": now,
                }
            )
        self._feeds[updated.url] = updated
        self.save(list(self._feeds.values()))

    def get_feeds(self, publisher: str | None = None) -> list[DiscoveredFeed]:
        """Filter by publisher slug or return all."""
        feeds = list(self._feeds.values())
        if publisher is not None:
            feeds = [f for f in feeds if f.publisher == publisher]
        return feeds

    def mark_status(self, url: str, status: str) -> None:
        """Update a feed's status. Save after change."""
        feed = self._feeds.get(url)
        if feed is None:
            return
        self._feeds[url] = feed.model_copy(update={"status": status})
        self.save(list(self._feeds.values()))

    def mark_stale_feeds(self, stale_threshold_days: int = 14) -> list[DiscoveredFeed]:
        """Mark active feeds as stale if last_seen exceeds the threshold.

        Feeds already marked dead are not affected. Returns the list of
        feeds that were marked stale.
        """
        now = datetime.now(UTC)
        threshold = now - timedelta(days=stale_threshold_days)
        stale: list[DiscoveredFeed] = []

        for url, feed in self._feeds.items():
            if feed.status != "active":
                continue
            if feed.last_seen is not None and feed.last_seen < threshold:
                updated = feed.model_copy(update={"status": "stale"})
                self._feeds[url] = updated
                stale.append(updated)

        if stale:
            self.save(list(self._feeds.values()))

        return stale


class HttpCache:
    """SQLite-based ETag cache for HTTP responses.

    Uses fresh connections per operation and WAL mode for concurrency.
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Create a fresh connection with WAL mode enabled."""
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        """Create the cache table if it does not exist."""
        conn = self._connect()
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS http_cache "
                "(url TEXT PRIMARY KEY, etag TEXT, data TEXT, timestamp INTEGER)"
            )
            conn.commit()
        finally:
            conn.close()

    def get(self, url: str) -> tuple[str | None, str | None]:
        """Return (etag, cached_data) or (None, None)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT etag, data FROM http_cache WHERE url = ?", (url,)
            ).fetchone()
            if row is None:
                return None, None
            return row[0], row[1]
        finally:
            conn.close()

    def put(self, url: str, etag: str, data: str) -> None:
        """Upsert cache entry with current timestamp."""
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO http_cache (url, etag, data, timestamp) "
                "VALUES (?, ?, ?, ?)",
                (url, etag, data, int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()

    def clear(self) -> None:
        """Drop all cache entries."""
        conn = self._connect()
        try:
            conn.execute("DELETE FROM http_cache")
            conn.commit()
        finally:
            conn.close()
