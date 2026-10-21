# Copyright (c) 2026 Volodya1000
from __future__ import annotations

import logging

_NOISY_LOGGERS: tuple[str, ...] = ("LiteLLM", "httpcore", "httpx")


def configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if verbose:
        for name in _NOISY_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)
