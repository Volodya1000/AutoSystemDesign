"""Contract tests for the OpenAPI and Swagger UI rendering adapters."""

import json
from pathlib import Path

import pytest

from application.pipeline.outcome import DiagramRenderResult
from domain.models.api import (
    ApiDesign,
    ApiOperation,
    ApiParameter,
    ApiRequestBody,
    ApiResponse,
    DataType,
    HttpMethod,
)
from infrastructure.visualisation.openapi.openapi_renderer import OpenApiRenderer
from infrastructure.visualisation.openapi.renderers import DefaultApiArtifactRenderer
from infrastructure.visualisation.openapi.swagger_ui_renderer import (
    SwaggerUiRenderer,
    safe_json_for_script,
)

pytestmark = pytest.mark.unit


def _api_design() -> ApiDesign:
    return ApiDesign(
        title="Resource API",
        version="2.3.0",
        description="API for managing resources.",
        schemas={
            "Resource": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
            },
            "CreateResourceRequest": {
                "type": "object",
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            },
        },
        operations=[
            ApiOperation(
                operation_id="update_resource",
                method=HttpMethod.PUT,
                path="/v1/resources/{resourceId}",
                summary="Update a resource",
                description="Replaces a resource by its identifier.",
                entrypoint_component_id="public_api",
                handler_component_id="resource_service",
                requirement_ids=["FR-1"],
                sequence_ids=["FR-1_happy_path"],
                parameters=[
                    ApiParameter.model_validate(
                        {
                            "name": "resourceId",
                            "in": "path",
                            "required": True,
                            "data_type": DataType.STRING,
                            "format": "uuid",
                        }
                    ),
                    ApiParameter.model_validate(
                        {
                            "name": "include",
                            "in": "query",
                            "required": False,
                            "data_type": DataType.ARRAY,
                            "item_type": DataType.STRING,
                        }
                    ),
                ],
                request_body=ApiRequestBody(
                    required=True,
                    schema_ref="CreateResourceRequest",
                ),
                responses=[
                    ApiResponse(
                        status_code="200",
                        description="Resource updated.",
                        schema_ref="Resource",
                    ),
                    ApiResponse(
                        status_code="400",
                        description="Invalid request.",
                        content_type=None,
                    ),
                ],
                security_required=True,
            )
        ],
    )


def test_openapi_renderer_maps_operations_parameters_and_components() -> None:
    api = _api_design()

    spec = OpenApiRenderer().render_spec(api)

    operation = spec["paths"]["/v1/resources/{resourceId}"]["put"]
    assert spec["openapi"] == "3.1.0"
    assert spec["info"] == {
        "title": "Resource API",
        "version": "2.3.0",
        "description": "API for managing resources.",
    }
    assert operation["operationId"] == "update_resource"
    assert operation["x-entrypoint-component"] == "public_api"
    assert operation["x-handler-component"] == "resource_service"
    assert operation["x-requirement-ids"] == ["FR-1"]
    assert operation["x-sequence-ids"] == ["FR-1_happy_path"]
    assert operation["security"] == [{"bearerAuth": []}]
    assert operation["parameters"] == [
        {
            "name": "resourceId",
            "in": "path",
            "required": True,
            "schema": {"type": "string", "format": "uuid"},
        },
        {
            "name": "include",
            "in": "query",
            "required": False,
            "schema": {"type": "array", "items": {"type": "string"}},
        },
    ]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/CreateResourceRequest"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Resource"
    }
    assert "content" not in operation["responses"]["400"]
    assert spec["components"]["schemas"] == api.schemas
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"


def test_openapi_renderer_uses_fallback_description_when_absent() -> None:
    api = _api_design().model_copy(update={"description": None})

    spec = OpenApiRenderer().render_spec(api)

    assert spec["info"]["description"] == "Generated by AutoSystemDesign"


def test_safe_json_for_script_escapes_html_sensitive_characters() -> None:
    serialized = safe_json_for_script(
        {"value": "</script><script>alert('x')</script>&"}
    )

    assert r"\u003c/script\u003e" in serialized
    assert r"\u003cscript\u003e" in serialized
    assert r"\u0026" in serialized
    assert "</script>" not in serialized


def test_swagger_renderer_embeds_a_dereferenced_spec_and_escapes_title() -> None:
    api = _api_design()
    spec = OpenApiRenderer().render_spec(api)

    html = SwaggerUiRenderer().render_html(spec, "Resource & Admin <API>")

    assert "<title>Resource &amp; Admin &lt;API&gt; - Swagger UI</title>" in html
    assert "const spec =" in html
    assert "spec: spec," in html
    assert "url: spec" not in html
    assert '"operationId": "update_resource"' in html
    assert '"$ref"' not in html
    assert "Resource API" in html


def test_default_api_artifact_renderer_writes_json_and_html_files(
    tmp_path: Path,
) -> None:
    result = DefaultApiArtifactRenderer().render(
        _api_design(),
        title="Resource API",
        base_name="resource_api",
        out_dir=tmp_path,
    )

    json_path = tmp_path / "resource_api_openapi.json"
    html_path = tmp_path / "resource_api_swagger.html"
    assert result == DiagramRenderResult(
        artifacts=(json_path, html_path),
        warnings=(),
        image_rendered=False,
    )
    spec = json.loads(json_path.read_text(encoding="utf-8"))
    assert spec["openapi"] == "3.1.0"
    html = html_path.read_text(encoding="utf-8")
    assert "<title>Resource API - Swagger UI</title>" in html
    assert "const spec =" in html


def test_default_api_artifact_renderer_returns_warning_for_invalid_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer = DefaultApiArtifactRenderer()

    def fail_to_render_spec(_api: ApiDesign) -> dict:
        raise ValueError("invalid OpenAPI model")

    monkeypatch.setattr(renderer._openapi_renderer, "render_spec", fail_to_render_spec)

    result = renderer.render(
        _api_design(),
        title="Resource API",
        base_name="resource_api",
        out_dir=tmp_path,
    )

    assert result.artifacts == ()
    assert len(result.warnings) == 1
    assert "invalid OpenAPI model" in result.warnings[0]
    assert not (tmp_path / "resource_api_openapi.json").exists()
