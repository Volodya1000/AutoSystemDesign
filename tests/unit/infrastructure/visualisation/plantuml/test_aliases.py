"""Unit tests for collision-safe PlantUML alias allocation."""

import pytest

from infrastructure.visualisation.plantuml.aliases import AliasRegistry

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("orders-api", "orders_api"),
        ("123worker", "n123worker"),
        ("", "n"),
        ("_private", "n_private"),
    ],
)
def test_register_sanitizes_plantuml_aliases(identifier: str, expected: str) -> None:
    registry = AliasRegistry()

    assert registry.register(identifier) == expected


def test_register_is_idempotent_for_the_same_identifier() -> None:
    registry = AliasRegistry()

    first = registry.register("orders-api")

    assert registry.register("orders-api") == first
    assert registry.find("orders-api") == first


def test_register_disambiguates_distinct_identifiers_with_same_sanitized_alias() -> (
    None
):
    registry = AliasRegistry()

    assert registry.register("orders-api") == "orders_api"
    assert registry.register("orders_api") == "orders_api_2"
    assert registry.register("orders.api") == "orders_api_3"


def test_register_skips_reserved_aliases() -> None:
    registry = AliasRegistry(reserved={"system_boundary", "node"})

    assert registry.register("system-boundary") == "system_boundary_2"
    assert registry.register("node") == "node_2"


def test_find_returns_none_for_unregistered_identifier() -> None:
    registry = AliasRegistry()

    assert registry.find("missing") is None
