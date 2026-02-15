"""CLI entry point for australianewsrss."""

import logging
from pathlib import Path

import typer

from australianewsrss import publishers
from australianewsrss.discovery import sbs as sbs_discovery
from australianewsrss.enrichment_rules import get_enrichment_rules
from australianewsrss.http_client import PoliteHttpClient
from australianewsrss.pipeline import enrich as enrich_mod
from australianewsrss.pipeline import fetch, merge
from australianewsrss.pipeline import generate as generate_mod
from australianewsrss.state import FeedRegistry, HttpCache

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="australianewsrss",
    help="Discover and aggregate RSS feeds from Australian news publishers.",
)


@app.command()
def discover(
    publisher: str | None = typer.Option(
        None, help="Publisher slug (abc, sbs, smh). Omit for all."
    ),
    state_dir: str = typer.Option(
        "state", help="Directory for feed registry and HTTP cache."
    ),
) -> None:
    """Discover RSS feeds from publisher CMS structures."""
    state_path = Path(state_dir)
    registry = FeedRegistry(state_path)
    cache = HttpCache(state_path / "http_cache.db")
    client = PoliteHttpClient(cache)

    try:
        # Determine which publishers to discover
        valid_slugs = list(publishers.PUBLISHERS.keys())

        if publisher is not None:
            if publisher not in valid_slugs:
                typer.echo(
                    f"Unknown publisher: {publisher}. "
                    f"Valid publishers: {', '.join(valid_slugs)}"
                )
                raise typer.Exit(code=1)
            slugs = [publisher]
        else:
            slugs = valid_slugs

        # Run discovery per publisher with error isolation (AC6.3)
        failures: list[str] = []
        for slug in slugs:
            try:
                discover_fn = publishers.get_discovery_function(slug)
                discover_fn(client, registry)
            except Exception:
                logger.exception("Discovery failed for %s", slug)
                typer.echo(f"Error: discovery failed for {slug}")
                failures.append(slug)

        # Mark stale feeds (AC1.6)
        stale = registry.mark_stale_feeds()
        if stale:
            for f in stale:
                typer.echo(f"Marked stale: {f.publisher} — {f.title} ({f.url})")

        # Health summary
        all_feeds = registry.get_feeds()
        status_counts: dict[str, dict[str, int]] = {}
        for f in all_feeds:
            pub_counts = status_counts.setdefault(f.publisher, {})
            pub_counts[f.status] = pub_counts.get(f.status, 0) + 1

        typer.echo(f"Total feeds: {len(all_feeds)}")
        for pub, counts in sorted(status_counts.items()):
            parts = [f"{status}={n}" for status, n in sorted(counts.items())]
            typer.echo(f"  {pub}: {', '.join(parts)}")

        if failures:
            typer.echo(f"Publisher failures: {', '.join(failures)}")
    finally:
        client.close()


@app.command()
def generate(
    output_dir: str = typer.Option(
        "_site", help="Output directory for generated files."
    ),
    base_url: str = typer.Option(
        "https://Denubis.github.io/AustraliaNewsRSS/",
        help="Base URL for self-referencing feed links.",
    ),
    state_dir: str = typer.Option(
        "state", help="Directory for feed registry and HTTP cache."
    ),
) -> None:
    """Generate normalised RSS feeds and catalogue."""
    state_path = Path(state_dir)
    output_path = Path(output_dir)
    feed_output = output_path / "feed"
    feed_output.mkdir(parents=True, exist_ok=True)

    registry = FeedRegistry(state_path)
    cache = HttpCache(state_path / "http_cache.db")
    client = PoliteHttpClient(cache)

    try:
        generated_feeds: dict[str, str] = {}

        for slug in publishers.PUBLISHERS:
            config = publishers.get_publisher(slug)
            all_feeds = registry.get_feeds(publisher=slug)

            # Defense-in-depth: stale registry entries may include noisy
            # non-feed SBS URLs until the next discovery run.
            if slug == "sbs":
                for feed in all_feeds:
                    if feed.status != "active":
                        continue
                    if not sbs_discovery.is_supported_feed_url(feed.url):
                        registry.mark_status(feed.url, "dead")
                        logger.warning(
                            "Marked unsupported SBS feed as dead: %s", feed.url
                        )

            active_feeds = [
                f
                for f in all_feeds
                if f.status == "active"
                and (slug != "sbs" or sbs_discovery.is_supported_feed_url(f.url))
            ]

            if not active_feeds:
                continue

            fetched = fetch.fetch_feeds(client, active_feeds)

            # Persist hydrated feed metadata (title/category hints) so
            # catalogue and future runs use real upstream channel labels.
            for fetched_feed in fetched:
                registry.upsert(fetched_feed.feed)

            # Build source mappings for enrichment
            source_feeds = {ff.feed.url: ff.feed for ff in fetched}
            article_sources: dict[str, str] = {}
            for ff in fetched:
                for item in ff.items:
                    canonical = merge.canonicalise_url(item.url)
                    if canonical not in article_sources:
                        article_sources[canonical] = item.source_feed_url

            articles = merge.merge_and_dedup(fetched)

            # AC2.8: if no articles, retain previous output
            output_file = feed_output / f"{slug}.xml"
            if not articles:
                if output_file.exists():
                    typer.echo(
                        f"Warning: {slug} returned no articles; "
                        "retaining previous output."
                    )
                    generated_feeds[slug] = f"feed/{slug}.xml"
                    continue

            rules = get_enrichment_rules()
            enriched = enrich_mod.enrich(articles, source_feeds, article_sources, rules)

            self_url = f"{base_url.rstrip('/')}/feed/{slug}.xml"
            xml = generate_mod.generate_rss(enriched, config, self_url)

            output_file.write_text(xml)
            generated_feeds[slug] = f"feed/{slug}.xml"
            typer.echo(f"Generated {slug}: {len(enriched)} articles")

        # Catalogue and index
        catalogue_json = generate_mod.generate_catalogue(registry)
        (output_path / "catalogue.json").write_text(catalogue_json)

        index_html = generate_mod.generate_index(registry, generated_feeds)
        (output_path / "index.html").write_text(index_html)

        typer.echo(f"Output: {len(generated_feeds)} feeds, catalogue.json, index.html")
    finally:
        client.close()


@app.command(name="test-live")
def test_live() -> None:
    """Smoke test against real publisher endpoints."""
    import feedparser

    known_feeds: dict[str, str] = {
        "abc": "https://www.abc.net.au/news/feed/2942460/rss.xml",
        "sbs": "https://www.sbs.com.au/news/topic/latest/feed",
        "smh": "https://www.smh.com.au/rss/feed.xml",
    }

    state_path = Path("state")
    cache = HttpCache(state_path / "http_cache.db")
    client = PoliteHttpClient(cache)

    all_ok = True
    try:
        for slug, url in known_feeds.items():
            typer.echo(f"Testing {slug}: {url}")
            try:
                body, was_cached = client.get(url)
                d = feedparser.parse(body)
                typer.echo(f"  Title: {d.feed.get('title', 'N/A')}")
                typer.echo(f"  Items: {len(d.entries)}")
                if d.bozo:
                    typer.echo(f"  Bozo: {d.bozo_exception}")
                    all_ok = False
                else:
                    typer.echo("  OK")
            except Exception as exc:
                typer.echo(f"  FAILED: {exc}")
                all_ok = False
    finally:
        client.close()

    if not all_ok:
        raise typer.Exit(code=1)
