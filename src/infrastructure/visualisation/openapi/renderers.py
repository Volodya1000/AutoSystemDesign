"""Infrastructure implementation of ApiArtifactRenderer port."""

from __future__ import annotations

import json
from pathlib import Path

from application.pipeline.outcome import DiagramRenderResult
from domain.models.api import ApiDesign
from infrastructure.visualisation.openapi.renderer import (
    OpenApiRenderer,
    SwaggerUiRenderer,
)


class DefaultApiArtifactRenderer:
    def __init__(self) -> None:
        self._openapi_renderer: OpenApiRenderer = OpenApiRenderer()
        self._swagger_renderer: SwaggerUiRenderer = SwaggerUiRenderer()

    def render(
        self,
        subject: ApiDesign,
        *,
        title: str,
        base_name: str,
        out_dir: Path,
    ) -> DiagramRenderResult:
        artifacts: list[Path] = []
        warnings: list[str] = []

        try:
            spec_dict: dict = self._openapi_renderer.render_spec(subject)
            json_path: Path = out_dir / f"{base_name}_openapi.json"
            json_path.write_text(json.dumps(spec_dict, indent=2), encoding="utf-8")
            artifacts.append(json_path)

            html_content: str = self._swagger_renderer.render_html(spec_dict, title)
            html_path: Path = out_dir / f"{base_name}_swagger.html"
            html_path.write_text(html_content, encoding="utf-8")
            artifacts.append(html_path)
        except (OSError, ValueError, TypeError) as error:
            warnings.append(f"Failed to render API artifacts: {error}")

        return DiagramRenderResult(
            artifacts=tuple(artifacts),
            warnings=tuple(warnings),
            image_rendered=False,
        )
