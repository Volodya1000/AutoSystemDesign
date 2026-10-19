"""PlantUML-safe alias assignment for graph node identifiers."""

import re
from typing import Final

_INVALID_ALIAS_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_]")


def _sanitize_alias(identifier: str) -> str:
    """Turn a node identifier into a PlantUML-safe alias."""
    cleaned: str = _INVALID_ALIAS_CHARACTERS.sub("_", identifier)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"n{cleaned}"
    return cleaned


class AliasRegistry:
    """Assigns unique PlantUML-safe aliases to node identifiers.

    Distinct identifiers can sanitise to the same alias ("order-api" and
    "order_api"); the registry disambiguates them with numeric suffixes.
    """

    def __init__(self, reserved: set[str] | None = None) -> None:
        self._by_identifier: dict[str, str] = {}
        self._used_aliases: set[str] = set() if reserved is None else set(reserved)

    def register(self, identifier: str) -> str:
        """Return the alias of an identifier, registering it once."""
        existing: str | None = self._by_identifier.get(identifier)
        if existing is not None:
            return existing
        base: str = _sanitize_alias(identifier)
        alias: str = base
        suffix: int = 2
        while alias in self._used_aliases:
            alias = f"{base}_{suffix}"
            suffix += 1
        self._used_aliases.add(alias)
        self._by_identifier[identifier] = alias
        return alias

    def find(self, identifier: str) -> str | None:
        """Return the alias of a registered identifier, or None."""
        return self._by_identifier.get(identifier)
