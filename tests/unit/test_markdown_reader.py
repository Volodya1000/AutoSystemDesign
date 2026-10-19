from pathlib import Path

import pytest

from infrastructure.document_readers.markdown_reader import MarkdownReader


@pytest.mark.unit
def test_reads_utf8_markdown(tmp_path: Path) -> None:
    path = tmp_path / "requirements.md"
    path.write_text("# Требования\nСервис должен отвечать за 200 мс.", encoding="utf-8")
    assert "Сервис должен" in MarkdownReader().read_text(path)


@pytest.mark.unit
def test_rejects_other_extensions(tmp_path: Path) -> None:
    path = tmp_path / "requirements.txt"
    path.write_text("text", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported Markdown"):
        MarkdownReader().read_text(path)


@pytest.mark.unit
def test_rejects_empty_document(tmp_path: Path) -> None:
    path = tmp_path / "empty.md"
    path.write_text("  ", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        MarkdownReader().read_text(path)
