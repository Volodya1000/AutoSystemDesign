"""Rendering of known protocol singletons for use in LLM prompts.

The JSON Schema cannot express allowed protocol names on its own:
ConnectionProtocol.name is a plain string in the model, so the valid
values are not part of the schema. The list is derived at import time
from the domain module, so adding a new protocol constant is enough:
this fragment follows.
"""

from typing import Final

from domain.models import protocols as domain_protocols
from domain.models.protocols import ConnectionProtocol

_KNOWN_PROTOCOLS: Final[tuple[ConnectionProtocol, ...]] = tuple(
    sorted(
        (
            value
            for value in vars(domain_protocols).values()
            if isinstance(value, ConnectionProtocol)
        ),
        key=lambda protocol: protocol.name,
    )
)


def render_known_protocols() -> str:
    """Lists the protocol singletons an edge may reference by name."""
    lines: list[str] = ["Allowed protocol values for edge.protocol.name:"]
    lines.extend(
        f"- {protocol.name} (is_asynchronous={str(protocol.is_asynchronous).lower()})"
        for protocol in _KNOWN_PROTOCOLS
    )
    return "\n".join(lines)
