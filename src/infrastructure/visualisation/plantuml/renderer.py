"""PlantUML image rendering: the port, the HTTP adapters and the resolver.

Two public server protocols are implemented over plain GET requests:
PlantUML servers (the public plantuml.com endpoint and self-hosted
plantuml-server instances) and Kroki gateways (the public kroki.io
endpoint), which accept programmatic clients without bot protection
and therefore serve as the automatic fallback in "auto" mode.
"""

from __future__ import annotations

import logging
import httpx
import urllib.parse
from typing import TYPE_CHECKING, Final, Protocol

from infrastructure.visualisation.plantuml.encoding import (
    build_kroki_url,
    build_plantuml_url,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from infrastructure.visualisation.plantuml.models import DiagramImageFormat


PLANTUML_PUBLIC_SERVER_URL: Final[str] = "https://www.plantuml.com/plantuml"
KROKI_PUBLIC_SERVER_URL: Final[str] = "https://kroki.io"
AUTO_SERVER_SELECTION: Final[str] = "auto"

_USER_AGENT: Final[str] = "Mozilla/5.0 (compatible; AutoSystemDesign/1.0)"
_DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0

_logger: logging.Logger = logging.getLogger(__name__)


class DiagramRenderingError(Exception):
    """Raised when a diagram server cannot render the diagram source."""

    @classmethod
    def rejected(cls, server_label: str, status_code: int) -> DiagramRenderingError:
        return cls(f"{server_label} rejected the diagram: HTTP {status_code}")

    @classmethod
    def unreachable(cls, server_label: str, cause: OSError) -> DiagramRenderingError:
        return cls(f"Cannot reach {server_label}: {cause}")

    @classmethod
    def all_servers_failed(cls, failures: Sequence[str]) -> DiagramRenderingError:
        return cls("All diagram servers failed: " + "; ".join(failures))


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
    python-urllib agent. The INFO log identifies which server actually
    rendered the image when several are configured.
    """
    parsed_url = urllib.parse.urlsplit(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise InvalidDiagramUrlError

    try:
        response = httpx.get(
            url,
            headers={"User-Agent": _USER_AGENT},
            timeout=timeout_seconds,
            follow_redirects=False,
        )
        response.raise_for_status()
        content: bytes = response.content
    except httpx.HTTPStatusError as error:
        raise DiagramRenderingError.rejected(
            server_label, error.response.status_code
        ) from error
    except httpx.RequestError as error:
        raise DiagramRenderingError.unreachable(
            server_label, OSError(str(error))
        ) from error
    _logger.info("Diagram image rendered by %s", server_label)
    return content


class PlantumlServerImageRenderer:
    """Fetches images from a PlantUML HTTP server over GET.

    Works with the public plantuml.com server and with self-hosted
    plantuml-server instances (for example the docker compose
    deployment in deploy/plantuml): point `server_url` at them. No
    local Java installation is required.
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


class InvalidDiagramUrlError(ValueError):
    """Raised when a renderer URL is not an absolute HTTP(S) URL."""

    def __init__(self) -> None:
        super().__init__("Invalid diagram URL")


class RendererConfigurationError(ValueError):
    """Invalid renderer configuration."""

    def __init__(self) -> None:
        super().__init__("At least one renderer is required")


class UnknownDiagramServerError(ValueError):
    """Unsupported diagram server selection."""

    def __init__(self, selection: str) -> None:
        super().__init__(
            f"Unknown diagram server selection {selection!r}: expected 'auto', "
            "'plantuml', 'kroki' or an http(s) plantuml-server URL"
        )


class FallbackImageRenderer:
    """Tries several renderers in order; the first success wins.

    `build_image_url` delegates to the primary renderer, so preview URLs
    always point at the preferred server.
    """

    def __init__(self, renderers: Sequence[PlantumlImageRenderer]) -> None:
        if not renderers:
            raise RendererConfigurationError
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
                image_bytes: bytes = renderer.render(source, image_format)
            except DiagramRenderingError as error:
                failures.append(str(error))
                _logger.warning("Diagram server failed, trying the next one: %s", error)
                continue
            return image_bytes
        raise DiagramRenderingError.all_servers_failed(failures)


def resolve_image_renderer(server: str) -> PlantumlImageRenderer:
    """Builds the renderer for a server selection string.

    Supported selections:
    - "auto": the public PlantUML server with the public Kroki gateway
      as an automatic fallback (the default);
    - "plantuml": the public PlantUML server only;
    - "kroki": the public Kroki gateway only;
    - an http(s) URL of a self-hosted plantuml-server instance, for
      example the docker compose deployment in deploy/plantuml.
    """
    selection: str = server.strip().lower()
    if selection == AUTO_SERVER_SELECTION:
        return FallbackImageRenderer(
            renderers=[
                PlantumlServerImageRenderer(),
                KrokiImageRenderer(),
            ]
        )
    if selection == "plantuml":
        return PlantumlServerImageRenderer()
    if selection == "kroki":
        return KrokiImageRenderer()
    if selection.startswith(("http://", "https://")):
        return PlantumlServerImageRenderer(server_url=server.strip())
    raise UnknownDiagramServerError(server)
