"""Tests for the australianewsrss CLI — Phase 7 integration tests."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from typer.testing import CliRunner

from australianewsrss.cli import app
from australianewsrss.models import (
    DiscoveredFeed,
    FeedItem,
    FetchedFeed,
)
from australianewsrss.state import FeedRegistry

runner = CliRunner()
NOW = datetime(2026, 2, 14, 12, 0, 0, tzinfo=UTC)


def _feed(
    publisher: Literal["abc", "sbs", "smh"] = "abc",
    url: str = "https://abc.net.au/news/feed/123/rss.xml",
    title: str = "ABC Top Stories",
    feed_id: str = "abc-123",
    status: str = "active",
) -> DiscoveredFeed:
    return DiscoveredFeed(
        publisher=publisher,
        url=url,
        title=title,
        category_hint="news",
        feed_id=feed_id,
        status=status,
        first_seen=NOW,
        last_seen=NOW,
        last_checked=NOW,
    )


def _item(
    url: str = "https://abc.net.au/news/article-1",
    title: str = "Test Article",
    source_feed_url: str = "https://abc.net.au/news/feed/123/rss.xml",
) -> FeedItem:
    return FeedItem(
        url=url,
        title=title,
        description="A test article.",
        published=NOW,
        guid=url,
        source_feed_url=source_feed_url,
    )


def _populate(state_dir: Path, feeds: list[DiscoveredFeed]) -> None:
    """Create a FeedRegistry and populate with feeds."""
    reg = FeedRegistry(state_dir)
    for f in feeds:
        reg.upsert(f)


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------


class TestCLIHelp:
    def test_main_help_shows_all_commands(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("discover", "generate", "test-live"):
            assert cmd in result.output

    def test_discover_help_shows_options(self) -> None:
        result = runner.invoke(app, ["discover", "--help"])
        assert result.exit_code == 0
        assert "--publisher" in result.output
        assert "--state-dir" in result.output

    def test_generate_help_shows_options(self) -> None:
        result = runner.invoke(app, ["generate", "--help"])
        assert result.exit_code == 0
        assert "--output-dir" in result.output
        assert "--base-url" in result.output
        assert "--state-dir" in result.output


# ---------------------------------------------------------------------------
# Discover
# ---------------------------------------------------------------------------


class TestDiscoverCommand:
    def test_discovers_all_publishers_by_default(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        calls: list[str] = []

        def mock_abc(client, registry):
            calls.append("abc")
            registry.upsert(_feed(publisher="abc"))
            return [_feed(publisher="abc")]

        def mock_sbs(client, registry):
            calls.append("sbs")
            f = _feed(publisher="sbs", url="https://sbs.com.au/feed", feed_id="sbs-1")
            registry.upsert(f)
            return [f]

        def mock_smh(client, registry):
            calls.append("smh")
            f = _feed(publisher="smh", url="https://smh.com.au/feed", feed_id="smh-1")
            registry.upsert(f)
            return [f]

        monkeypatch.setattr(
            "australianewsrss.publishers.DISCOVERY_FUNCTIONS",
            {"abc": mock_abc, "sbs": mock_sbs, "smh": mock_smh},
        )

        state_dir = tmp_path / "state"
        result = runner.invoke(app, ["discover", "--state-dir", str(state_dir)])

        assert result.exit_code == 0
        assert set(calls) == {"abc", "sbs", "smh"}

    def test_discovers_only_specified_publisher(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        calls: list[str] = []

        def mock_abc(client, registry):
            calls.append("abc")
            return []

        monkeypatch.setattr(
            "australianewsrss.publishers.DISCOVERY_FUNCTIONS",
            {
                "abc": mock_abc,
                "sbs": lambda c, r: (_ for _ in ()).throw(AssertionError("sbs called")),
                "smh": lambda c, r: (_ for _ in ()).throw(AssertionError("smh called")),
            },
        )

        state_dir = tmp_path / "state"
        result = runner.invoke(
            app,
            ["discover", "--publisher", "abc", "--state-dir", str(state_dir)],
        )

        assert result.exit_code == 0
        assert calls == ["abc"]

    def test_invalid_publisher_exits_with_error(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "state"
        result = runner.invoke(
            app,
            [
                "discover",
                "--publisher",
                "invalid",
                "--state-dir",
                str(state_dir),
            ],
        )

        assert result.exit_code == 1
        # Should list valid publisher slugs
        assert "abc" in result.output
        assert "sbs" in result.output
        assert "smh" in result.output

    def test_publisher_failure_does_not_block_others(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """AC6.3: single publisher discovery failure does not block others."""
        calls: list[str] = []

        def mock_abc_fail(client, registry):
            calls.append("abc")
            raise RuntimeError("ABC discovery failed")

        def mock_sbs_ok(client, registry):
            calls.append("sbs")
            f = _feed(publisher="sbs", url="https://sbs.com.au/feed", feed_id="sbs-1")
            registry.upsert(f)
            return [f]

        def mock_smh_ok(client, registry):
            calls.append("smh")
            f = _feed(publisher="smh", url="https://smh.com.au/feed", feed_id="smh-1")
            registry.upsert(f)
            return [f]

        monkeypatch.setattr(
            "australianewsrss.publishers.DISCOVERY_FUNCTIONS",
            {"abc": mock_abc_fail, "sbs": mock_sbs_ok, "smh": mock_smh_ok},
        )

        state_dir = tmp_path / "state"
        result = runner.invoke(app, ["discover", "--state-dir", str(state_dir)])

        assert result.exit_code == 0
        assert set(calls) == {"abc", "sbs", "smh"}

        # SBS and SMH feeds should be in registry despite ABC failure
        registry = FeedRegistry(state_dir)
        publishers = {f.publisher for f in registry.get_feeds()}
        assert "sbs" in publishers
        assert "smh" in publishers

    def test_marks_stale_feeds_after_discovery(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        state_dir = tmp_path / "state"

        # Pre-populate with a feed whose last_seen is >14 days ago
        reg = FeedRegistry(state_dir)
        old_feed = _feed(publisher="abc")
        reg.upsert(old_feed)

        # Manually backdate last_seen
        old_date = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        for url, f in reg._feeds.items():
            reg._feeds[url] = f.model_copy(update={"last_seen": old_date})
        reg.save(list(reg._feeds.values()))

        # Discovery does not re-discover the old feed
        def mock_noop(client, registry):
            return []

        monkeypatch.setattr(
            "australianewsrss.publishers.DISCOVERY_FUNCTIONS",
            {"abc": mock_noop, "sbs": mock_noop, "smh": mock_noop},
        )

        result = runner.invoke(app, ["discover", "--state-dir", str(state_dir)])

        assert result.exit_code == 0

        # Feed should now be stale
        reg2 = FeedRegistry(state_dir)
        feeds = reg2.get_feeds()
        assert len(feeds) == 1
        assert feeds[0].status == "stale"


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


class TestGenerateCommand:
    def test_produces_all_output_files(self, tmp_path: Path, monkeypatch) -> None:
        state_dir = tmp_path / "state"
        output_dir = tmp_path / "output"

        _populate(
            state_dir,
            [
                _feed(
                    publisher="abc",
                    url="https://abc.net.au/feed/1/rss.xml",
                    feed_id="abc-1",
                ),
                _feed(
                    publisher="sbs",
                    url="https://www.sbs.com.au/news/topic/world/feed",
                    feed_id="sbs-1",
                ),
                _feed(
                    publisher="smh",
                    url="https://smh.com.au/rss/feed.xml",
                    feed_id="smh-1",
                ),
            ],
        )

        def mock_fetch(client, feeds):
            results = []
            for f in feeds:
                item = _item(
                    url=f"https://{f.publisher}.example.com/article-1",
                    source_feed_url=f.url,
                )
                results.append(FetchedFeed(feed=f, items=[item], was_cached=False))
            return results

        monkeypatch.setattr("australianewsrss.pipeline.fetch.fetch_feeds", mock_fetch)

        result = runner.invoke(
            app,
            [
                "generate",
                "--state-dir",
                str(state_dir),
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert (output_dir / "feed" / "abc.xml").exists()
        assert (output_dir / "feed" / "sbs.xml").exists()
        assert (output_dir / "feed" / "smh.xml").exists()
        assert (output_dir / "catalogue.json").exists()
        assert (output_dir / "index.html").exists()

    def test_custom_output_dir(self, tmp_path: Path, monkeypatch) -> None:
        state_dir = tmp_path / "state"
        custom_dir = tmp_path / "my_output"

        _populate(state_dir, [_feed(publisher="abc")])

        def mock_fetch(client, feeds):
            return [
                FetchedFeed(
                    feed=feeds[0],
                    items=[_item(source_feed_url=feeds[0].url)],
                    was_cached=False,
                )
            ]

        monkeypatch.setattr("australianewsrss.pipeline.fetch.fetch_feeds", mock_fetch)

        result = runner.invoke(
            app,
            [
                "generate",
                "--state-dir",
                str(state_dir),
                "--output-dir",
                str(custom_dir),
            ],
        )

        assert result.exit_code == 0
        assert (custom_dir / "feed" / "abc.xml").exists()
        assert (custom_dir / "catalogue.json").exists()
        assert (custom_dir / "index.html").exists()

    def test_generate_excludes_and_retires_unsupported_sbs_feeds(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        state_dir = tmp_path / "state"
        output_dir = tmp_path / "output"
        noisy_url = "https://www.sbs.com.au/news/article/feeds/nbv1rs3kw"
        good_url = "https://www.sbs.com.au/news/topic/world/feed"

        _populate(
            state_dir,
            [
                _feed(
                    publisher="sbs",
                    url=noisy_url,
                    title="SBS News - Article Feeds Nbv1Rs3Kw",
                    feed_id="article-feeds-nbv1rs3kw",
                    status="active",
                ),
                _feed(
                    publisher="sbs",
                    url=good_url,
                    title="SBS News - World",
                    feed_id="world",
                    status="active",
                ),
            ],
        )

        seen_urls: list[str] = []

        def mock_fetch(client, feeds):
            seen_urls.extend([f.url for f in feeds])
            return [
                FetchedFeed(
                    feed=f,
                    items=[_item(url=f"https://sbs.example.com/{f.feed_id}")],
                    was_cached=False,
                )
                for f in feeds
            ]

        monkeypatch.setattr("australianewsrss.pipeline.fetch.fetch_feeds", mock_fetch)

        result = runner.invoke(
            app,
            [
                "generate",
                "--state-dir",
                str(state_dir),
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert noisy_url not in seen_urls
        assert good_url in seen_urls

        registry = FeedRegistry(state_dir)
        by_url = {f.url: f for f in registry.get_feeds(publisher="sbs")}
        assert by_url[noisy_url].status == "dead"

    def test_retains_previous_output_when_fetch_empty(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """AC2.8: empty fetch result preserves the last successful generation."""
        state_dir = tmp_path / "state"
        output_dir = tmp_path / "output"

        _populate(state_dir, [_feed(publisher="abc")])

        # Place a pre-existing output file
        feed_dir = output_dir / "feed"
        feed_dir.mkdir(parents=True)
        previous = "<rss>previous good content</rss>"
        (feed_dir / "abc.xml").write_text(previous)

        # fetch_feeds returns empty (all feeds failed or had no items)
        def mock_fetch_empty(client, feeds):
            return []

        monkeypatch.setattr(
            "australianewsrss.pipeline.fetch.fetch_feeds", mock_fetch_empty
        )

        result = runner.invoke(
            app,
            [
                "generate",
                "--state-dir",
                str(state_dir),
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        # Previous output preserved
        assert (feed_dir / "abc.xml").read_text() == previous
