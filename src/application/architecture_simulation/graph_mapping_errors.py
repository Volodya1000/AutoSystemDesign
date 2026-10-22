"""Typed errors for unsupported simulation graph semantics."""

from application.architecture_simulation.mapping_failures import MappingFailure


class GraphMappingError(ValueError):
    """Preserve a typed reason for non-modelled graph semantics."""

    def __init__(self, code: MappingFailure, identifier: str) -> None:
        self.code: MappingFailure = code
        self.identifier: str = identifier
        super().__init__(f"{code.value}: {identifier}")
