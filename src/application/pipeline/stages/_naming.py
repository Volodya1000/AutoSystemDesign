"""Pure helpers used by the sequence stage for naming and identification.

Extracted from ``sequence.py`` so that artifact-name planning and
functional-requirement extraction can be unit-tested in isolation and
reused by any future stage that needs the same conventions.

No I/O, no logging, no dependency on pipeline context: these functions
are deterministic and side-effect free.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from domain.models import DesignScenario

_SAFE_ID_PATTERN: re.Pattern[str] = re.compile(r"[^A-Za-z0-9_]")


def plan_base_names(
    scenario_id: str,
    requirement_ids: Iterable[str],
) -> Mapping[str, str]:
    """Precomputes unique base names; detects normalization collisions.

    "REQ-1" and "REQ_1" both normalize to "req_1" and would overwrite each
    other's artifacts. Refuse to silently lose data.
    """
    base_names: dict[str, str] = {}
    seen: dict[str, str] = {}
    for req_id in requirement_ids:
        safe_id: str = _SAFE_ID_PATTERN.sub("_", req_id).lower()
        previous: str | None = seen.get(safe_id)
        if previous is not None:
            raise ValueError(
                f"Requirement identifier collision: '{previous}' and "
                f"'{req_id}' both normalize to '{safe_id}'. Rename one of "
                f"them in the scenario so artifacts stay distinct."
            )
        seen[safe_id] = req_id
        base_names[req_id] = f"{scenario_id}_seq_{safe_id}"
    return base_names


def functional_requirement_ids(scenario: DesignScenario) -> list[str]:
    """Best-effort extraction of functional-requirement identifiers.

    Supports both common layouts and returns [] when the model does not
    expose them; a fail-fast check is only possible when they are visible.
    """
    ids: list[str] = []

    functional = getattr(scenario, "functional_requirements", None)
    if functional:
        for req in functional:
            identifier = getattr(req, "identifier", None)
            if identifier:
                ids.append(str(identifier))
        return ids

    for req in getattr(scenario, "requirements", []) or []:
        if getattr(req, "type_identifier", None) == "functional":
            identifier = getattr(req, "identifier", None)
            if identifier:
                ids.append(str(identifier))
    return ids
