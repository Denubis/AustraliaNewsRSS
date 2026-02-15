"""Pattern-based enrichment rules for tag addition."""

from australianewsrss.models import EnrichmentRule

DEFAULT_RULES: list[EnrichmentRule] = [
    EnrichmentRule(
        publisher="smh",
        pattern_type="url",
        pattern="/column-8/",
        add_categories=("smh:Column 8", "smh:Opinion"),
    ),
    EnrichmentRule(
        publisher="abc",
        pattern_type="url",
        pattern="/rural/",
        add_categories=("abc:Rural",),
    ),
    EnrichmentRule(
        publisher="sbs",
        pattern_type="url",
        pattern="/language/",
        add_categories=("sbs:Language",),
    ),
]


def get_enrichment_rules() -> list[EnrichmentRule]:
    """Return a copy of the default enrichment rules."""
    return list(DEFAULT_RULES)
