"""Tests for australianewsrss.enrichment_rules default rule definitions."""

from australianewsrss.enrichment_rules import DEFAULT_RULES, get_enrichment_rules
from australianewsrss.models import EnrichmentRule


class TestDefaultRules:
    """Verify DEFAULT_RULES structure and content."""

    def test_default_rules_is_a_list(self) -> None:
        assert isinstance(DEFAULT_RULES, list)

    def test_default_rules_not_empty(self) -> None:
        assert len(DEFAULT_RULES) > 0

    def test_all_entries_are_enrichment_rules(self) -> None:
        for rule in DEFAULT_RULES:
            assert isinstance(rule, EnrichmentRule)

    def test_all_rules_have_non_empty_pattern(self) -> None:
        for rule in DEFAULT_RULES:
            assert rule.pattern, f"Rule for {rule.publisher} has empty pattern"

    def test_all_rules_have_non_empty_add_categories(self) -> None:
        for rule in DEFAULT_RULES:
            assert len(rule.add_categories) > 0, (
                f"Rule for {rule.publisher} has empty add_categories"
            )

    def test_add_categories_are_tuples(self) -> None:
        for rule in DEFAULT_RULES:
            assert isinstance(rule.add_categories, tuple)

    def test_contains_smh_column_8_rule(self) -> None:
        column_8_rules = [r for r in DEFAULT_RULES if "/column-8/" in r.pattern]
        assert len(column_8_rules) == 1
        rule = column_8_rules[0]
        assert rule.publisher == "smh"
        assert rule.pattern_type == "url"
        assert "smh:Column 8" in rule.add_categories

    def test_contains_abc_rural_rule(self) -> None:
        rural_rules = [r for r in DEFAULT_RULES if "/rural/" in r.pattern]
        assert len(rural_rules) == 1
        rule = rural_rules[0]
        assert rule.publisher == "abc"
        assert rule.pattern_type == "url"
        assert "abc:Rural" in rule.add_categories

    def test_contains_sbs_language_rule(self) -> None:
        language_rules = [r for r in DEFAULT_RULES if "/language/" in r.pattern]
        assert len(language_rules) == 1
        rule = language_rules[0]
        assert rule.publisher == "sbs"
        assert rule.pattern_type == "url"
        assert "sbs:Language" in rule.add_categories


class TestGetEnrichmentRules:
    """Verify get_enrichment_rules() returns an independent copy."""

    def test_returns_list_of_enrichment_rules(self) -> None:
        rules = get_enrichment_rules()
        assert isinstance(rules, list)
        for rule in rules:
            assert isinstance(rule, EnrichmentRule)

    def test_returns_same_content_as_default(self) -> None:
        rules = get_enrichment_rules()
        assert rules == DEFAULT_RULES

    def test_returns_independent_copy(self) -> None:
        rules_a = get_enrichment_rules()
        rules_b = get_enrichment_rules()
        assert rules_a is not rules_b
        # Mutating one should not affect the other
        rules_a.clear()
        assert len(rules_b) == len(DEFAULT_RULES)

    def test_modifying_result_does_not_affect_defaults(self) -> None:
        rules = get_enrichment_rules()
        original_len = len(DEFAULT_RULES)
        rules.append(
            EnrichmentRule(
                publisher="test",
                pattern_type="url",
                pattern="/test/",
                add_categories=("test:Test",),
            )
        )
        assert len(DEFAULT_RULES) == original_len
