"""PlantUML image rendering: the port and the HTTP adapters."""

import urllib.error
import urllib.request
from collections.abc import Sequence
from typing import Final, Protocol

from infrastructure.visualisation.plantuml.encoding import (
    build_kroki_url,
    build_plantuml_url,
)
from infrastructure.visualisation.plantuml.models import DiagramImageFormat

PLANTUML_PUBLIC_SERVER_URL: Final[str] = "https://www.plantuml.com/plantuml"
KROKI_PUBLIC_SERVER_URL: Final[str] = "https://kroki.io"

_USER_AGENT: Final[str] = "Mozilla/5.0 (compatible; AutoSystemDesign/1.0)"
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0


class DiagramRenderingError(Exception):
    """Raised when a diagram server cannot render the diagram source."""


class PlantumlImageRenderer(Protocol):
    """Port: turns PlantUML source into images.

    `build_image_url` is a pure offline computation and is safe to call
    anywhere (frontends can embed the URL directly). `render` performs
    network I/O and raises DiagramRenderingError on failure.
    """

    def build_image_url(self, source: str, image_format: DiagramImageFormat) -> str: ...

    def render(self, source: str, image_format: DiagramImageFormat) -> bytes: ...


def _fetch(url: str, server_label: str, timeout_seconds: float) -> bytes:
    """Downloads the URL content with a client user agent.

    A custom user agent is required: the Cloudflare in front of the
    public PlantUML server answers HTTP 403 to the default
    python-urllib agent.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT}, method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content: bytes = response.read()
    except urllib.error.HTTPError as error:
        raise DiagramRenderingError(
            f"{server_label} rejected the diagram: HTTP {error.code}"
        ) from error
    except OSError as error:
        raise DiagramRenderingError(f"Cannot reach {server_label}: {error}") from error
    return content


class PlantumlServerImageRenderer:
    """Fetches images from a PlantUML HTTP server over GET.

    Works with the public plantuml.com server and with self-hosted
    plantuml-server instances (for example the official Docker image):
    point `server_url` at them. No local Java installation is required.
    """

    def __init__(
        self,
        server_url: str = PLANTUML_PUBLIC_SERVER_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._server_url: str = server_url.rstrip("/")
        self._timeout_seconds: float = timeout_seconds

    def build_image_url(self, source: str, image_format: DiagramImageFormat) -> str:
        """Returns the URL that renders the source in the given format."""
        return build_plantuml_url(self._server_url, source, image_format)

    def render(self, source: str, image_format: DiagramImageFormat) -> bytes:
        """Downloads the rendered image from the PlantUML server."""
        return _fetch(
            self.build_image_url(source, image_format),
            f"PlantUML server {self._server_url}",
            self._timeout_seconds,
        )


class KrokiImageRenderer:
    """Fetches images from a Kroki diagram gateway over GET.

    Kroki (https://kroki.io) renders PlantUML among many other diagram
    types and accepts programmatic clients without bot protection,
    which makes it a reliable fallback for the public PlantUML server.
    """

    def __init__(
        self,
        server_url: str = KROKI_PUBLIC_SERVER_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._server_url: str = server_url.rstrip("/")
        self._timeout_seconds: float = timeout_seconds

    def build_image_url(self, source: str, image_format: DiagramImageFormat) -> str:
        """Returns the URL that renders the source in the given format."""
        return build_kroki_url(self._server_url, source, image_format)

    def render(self, source: str, image_format: DiagramImageFormat) -> bytes:
        """Downloads the rendered image from the Kroki gateway."""
        return _fetch(
            self.build_image_url(source, image_format),
            f"Kroki server {self._server_url}",
            self._timeout_seconds,
        )


class FallbackImageRenderer:
    """Tries several renderers in order; the first success wins.

    `build_image_url` delegates to the primary renderer, so preview URLs
    always point at the preferred server.
    """

    def __init__(self, renderers: Sequence[PlantumlImageRenderer]) -> None:
        if not renderers:
            raise ValueError("At least one renderer is required")
        self._renderers: tuple[PlantumlImageRenderer, ...] = tuple(renderers)

    def build_image_url(self, source: str, image_format: DiagramImageFormat) -> str:
        """Returns the image URL of the primary renderer."""
        return self._renderers[0].build_image_url(source, image_format)

    def render(self, source: str, image_format: DiagramImageFormat) -> bytes:
        """Renders through the first server that responds successfully."""
        failures: list[str] = []
        renderer: PlantumlImageRenderer
        for renderer in self._renderers:
            try:
                return renderer.render(source, image_format)
            except DiagramRenderingError as error:
                failures.append(str(error))
        raise DiagramRenderingError("; ".join(failures))


def build_default_image_renderer(
    plantuml_server_url: str | None = None,
) -> PlantumlImageRenderer:
    """Composes the default image rendering strategy.

    A custom `plantuml_server_url` pins a single PlantUML server (for
    example a local plantuml-server container); by default the public
    PlantUML server is used with the public Kroki gateway as an
    automatic fallback, so one picky server cannot break a run.
    """
    if plantuml_server_url is not None:
        return PlantumlServerImageRenderer(server_url=plantuml_server_url)
    return FallbackImageRenderer(
        renderers=[
            PlantumlServerImageRenderer(),
            KrokiImageRenderer(),
        ]
    )
