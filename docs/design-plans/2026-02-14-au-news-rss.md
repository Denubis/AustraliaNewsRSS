# Australian News RSS Aggregator Design

**GitHub Issue:** None

## Summary

This tool programmatically discovers and aggregates RSS feeds from Australian news publishers (ABC, SBS, and The Sydney Morning Herald) by probing their underlying content management systems rather than relying on hardcoded feed lists. It produces a single "everything" feed per publisher that merges all discovered category feeds, eliminates duplicate articles that appear across multiple feeds, and enriches each item with comprehensive category tags optimised for NewsBlur filtering.

The approach uses a three-stage pipeline: **Discovery** crawls publisher websites to extract CMS-specific feed references (CoreMedia collection IDs for ABC, Brightspot feed links for SBS, known patterns for SMH), **Fetch + Merge** retrieves all upstream feeds with polite HTTP practices (ETag caching, rate limiting, conditional GETs), deduplicates articles by canonical URL, and unions their category tags, and **Generate** produces maximally-valid RSS 2.0 XML with rich metadata (`media:content`, `enclosure`, featured images), a machine-readable JSON catalogue tracking feed lifecycle, and an HTML index page. The system runs as a scheduled GitHub Actions workflow, deploying static files to GitHub Pages. Feed registry state is maintained in a JSON file committed to git, tracking discovered feeds and their health status. HTTP cache (ETag data) lives in an ephemeral SQLite database that is not committed, rebuilding on cache miss.

## Definition of Done

1. A Python tool that programmatically discovers RSS feeds from ABC (CoreMedia), SBS (Brightspot), and SMH (Nine custom CMS) by probing their CMS structures -- not by maintaining a hardcoded list.
2. A normalised "everything" RSS 2.0 feed per publisher (ABC, SBS, SMH) that merges all discovered category feeds, deduplicates by article URL, and applies rich `<category>` tags for NewsBlur filtering.
3. A machine-readable catalogue (JSON) of all discovered feeds with metadata (publisher, category, feed URL, health status, last seen).
4. GitHub Actions workflow that runs discovery + generation on a schedule, deploying static RSS XML + catalogue JSON to GitHub Pages.

**Key qualities:**
- Polite crawling: ETag caching, conditional GETs, rate limiting, proper User-Agent (following the philosophyofwork pattern with SQLite HTTP cache).
- JSON feed registry for incremental discovery across runs (committed to git, text-diffable).
- "Maximally valid" RSS 2.0: proper `<guid>`, `<pubDate>`, `<category>` tags, `webfeedsFeaturedVisual` images, `media:content` -- optimised for NewsBlur.
- Feed catalogue tracks lifecycle: new feeds appearing, old feeds dying, dynamic collections coming and going.
- Tag enrichment via configurable rules: pattern-based category addition (e.g., detecting Column 8 content in SMH by URL pattern).
- Proper credit and attribution preserved from upstream feeds.

**Out of scope (for now):**
- Other publishers beyond ABC, SBS, and SMH (Guardian, News Corp -- future additions).
- AI-powered scraping of publishers with no feeds (the rss-anything approach).
- Web UI beyond what GitHub Pages provides natively.

## Acceptance Criteria

### au-news-rss.AC1: Programmatic feed discovery from CMS structures

- **au-news-rss.AC1.1 Success:** ABC discovery extracts CoreMedia collection IDs from section page HTML and converts them to valid feed URLs
- **au-news-rss.AC1.2 Success:** ABC discovery detects both `coremedia://collection/{ID}` and `coremedia://dynamiccollection/{ID}` references
- **au-news-rss.AC1.3 Success:** SBS discovery finds feed URLs from the SBS feeds page and section page `<link rel="alternate">` tags
- **au-news-rss.AC1.4 Success:** SMH discovery returns known feed paths and detects new sections from navigation
- **au-news-rss.AC1.5 Failure:** Invalid or dead feed URLs (404, 500) are recorded with `dead` status, not silently dropped
- **au-news-rss.AC1.6 Edge:** ABC dynamic collections that disappear are tracked with `last_seen` timestamp and eventually marked `stale`

### au-news-rss.AC2: Normalised "everything" feed per publisher

- **au-news-rss.AC2.1 Success:** Generated feed contains articles from all discovered upstream feeds for the publisher
- **au-news-rss.AC2.2 Success:** Duplicate articles (same URL across multiple upstream feeds) appear exactly once in output
- **au-news-rss.AC2.3 Success:** Deduplicated articles retain the union of all category tags from all copies
- **au-news-rss.AC2.4 Success:** Source feed name added as `<category>` tag with publisher prefix (e.g., `abc:Politics`)
- **au-news-rss.AC2.5 Success:** Upstream `<category>` tags preserved verbatim alongside enriched tags
- **au-news-rss.AC2.6 Success:** Pattern-based rules add categories (e.g., SMH Column 8 detected by URL pattern)
- **au-news-rss.AC2.7 Success:** `<dc:creator>`, `<copyright>`, and `<description>` content preserved from upstream
- **au-news-rss.AC2.8 Failure:** Empty upstream feed does not produce empty output -- last successful generation kept

### au-news-rss.AC3: Valid RSS 2.0 optimised for NewsBlur

- **au-news-rss.AC3.1 Success:** Generated XML parses without errors via `feedparser` round-trip
- **au-news-rss.AC3.2 Success:** Every item has `<guid>`, `<pubDate>`, `<link>`, `<title>`, and `<description>`
- **au-news-rss.AC3.3 Success:** Images emitted as `<media:content>`, `<enclosure>`, and `<img class="webfeedsFeaturedVisual">` in description CDATA
- **au-news-rss.AC3.4 Success:** `<atom:link rel="self">` points to the feed's own URL on GitHub Pages
- **au-news-rss.AC3.5 Success:** Feed includes `<channel>` level `<generator>`, `<copyright>` with upstream attribution, and `<language>en-AU</language>`

### au-news-rss.AC4: Machine-readable catalogue

- **au-news-rss.AC4.1 Success:** `catalogue.json` lists all discovered feeds with publisher, title, URL, status, first_seen, last_seen, last_checked
- **au-news-rss.AC4.2 Success:** `index.html` renders a human-readable view of the catalogue with per-publisher feed listings
- **au-news-rss.AC4.3 Success:** Catalogue reflects feed lifecycle: new feeds appear, dead feeds marked, stale feeds flagged

### au-news-rss.AC5: Polite crawling

- **au-news-rss.AC5.1 Success:** HTTP client sends conditional GET with `If-None-Match` when ETag is cached, receiving 304 for unchanged content
- **au-news-rss.AC5.2 Success:** Minimum 300ms delay between requests to same domain
- **au-news-rss.AC5.3 Success:** User-Agent identifies the tool with contact URL
- **au-news-rss.AC5.4 Success:** `Retry-After` header respected when present

### au-news-rss.AC6: GitHub Actions deployment

- **au-news-rss.AC6.1 Success:** Discovery workflow runs on schedule and commits feed registry changes when feeds change
- **au-news-rss.AC6.2 Success:** Generation workflow runs on schedule and deploys static files to GitHub Pages
- **au-news-rss.AC6.3 Failure:** Single publisher discovery failure does not block other publishers or generation

## Glossary

- **CoreMedia**: ABC's content management system; exposes content via collection IDs that can be converted to RSS feed URLs
- **Brightspot**: SBS's content management system; publishes feeds discoverable via `<link rel="alternate">` tags
- **Nine custom CMS**: The Sydney Morning Herald's proprietary content management system; has static feed paths without programmatic discovery
- **ETag**: HTTP header used for cache validation; allows clients to make conditional requests that return 304 Not Modified when content hasn't changed
- **Conditional GET**: HTTP request pattern using `If-None-Match` header with a cached ETag to avoid re-downloading unchanged resources
- **NewsBlur**: Feed reader service that this tool optimises for via specific image and category tag conventions
- **`<category>` tag**: RSS 2.0 element for categorising feed items; used here for multi-dimensional filtering (source feed, publisher, topic)
- **`media:content`**: Yahoo Media RSS extension for attaching images and multimedia to feed items
- **`webfeedsFeaturedVisual`**: Class name convention for designating hero images in feed item HTML; recognised by NewsBlur
- **Canonical URL**: Normalised version of an article URL with query parameters stripped to enable accurate duplicate detection
- **Tag enrichment**: Process of adding category tags to feed items from three sources: source feed name, upstream passthrough, and pattern-based rules
- **Polite crawling**: HTTP client practices that respect server resources: rate limiting, caching, conditional requests, transparent user-agent
- **Pydantic**: Python library for data validation using type annotations
- **Typer**: Python library for building command-line interfaces with type hints
- **Dynamic collection**: ABC-specific term for time-limited collections that appear and disappear (e.g., election coverage, breaking news events)
- **Column 8**: SMH daily miscellany column that needs explicit tagging for RSS filtering; detected by URL pattern

## Architecture

Three-stage feed-merge pipeline: **Discover** upstream feeds, **Fetch + Merge** them into a single stream per publisher, **Generate** normalised RSS 2.0 output. Deployed as a scheduled Python script via GitHub Actions, serving static files on GitHub Pages.

### Components

```
australianewsrss/
  __init__.py
  cli.py              # typer CLI entry point
  models.py           # Pydantic models: DiscoveredFeed, NormalisedArticle, PublisherConfig
  http_client.py      # Polite HTTP client with ETag cache (SQLite-backed)
  state.py             # Feed registry (JSON) and HTTP cache (SQLite) management

  discovery/
    __init__.py
    abc.py             # ABC CoreMedia collection ID scraper
    sbs.py             # SBS Brightspot feed discovery
    smh.py             # SMH static feed registry + section discovery

  pipeline/
    __init__.py
    fetch.py           # Fetch all feeds for a publisher, respecting ETags
    merge.py           # Merge items across feeds, dedup by canonical URL
    enrich.py          # Tag enrichment: source-feed tags, upstream passthrough, pattern rules
    generate.py        # RSS 2.0 XML generation + catalogue JSON/HTML

  publishers.py       # Publisher registry: maps slug -> discovery + enrichment config
```

### Data Flow

1. **Discovery** (daily): Crawl publisher section pages -> extract CMS-specific feed references -> probe each as RSS -> record in `state/feeds.json`.
2. **Fetch** (hourly): For each registered feed, conditional GET with ETag/If-None-Match. Skip feeds that haven't changed (304).
3. **Merge**: Combine items from all feeds for a publisher. Dedup by canonical article URL (strip query params). Union category tags across copies.
4. **Enrich**: Apply three tag layers -- source feed name as `<category>`, upstream tags passthrough, pattern-based rules from YAML config.
5. **Generate**: Produce RSS 2.0 XML per publisher + `catalogue.json` + `index.html`. Deploy to GitHub Pages.

### Key Contracts

`discovery/*.py` each expose: `discover_feeds(client: HttpClient, registry: FeedRegistry) -> list[DiscoveredFeed]`

`pipeline/fetch.py` exposes: `fetch_feeds(client: HttpClient, feeds: list[DiscoveredFeed]) -> list[FetchedFeed]`

`pipeline/merge.py` exposes: `merge_and_dedup(fetched: list[FetchedFeed]) -> list[NormalisedArticle]`

`pipeline/enrich.py` exposes: `enrich(articles: list[NormalisedArticle], rules: list[EnrichmentRule]) -> list[NormalisedArticle]`

`pipeline/generate.py` exposes: `generate_rss(articles: list[NormalisedArticle], publisher: PublisherConfig) -> str` and `generate_catalogue(registry: FeedRegistry) -> str`

Each stage is a pure function (except HTTP I/O in fetch/discovery). Testable independently.

### Publisher-Specific Discovery

**ABC (CoreMedia CMS):** Crawl ~15-20 seed section URLs. Regex-extract `coremedia://collection/{ID}` and `coremedia://dynamiccollection/{ID}` from HTML. Probe `abc.net.au/news/feed/{ID}/rss.xml` with HEAD requests. Record feed title and status. Dynamic collections tracked with `first_seen`/`last_seen` for lifecycle monitoring.

**SBS (Brightspot CMS):** Start from `sbs.com.au/news/feeds` page. Crawl section pages for `<link rel="alternate" type="application/rss+xml">`. Probe `sbs.com.au/news/topic/{slug}/feed` patterns.

**SMH (Nine custom CMS):** Known static feed paths (`/rss/feed.xml`, `/rss/business.xml`, etc.) plus navigation crawl for new sections. Primary value is enrichment, not discovery.

### Tag Enrichment

Three layers applied in sequence:

1. **Source feed tags**: Every item tagged with its source feed name, prefixed by publisher (`abc:Politics`, `sbs:World`, `smh:Sport`). Most reliable signal -- ABC's own `<category>` tags are inconsistent.
2. **Upstream passthrough**: All existing `<category>` tags from the original feed preserved verbatim.
3. **Pattern-based rules** (YAML config): URL/title/author pattern matching adds categories. Example: SMH URL containing `/column-8/` adds `smh:Column 8` and `smh:Opinion`.

### Image Normalisation

Output feeds emit three image representations for maximum reader compatibility:
- `<media:content url="..." medium="image"/>` (Feedly, FreshRSS)
- `<enclosure url="..." type="image/jpeg" length="0"/>` (legacy readers)
- `<img class="webfeedsFeaturedVisual">` in `<description>` CDATA (NewsBlur hero images)

Source: pick `isDefault="true"` from ABC `media:group`, or single `media:content`/`enclosure` from SBS/SMH.

### Polite HTTP Client

Follows the pattern from [philosophyofwork](https://github.com/MQFacultyOfArts/philosophyofwork):
- SQLite-backed ETag cache with conditional GET (`If-None-Match`)
- Minimum 300ms delay between requests to same domain (configurable per publisher)
- Respects `Retry-After` headers
- Transparent User-Agent: `AustraliaNewsRSS/0.1 (https://github.com/{user}/AustraliaNewsRSS; feed aggregation)`

### State Management

**Feed registry** (`state/feeds.json`): JSON file committed to repo. Human-readable, text-diffable, mergeable. Contains all discovered feeds with publisher, url, title, category_hint, feed_id, status, first_seen, last_seen, last_checked. Small (~50-100 feed records).

**HTTP cache** (`state/http_cache.db`): SQLite database for ETag/conditional GET caching. Ephemeral — `.gitignore`d, rebuilt on cache miss. Not committed to repo.

Does NOT store articles. Articles are ephemeral — fetched, merged, output as XML, discarded.

### Output Structure (GitHub Pages)

```
/
  index.html              # Human-readable catalogue page
  catalogue.json          # Machine-readable catalogue
  feed/abc.xml            # ABC "everything" feed
  feed/sbs.xml            # SBS "everything" feed
  feed/smh.xml            # SMH "everything" feed
```

### Error Handling

- Publisher discovery failure: log, skip, don't block other publishers.
- Individual feed fetch failure: use cached version, mark as `degraded` in catalogue.
- All feeds for a publisher fail: don't generate empty feed -- keep serving last successful generation.

## Existing Patterns

This is a greenfield project with no existing codebase patterns. Design introduces:

- **Polite HTTP client pattern** adapted from [philosophyofwork](https://github.com/MQFacultyOfArts/philosophyofwork) `paperpile_client.py`: SQLite ETag cache, rate limiting, conditional GETs, transparent User-Agent.
- **Feed-merge pipeline** as pure functions between typed Pydantic models. Influenced by `rss-anything`'s RSS generation approach but fundamentally different in purpose (normalising existing feeds vs creating feeds from scraping).
- **YAML-configured enrichment rules** for publisher-specific tag patterns.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Project Scaffolding
**Goal:** Working Python project with dependencies, linting, and CLI skeleton.

**Components:**
- `pyproject.toml` with dependencies (httpx, lxml, feedparser, pydantic, typer, jinja2, pytest)
- `australianewsrss/__init__.py`, `cli.py` (typer app with `discover` and `generate` subcommands -- stubs)
- Ruff and ty configuration
- `.github/workflows/` directory (empty, populated in Phase 6)

**Dependencies:** None (first phase)

**Done when:** `uv sync` succeeds, `uv run ruff check .` clean, `uv run python -m australianewsrss --help` shows CLI
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Data Models & Database
**Goal:** Pydantic models for all pipeline data and SQLite state management.

**Components:**
- `australianewsrss/models.py` -- DiscoveredFeed, NormalisedArticle, FetchedFeed, PublisherConfig, EnrichmentRule models
- `australianewsrss/state.py` -- FeedRegistry (JSON file CRUD), HttpCache (SQLite ETag cache)
- `australianewsrss/http_client.py` -- Polite HTTP client with ETag cache, rate limiting, conditional GETs

**Dependencies:** Phase 1

**Done when:** Models validate correctly, feed registry persists to JSON and round-trips, HTTP client respects ETags and rate limits. Tests cover model validation, registry round-trips, and HTTP cache behaviour (mocked).
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: ABC Discovery
**Goal:** Programmatic discovery of ABC RSS feeds from CoreMedia collection IDs.

**Components:**
- `australianewsrss/discovery/abc.py` -- Crawl ABC section pages, extract `coremedia://collection/{ID}` and `coremedia://dynamiccollection/{ID}` via regex, probe as feed URLs, record results
- Seed URL list for ABC sections (configurable)

**Dependencies:** Phase 2 (HTTP client, DB, models)

**Done when:** Discovery finds known ABC feeds from saved HTML fixtures. Tests use mocked HTTP with real HTML snapshots. Dynamic collection lifecycle (appear/disappear) tested.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: SBS and SMH Discovery
**Goal:** Feed discovery for SBS (Brightspot) and SMH (Nine CMS).

**Components:**
- `australianewsrss/discovery/sbs.py` -- Crawl SBS feeds page and section pages for RSS links
- `australianewsrss/discovery/smh.py` -- Static feed registry with navigation crawl for new sections
- `australianewsrss/publishers.py` -- Publisher registry mapping slug to discovery module and config

**Dependencies:** Phase 2 (HTTP client, DB, models)

**Done when:** SBS discovery finds known feeds from fixtures. SMH registry returns known feed URLs. Publisher registry resolves all three publishers. Tests with mocked HTTP.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Feed Pipeline (Fetch, Merge, Enrich)
**Goal:** Core pipeline: fetch upstream feeds, merge/dedup articles, apply tag enrichment.

**Components:**
- `australianewsrss/pipeline/fetch.py` -- Fetch all feeds for a publisher with conditional GETs, parse RSS XML
- `australianewsrss/pipeline/merge.py` -- Merge items across feeds, dedup by canonical URL (strip query params), union category tags
- `australianewsrss/pipeline/enrich.py` -- Three-layer tag enrichment: source feed name, upstream passthrough, YAML pattern rules
- Enrichment rules YAML config file

**Dependencies:** Phase 2 (models, HTTP client), Phases 3-4 (discovery provides feed list)

**Done when:** Pipeline produces correctly merged, deduped, enriched article lists from feed fixtures. Category tag union works. Column 8 detection works. Tests use real feed XML snapshots as fixtures.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: RSS Generation & Catalogue
**Goal:** Generate normalised RSS 2.0 XML, catalogue JSON, and index HTML.

**Components:**
- `australianewsrss/pipeline/generate.py` -- RSS 2.0 XML with atom:link, media:content, enclosure, webfeedsFeaturedVisual, enriched categories. Catalogue JSON. Index HTML via Jinja2 template.
- Jinja2 template for `index.html`

**Dependencies:** Phase 5 (pipeline produces NormalisedArticle lists)

**Done when:** Generated RSS validates with feedparser (round-trip test). Contains correct `<category>`, `<media:content>`, `<enclosure>`, `webfeedsFeaturedVisual` img tags. Catalogue JSON has correct feed metadata. Index HTML renders. All tests pass.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: CLI Integration
**Goal:** Wire all components together via the typer CLI.

**Components:**
- `australianewsrss/cli.py` -- `discover` command (runs discovery for all or specified publishers), `generate` command (runs full pipeline, writes output files), `test-live` command (smoke test against real endpoints)
- Output directory configuration (default: `_site/`)

**Dependencies:** Phases 3-6 (all pipeline components)

**Done when:** `uv run python -m australianewsrss discover` runs discovery. `uv run python -m australianewsrss generate` produces valid output files. Integration test runs full pipeline end-to-end with mocked HTTP.
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: GitHub Actions & Pages Deployment
**Goal:** Automated scheduled workflows deploying to GitHub Pages.

**Components:**
- `.github/workflows/discover.yml` -- Daily discovery workflow (06:00 AEST), commits feed registry changes
- `.github/workflows/generate.yml` -- Hourly feed generation workflow, deploys to GitHub Pages
- GitHub Pages configuration

**Dependencies:** Phase 7 (CLI entry points)

**Done when:** Workflows run successfully in CI. Discovery commits feed registry changes. Generation deploys static files to Pages. Feed URLs accessible at `https://{user}.github.io/AustraliaNewsRSS/feed/abc.xml`.
<!-- END_PHASE_8 -->

## Additional Considerations

**State split:** Feed registry is a JSON file (`state/feeds.json`) committed to the repo — human-readable, text-diffable, mergeable, with full change history via git. HTTP cache is an ephemeral SQLite database (`state/http_cache.db`) that is `.gitignore`d and rebuilds on cache miss. This avoids binary files in git while keeping discovery state persistent and auditable.

**Feed staleness:** ABC dynamic collections (event feeds like "Australia Votes", "Trump tariffs") appear and disappear. The catalogue tracks `first_seen` and `last_seen` timestamps. Feeds not seen for 14 days are marked `stale`; 30 days marks `dead`. This is informational -- dead feeds are retained in the catalogue for historical record.

**Upstream attribution:** All original `<dc:creator>`, `<copyright>`, and `<description>` content preserved verbatim. The generated feed's `<channel>` description credits the original publisher and links to their site. The `<generator>` tag identifies this tool.

**Discovery health monitoring:** If discovery for a publisher finds fewer feeds than the previous run, log a warning with the delta. This catches silent discovery failures (CMS restructure, changed URL patterns) before they produce a visibly degraded "everything" feed. The threshold is informational — discovery proceeds regardless, but the catalogue tracks the drop for manual review.
