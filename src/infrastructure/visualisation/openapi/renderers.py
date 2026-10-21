"""Infrastructure implementation of ApiArtifactRenderer port."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from application.pipeline.outcome import DiagramRenderResult
from infrastructure.visualisation.openapi.openapi_renderer import OpenApiRenderer
from infrastructure.visualisation.openapi.swagger_ui_renderer import SwaggerUiRenderer

if TYPE_CHECKING:
    from pathlib import Path

    from domain.models.api import ApiDesign


class DefaultApiArtifactRenderer:
    def __init__(
        self,
        *,
        openapi_renderer: OpenApiRenderer | None = None,
        swagger_renderer: SwaggerUiRenderer | None = None,
    ) -> None:
        self._openapi_renderer = (
            openapi_renderer if openapi_renderer is not None else OpenApiRenderer()
        )
        self._swagger_renderer = (
            swagger_renderer if swagger_renderer is not None else SwaggerUiRenderer()
        )

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
            spec_dict: dict[str, object] = self._openapi_renderer.render_spec(subject)
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
