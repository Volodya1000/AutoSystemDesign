"""Deterministic identifier and display-name transformations."""

import re


def slug_identifier(source_name: str) -> str:
    """Build a deterministic YAML-safe identifier from the source filename."""
    stem = source_name.rsplit(".", maxsplit=1)[0]
    identifier = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_-")[:64]
    if not identifier:
        return "document"
    if not identifier[0].isalnum() or not identifier[0].isascii():
        return f"doc_{identifier}"[:64]
    return identifier


def functional_name(text: str) -> str:
    """Derive a readable functional-requirement name without another LLM call."""
    first_sentence = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    return first_sentence[:80].rstrip()
