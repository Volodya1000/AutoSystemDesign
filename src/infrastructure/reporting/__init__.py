# Copyright (c) 2026 Volodya1000
"""Reporting port adapters and logging helpers.

The package is split into two modules:

- ``helpers``: pure formatting functions with no port dependency;
- ``adapters``: implementations of ``GenerationReporter`` and
  ``PipelineReporter`` that delegate to the helpers.

The original single-module import path (``infrastructure.reporting``)
is preserved by re-exporting the public surface from this package.
"""

from infrastructure.reporting.adapters import (
    LoggingGenerationReporter,
    LoggingPipelineReporter,
)
from infrastructure.reporting.helpers import (
    log_attempts,
    log_header,
    log_token_totals,
)

__all__ = [
    "LoggingGenerationReporter",
    "LoggingPipelineReporter",
    "log_attempts",
    "log_header",
    "log_token_totals",
]
