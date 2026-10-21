# Copyright (c) 2026 Volodya1000
"""Self-contained Swagger UI HTML generator from an OpenAPI specification."""

from __future__ import annotations

import html
import json
from typing import Any

from infrastructure.visualisation.openapi.dereference import (
    dereference_internal_refs,
)


def safe_json_for_script(data: dict[str, Any]) -> str:
    """Escapes JSON string to be safely embedded inside HTML script tags."""
    return (
        json.dumps(data, indent=None)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


class SwaggerUiRenderer:
    """Builds a single-file HTML viewer embedding OpenAPI spec with CDN assets.

    The specification is embedded through the ``spec`` option (never
    ``url:``) and fully dereferenced first, so the page performs no request
    for the specification and contains no references left for the runtime
    resolver to fetch. Only the Swagger UI assets themselves (CSS/JS from
    unpkg.com) require an internet connection; if they cannot be loaded,
    the page shows an explanatory message instead of a blank screen.

    The Standalone preset (top bar with the Authorize button and Try-it-out
    controls) is loaded from its own script -- in swagger-ui-dist 5.x it is
    NOT exposed as ``SwaggerUIBundle.SwaggerUIStandalonePreset`` -- and is
    wired up defensively: if that script fails to load, the page falls back
    to the base layout instead of pushing ``undefined`` into the presets
    array.
    """

    def render_html(self, spec_dict: dict[str, Any], title: str) -> str:
        embedded_spec: dict[str, Any] = dereference_internal_refs(spec_dict)
        safe_spec: str = safe_json_for_script(embedded_spec)
        escaped_title: str = html.escape(title)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escaped_title} - Swagger UI</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
  <style>
    body {{ margin: 0; padding: 0; background-color: #fafafa; }}
    #swagger-ui {{ max-width: 1280px; margin: 0 auto; }}
  </style>
  <!--
    The OpenAPI document below is embedded through the `spec` option with
    every internal $ref already inlined. Do not switch this to `url:`:
    pages opened from the file system cannot fetch sibling files, and the
    $ref resolver cannot fetch file:// URIs either.
  -->
</head>
<body>
<div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"
        charset="UTF-8"></script>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-standalone-preset.js"
        charset="UTF-8"></script>
<script>
  window.onload = () => {{
    if (typeof SwaggerUIBundle === "undefined") {{
      document.getElementById("swagger-ui").innerHTML =
        '<div style="font: 16px sans-serif; padding: 24px;">'
        + '<strong>Swagger UI failed to load.</strong> '
        + 'The viewer assets are fetched from unpkg.com and need internet '
        + 'access. The embedded specification itself is complete.';
      return;
    }}
    const spec = {safe_spec};
    const presets = [SwaggerUIBundle.presets.apis];
    const hasStandalone = typeof SwaggerUIStandalonePreset !== "undefined";
    if (hasStandalone) {{
      presets.push(SwaggerUIStandalonePreset);
    }}
    window.ui = SwaggerUIBundle({{
      spec: spec,
      dom_id: '#swagger-ui',
      deepLinking: true,
      presets: presets,
      layout: hasStandalone ? "StandaloneLayout" : "BaseLayout",
    }});
  }};
</script>
</body>
</html>
"""
