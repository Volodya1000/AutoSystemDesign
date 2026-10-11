"""Diagram rendering settings owned by config.yaml."""

from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

_SERVER_PATTERN: Final[str] = r"^(auto|plantuml|kroki|https?://.+)$"


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

    server: str = Field(default="auto", pattern=_SERVER_PATTERN)
    image_format: Literal["png", "svg"] = Field(default="svg")
    diagram_dir: str = Field(default="output/diagrams", min_length=1)
