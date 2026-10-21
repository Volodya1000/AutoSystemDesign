# Copyright (c) 2026 Volodya1000
"""Markdown document reader."""

from pathlib import Path
from typing import override

from application.document_reader import DocumentInputError, DocumentReader


class MarkdownReader(DocumentReader):
    """Read UTF-8 Markdown without modifying its semantic content."""

    @override
    def read_text(self, path: Path) -> str:
        if path.suffix.lower() not in {".md", ".markdown"}:
            raise DocumentInputError(f"Unsupported Markdown extension: {path.suffix}")
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Markdown file is not valid UTF-8: {path}") from exc
        if not text.strip():
            raise ValueError(f"Document is empty: {path}")
        return text
