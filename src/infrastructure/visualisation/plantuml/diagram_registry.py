"""Kind-keyed registry of diagram source builders.

Builders self-register with the ``@register_diagram_builder`` decorator
in their own modules. The package ``__init__`` imports every builder
module, so registration runs before any caller asks for a builder.

Adding a new diagram type:
1. create ``new_builder.py`` in this package;
2. add ``from infrastructure.visualisation.plantuml import new_builder``
   to ``__init__.py`` (one import line; the decorator does the rest).

Neither ``renderers.py`` nor ``composition.py`` has to change.
"""

from __future__ import annotations

from collections.abc import Callable

from infrastructure.visualisation.plantuml.ports import DiagramSourceBuilder

BuilderFactory = Callable[[], DiagramSourceBuilder]


class DiagramRendererRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, BuilderFactory] = {}

    def register(self, kind: str, factory: BuilderFactory) -> None:
        if kind in self._factories:
            raise ValueError(f"Diagram builder already registered for {kind!r}")
        self._factories[kind] = factory

    def create(self, kind: str) -> DiagramSourceBuilder:
        factory = self._factories.get(kind)
        if factory is None:
            raise KeyError(
                f"Unknown diagram kind {kind!r}; "
                f"registered kinds: {sorted(self._factories)}"
            )
        return factory()

    def registered_kinds(self) -> frozenset[str]:
        return frozenset(self._factories)


_default_registry = DiagramRendererRegistry()


def get_default_registry() -> DiagramRendererRegistry:
    return _default_registry


def register_diagram_builder(
    kind: str,
    *,
    registry: DiagramRendererRegistry | None = None,
) -> Callable[[BuilderFactory], BuilderFactory]:
    """Decorator that registers a builder factory under the given kind."""
    target = registry if registry is not None else _default_registry

    def decorator(factory: BuilderFactory) -> BuilderFactory:
        target.register(kind, factory)
        return factory

    return decorator
