"""Reject inline suppression comments in tracked project Python modules."""

from __future__ import annotations

import logging
import re
import sys
import tokenize
from pathlib import Path

FORBIDDEN_COMMENT = re.compile(
    r"#\s*(?:noqa\b|ruff:\s*noqa\b|type:\s*ignore\b|"
    r"pylint:\s*(?:disable|skip)\b|nosec\b|"
    r"pragma:\s*no\s*cover\b|pyright:\s*ignore\b)",
    re.IGNORECASE,
)
_SOURCE_DIRECTORIES = (Path("src"), Path("tests"), Path("scripts"))
_logger = logging.getLogger(__name__)


def _suppressions_in_file(path: Path) -> list[str]:
    """Inspect comment tokens without misreading string literals."""
    with path.open("rb") as source:
        return [
            f"{path}:{token.start[0]}: {token.string}"
            for token in tokenize.tokenize(source.readline)
            if token.type == tokenize.COMMENT and FORBIDDEN_COMMENT.search(token.string)
        ]


def main() -> int:
    """Report every inline suppression in source, tests, and scripts."""
    violations = [
        violation
        for directory in _SOURCE_DIRECTORIES
        for path in directory.rglob("*.py")
        for violation in _suppressions_in_file(path)
    ]
    if violations:
        _logger.error("%s", "\n".join(violations))
        return 1
    _logger.info("No inline lint or type suppressions found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
