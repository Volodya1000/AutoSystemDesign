"""Diagram rendering settings owned by config.yaml."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.diagram_server import normalize_diagram_server


class VisualisationSettings(BaseModel):
    """PlantUML diagram backend selection and output settings.

    `server` accepts:
    - "auto"     - public PlantUML server with the public Kroki gateway
                   as an automatic fallback (default);
    - "plantuml" - the public PlantUML server only;
    - "kroki"    - the public Kroki gateway only;
    - an http(s) URL of a self-hosted plantuml-server instance, for
      example the docker compose deployment in deploy/plantuml.

    The value is not a secret, so it may also be overridden through the
    environment (ASD_VISUALISATION__SERVER) like any other group.
    """

    model_config = ConfigDict(extra="forbid")

    server: str = "auto"
    image_format: Literal["png", "svg"] = Field(default="svg")
    diagram_dir: str = Field(default="output/diagrams", min_length=1)

    @field_validator("server")
    @classmethod
    def validate_server(cls, value: str) -> str:
        """Use the same typed selection model as renderer and CLI adapters."""
        return str(normalize_diagram_server(value))
