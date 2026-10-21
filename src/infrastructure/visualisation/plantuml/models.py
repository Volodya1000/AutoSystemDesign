# Copyright (c) 2026 Volodya1000
"""Data models of the PlantUML diagram pipeline (no I/O here)."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DiagramImageFormat(StrEnum):
    """Image formats the diagram servers can render."""

    PNG = "png"
    SVG = "svg"


class DiagramArtifacts(BaseModel):
    """Diagram output: PlantUML source, remote image URL, image bytes.

    The shape is chosen for UI reuse: `source` enables client-side
    rendering, `image_url` is a ready-to-embed image link, `image_bytes`
    can be displayed or persisted directly, and
    `model_dump(exclude={"image_bytes"})` is a JSON-safe payload for a
    future HTTP API. Instances are immutable; `with_image` returns a
    copy with the rendered image attached.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    image_url: str
    image_format: DiagramImageFormat
    image_bytes: bytes | None = None

    def with_image(self, image_bytes: bytes) -> "DiagramArtifacts":
        """Return a copy of the artifacts with the rendered image attached."""
        return self.model_copy(update={"image_bytes": image_bytes})
