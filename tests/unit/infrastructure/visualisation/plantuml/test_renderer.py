"""Unit tests for PlantUML renderer selection, fallback and HTTP failures."""

from __future__ import annotations

import httpx
import pytest

from infrastructure.visualisation.plantuml import renderer as renderer_module
from infrastructure.visualisation.plantuml.models import DiagramImageFormat
from infrastructure.visualisation.plantuml.renderer import (
    DiagramRenderingError,
    FallbackImageRenderer,
    KrokiImageRenderer,
    PlantumlServerImageRenderer,
    resolve_image_renderer,
)

pytestmark = pytest.mark.unit


class SimulatedNetworkDownError(OSError):
    """Test-only network failure."""

    def __init__(self) -> None:
        super().__init__("network down")


class StubRenderer:
    """An offline renderer double with a scripted success or failure."""

    def __init__(
        self,
        image_url: str,
        *,
        image: bytes = b"image",
        failure: DiagramRenderingError | None = None,
    ) -> None:
        self.image_url = image_url
        self.image = image
        self.failure = failure
        self.calls: int = 0

    def build_image_url(self, source: str, image_format: DiagramImageFormat) -> str:
        del source, image_format
        return self.image_url

    def render(self, source: str, image_format: DiagramImageFormat) -> bytes:
        del source, image_format
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        return self.image


def test_resolve_image_renderer_supports_named_selections() -> None:
    assert isinstance(resolve_image_renderer("plantuml"), PlantumlServerImageRenderer)
    assert isinstance(resolve_image_renderer(" KROKI "), KrokiImageRenderer)
    assert isinstance(resolve_image_renderer("auto"), FallbackImageRenderer)


@pytest.mark.parametrize("server", ["", "local", "ftp://example.com"])
def test_resolve_image_renderer_rejects_unknown_selections(server: str) -> None:
    with pytest.raises(ValueError, match="Unknown diagram server selection"):
        resolve_image_renderer(server)


def test_resolve_image_renderer_accepts_self_hosted_http_url() -> None:
    renderer = resolve_image_renderer("  http://localhost:8080/  ")

    assert isinstance(renderer, PlantumlServerImageRenderer)
    assert renderer.build_image_url("source", DiagramImageFormat.SVG).startswith(
        "http://localhost:8080/svg/"
    )


def test_fallback_renderer_returns_first_success() -> None:
    first = StubRenderer("first-url", image=b"first")
    second = StubRenderer("second-url", image=b"second")
    renderer = FallbackImageRenderer([first, second])

    assert renderer.build_image_url("source", DiagramImageFormat.SVG) == "first-url"
    assert renderer.render("source", DiagramImageFormat.SVG) == b"first"
    assert first.calls == 1
    assert second.calls == 0


def test_fallback_renderer_tries_next_server_after_rendering_error() -> None:
    first = StubRenderer(
        "primary",
        failure=DiagramRenderingError("primary unavailable"),
    )
    second = StubRenderer("fallback", image=b"fallback-image")
    renderer = FallbackImageRenderer([first, second])

    assert renderer.render("source", DiagramImageFormat.PNG) == b"fallback-image"
    assert first.calls == 1
    assert second.calls == 1


def test_fallback_renderer_reports_all_server_failures() -> None:
    renderer = FallbackImageRenderer(
        [
            StubRenderer("primary", failure=DiagramRenderingError("primary down")),
            StubRenderer("fallback", failure=DiagramRenderingError("fallback down")),
        ]
    )

    with pytest.raises(
        DiagramRenderingError, match="All diagram servers failed"
    ) as exc:
        renderer.render("source", DiagramImageFormat.SVG)

    assert "primary down" in str(exc.value)
    assert "fallback down" in str(exc.value)


def test_fallback_renderer_requires_at_least_one_renderer() -> None:
    with pytest.raises(ValueError, match="At least one renderer"):
        FallbackImageRenderer([])


def test_http_renderer_rejects_non_http_url_before_opening(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_get(*args: object, **kwargs: object) -> httpx.Response:
        del args, kwargs
        raise AssertionError

    monkeypatch.setattr(renderer_module.httpx, "get", unexpected_get)
    renderer = PlantumlServerImageRenderer(server_url="file://localhost/tmp")

    with pytest.raises(ValueError, match="Invalid diagram URL"):
        renderer.render("source", DiagramImageFormat.PNG)


def test_http_renderer_sets_user_agent_and_returns_response_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        observed["url"] = url
        observed.update(kwargs)
        request = httpx.Request("GET", url)
        return httpx.Response(200, content=b"rendered-image", request=request)

    monkeypatch.setattr(renderer_module.httpx, "get", fake_get)
    renderer = PlantumlServerImageRenderer(
        server_url="https://plantuml.example/", timeout_seconds=4.0
    )

    assert renderer.render("source", DiagramImageFormat.PNG) == b"rendered-image"
    observed_url = observed["url"]
    assert isinstance(observed_url, str)
    assert observed_url.startswith("https://plantuml.example/")
    observed_headers = observed["headers"]
    assert isinstance(observed_headers, dict)
    user_agent = observed_headers.get("User-Agent")
    assert isinstance(user_agent, str)
    assert "AutoSystemDesign" in user_agent
    assert observed["timeout"] == EXPECTED_ASSERT_OBSERVED_TIMEOUT
    assert observed["follow_redirects"] is False


def test_http_renderer_maps_http_errors_to_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        del kwargs
        request = httpx.Request("GET", url)
        response = httpx.Response(403, request=request)
        message = "Forbidden"
        raise httpx.HTTPStatusError(message, request=request, response=response)

    monkeypatch.setattr(renderer_module.httpx, "get", fake_get)
    renderer = PlantumlServerImageRenderer(server_url="https://plantuml.example")

    with pytest.raises(DiagramRenderingError, match="HTTP 403"):
        renderer.render("source", DiagramImageFormat.PNG)


def test_http_renderer_maps_connection_errors_to_domain_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        del url, kwargs
        message = "network down"
        raise httpx.ConnectError(message)

    monkeypatch.setattr(renderer_module.httpx, "get", fake_get)
    renderer = KrokiImageRenderer(server_url="https://kroki.example")

    with pytest.raises(DiagramRenderingError, match="Cannot reach Kroki server"):
        renderer.render("source", DiagramImageFormat.SVG)

EXPECTED_ASSERT_OBSERVED_TIMEOUT = 4.0

