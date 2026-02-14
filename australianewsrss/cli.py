"""CLI entry point for australianewsrss."""

import typer

app = typer.Typer(
    name="australianewsrss",
    help="Discover and aggregate RSS feeds from Australian news publishers.",
)


@app.command()
def discover(
    publisher: str | None = typer.Option(
        None, help="Publisher slug (abc, sbs, smh). Omit for all."
    ),
) -> None:
    """Discover RSS feeds from publisher CMS structures."""
    typer.echo(f"Discovery not yet implemented. Publisher: {publisher or 'all'}")


@app.command()
def generate(
    output_dir: str = typer.Option(
        "_site", help="Output directory for generated files."
    ),
) -> None:
    """Generate normalised RSS feeds and catalogue."""
    typer.echo(f"Generation not yet implemented. Output: {output_dir}")
