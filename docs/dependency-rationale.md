# Dependency Rationale

Falsifiable justifications for every direct dependency. Each entry records why the package was added, what evidence supports its use, and who it serves.

Maintained by design plans (when adding deps) and controlled-dependency-upgrade (when auditing). Reviewed by restate-our-assumptions (periodic philosophical audit).

## httpx
**Added:** 2026-02-14
**Design plan:** docs/design-plans/2026-02-14-au-news-rss.md
**Claim:** HTTP client with native ETag/conditional GET support, async capability, and timeout handling for polite crawling of publisher websites
**Evidence:** `australianewsrss/http_client.py` — all outbound HTTP requests to publisher feeds and section pages
**Serves:** Runtime users

## lxml
**Added:** 2026-02-14
**Design plan:** docs/design-plans/2026-02-14-au-news-rss.md
**Claim:** Fast XML/HTML parser for extracting CoreMedia collection IDs from ABC HTML and for RSS XML generation
**Evidence:** `australianewsrss/discovery/abc.py` (HTML parsing), `australianewsrss/pipeline/generate.py` (XML generation)
**Serves:** Runtime users

## feedparser
**Added:** 2026-02-14
**Design plan:** docs/design-plans/2026-02-14-au-news-rss.md
**Claim:** Battle-tested RSS/Atom parser that handles edge cases in malformed feeds from ABC, SBS, and SMH
**Evidence:** `australianewsrss/pipeline/fetch.py` (feed parsing), tests (round-trip validation of generated feeds)
**Serves:** Runtime users, developers (testing)

## pydantic
**Added:** 2026-02-14
**Design plan:** docs/design-plans/2026-02-14-au-news-rss.md
**Claim:** Typed data models for pipeline stages (DiscoveredFeed, NormalisedArticle, PublisherConfig) ensuring data integrity between components
**Evidence:** `australianewsrss/models.py`
**Serves:** Runtime users, developers (type safety)

## typer
**Added:** 2026-02-14
**Design plan:** docs/design-plans/2026-02-14-au-news-rss.md
**Claim:** CLI framework for `discover`, `generate`, and `test-live` subcommands
**Evidence:** `australianewsrss/cli.py`
**Serves:** Runtime users, CI (GitHub Actions invokes CLI)

## jinja2
**Added:** 2026-02-14
**Design plan:** docs/design-plans/2026-02-14-au-news-rss.md
**Claim:** Template engine for generating the human-readable catalogue index.html page
**Evidence:** `australianewsrss/pipeline/generate.py`, Jinja2 template for index.html
**Serves:** Runtime users
