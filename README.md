# Australian News RSS Aggregator

Programmatically discovers and aggregates RSS feeds from Australian news publishers — ABC, SBS, and The Sydney Morning Herald. Produces a single "everything" RSS 2.0 feed per publisher, optimised for [NewsBlur](https://newsblur.com/) filtering.

## How it works

Three-stage pipeline running as a scheduled GitHub Actions workflow:

1. **Discovery** — crawls publisher websites to find RSS feeds via CMS-specific patterns (CoreMedia collection IDs for ABC, Brightspot feed links for SBS, known paths for SMH)
2. **Fetch + Merge** — retrieves all upstream feeds with polite HTTP (ETag caching, rate limiting, conditional GETs), deduplicates articles by canonical URL, unions category tags
3. **Generate** — produces RSS 2.0 XML per publisher with rich metadata (`media:content`, `enclosure`, `webfeedsFeaturedVisual` images), a JSON catalogue, and an HTML index page

## Feeds

| Publisher | Feed |
|-----------|------|
| ABC News | `feed/abc.xml` |
| SBS News | `feed/sbs.xml` |
| Sydney Morning Herald | `feed/smh.xml` |

Plus `catalogue.json` (machine-readable feed registry) and `index.html` (human-readable overview).

## Development

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                                    # Install dependencies
uv run pytest                              # Run tests
uv run ruff check .                        # Lint
uv run python -m australianewsrss --help   # CLI
```

### CLI commands

- `discover` — probe publisher CMS structures for RSS feed URLs
- `generate` — run full pipeline, write output to `_site/`
- `test-live` — smoke test against real publisher endpoints

## License

MIT
