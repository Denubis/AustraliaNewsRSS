"""Tests for australianewsrss.publishers registry."""

import pytest
from pydantic import ValidationError

from australianewsrss.models import PublisherConfig
from australianewsrss.publishers import (
    DISCOVERY_FUNCTIONS,
    PUBLISHERS,
    get_all_publishers,
    get_discovery_function,
    get_publisher,
)


class TestGetPublisher:
    """Tests for get_publisher lookup."""

    def test_get_publisher_abc(self) -> None:
        config = get_publisher("abc")
        assert isinstance(config, PublisherConfig)
        assert config.name == "ABC News"
        assert config.base_url == "https://www.abc.net.au"
        assert len(config.seed_urls) > 0

    def test_get_publisher_sbs(self) -> None:
        config = get_publisher("sbs")
        assert isinstance(config, PublisherConfig)
        assert config.name == "SBS News"
        assert config.base_url == "https://www.sbs.com.au"
        assert len(config.seed_urls) > 0

    def test_get_publisher_smh(self) -> None:
        config = get_publisher("smh")
        assert isinstance(config, PublisherConfig)
        assert config.name == "Sydney Morning Herald"
        assert config.base_url == "https://www.smh.com.au"
        assert len(config.seed_urls) > 0

    def test_get_publisher_nonexistent_raises_keyerror(self) -> None:
        with pytest.raises(KeyError):
            get_publisher("bbc")


class TestGetAllPublishers:
    """Tests for get_all_publishers."""

    def test_get_all_publishers_returns_three(self) -> None:
        publishers = get_all_publishers()
        assert len(publishers) == 3

    def test_each_publisher_has_nonempty_seed_urls(self) -> None:
        for config in get_all_publishers():
            assert len(config.seed_urls) > 0, f"{config.slug} has empty seed_urls"


class TestGetDiscoveryFunction:
    """Tests for get_discovery_function lookup."""

    def test_get_discovery_function_abc(self) -> None:
        func = get_discovery_function("abc")
        assert callable(func)

    def test_get_discovery_function_sbs(self) -> None:
        func = get_discovery_function("sbs")
        assert callable(func)

    def test_get_discovery_function_smh(self) -> None:
        func = get_discovery_function("smh")
        assert callable(func)

    def test_get_discovery_function_nonexistent_raises_keyerror(
        self,
    ) -> None:
        with pytest.raises(KeyError):
            get_discovery_function("bbc")


class TestRegistryConsistency:
    """Tests for consistency between PUBLISHERS and DISCOVERY_FUNCTIONS."""

    def test_discovery_functions_match_publishers(self) -> None:
        assert set(PUBLISHERS.keys()) == set(DISCOVERY_FUNCTIONS.keys())

    def test_publisher_configs_are_frozen(self) -> None:
        config = get_publisher("abc")
        with pytest.raises(ValidationError):
            config.slug = "mutated"
