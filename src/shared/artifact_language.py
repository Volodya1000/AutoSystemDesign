"""Supported languages for human-readable generated artifact text."""

from enum import StrEnum


class ArtifactLanguage(StrEnum):
    """Keep display language independent of technical identifiers."""

    RUSSIAN = "ru"
    ENGLISH = "en"
