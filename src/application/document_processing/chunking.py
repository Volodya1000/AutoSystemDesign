"""Pure text chunking functions."""

from application.document_reader import DocumentInputError


def split_document_text(
    text: str,
    *,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    """Split text into bounded overlapping windows, preferring paragraph breaks."""
    if max_chars < 1:
        message = "max_chars must be positive"
        raise DocumentInputError(message)
    if overlap_chars < 0 or overlap_chars >= max_chars:
        message = "overlap_chars must be in [0, max_chars)"
        raise DocumentInputError(message)
    if not text:
        return []

    chunks: list[str] = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + max_chars, text_length)
        if end < text_length:
            boundary = text.rfind("\n\n", start + max_chars // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = max(start + 1, end - overlap_chars)
    return chunks
