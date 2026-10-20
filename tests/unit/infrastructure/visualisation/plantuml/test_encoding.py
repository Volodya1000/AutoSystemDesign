"""Unit tests for offline PlantUML and Kroki URL encoding."""

import base64
import zlib

import pytest

from infrastructure.visualisation.plantuml.encoding import (
    _PLANTUML_ALPHABET,
    build_kroki_url,
    build_plantuml_url,
    encode_kroki_text,
    encode_plantuml_text,
)
from infrastructure.visualisation.plantuml.models import DiagramImageFormat

pytestmark = pytest.mark.unit


def _decode_plantuml_token(token: str) -> str:
    """Decode the PlantUML 6-bit alphabet for a round-trip assertion."""
    bit_buffer: int = 0
    bit_count: int = 0
    output = bytearray()

    for character in token:
        bit_buffer = (bit_buffer << 6) | _PLANTUML_ALPHABET.index(character)
        bit_count += 6
        while bit_count >= MIN_WHILE_BIT_COUNT:
            bit_count -= 8
            output.append((bit_buffer >> bit_count) & 0xFF)

    return zlib.decompress(bytes(output), -zlib.MAX_WBITS).decode("utf-8")


@pytest.mark.parametrize(
    "source",
    [
        "@startuml\nAlice -> Bob: hello\n@enduml",
        "@startuml\ntitle 订单\n用户 -> 服务: 创建\n@enduml",
        "",
    ],
)
def test_plantuml_encoding_round_trips_utf8_source(source: str) -> None:
    token = encode_plantuml_text(source)

    assert token
    assert set(token) <= set(_PLANTUML_ALPHABET)
    assert _decode_plantuml_token(token) == source


@pytest.mark.parametrize(
    "source",
    [
        "@startuml\nAlice -> Bob: hello\n@enduml",
        "@startuml\ntitle Заказ\nПользователь -> Сервис: создать\n@enduml",
        "",
    ],
)
def test_kroki_encoding_round_trips_utf8_source(source: str) -> None:
    encoded = encode_kroki_text(source)
    compressed = base64.urlsafe_b64decode(encoded.encode("ascii"))

    assert zlib.decompress(compressed).decode("utf-8") == source


def test_build_plantuml_url_uses_server_format_and_encoded_token() -> None:
    source = "@startuml\nAlice -> Bob\n@enduml"

    url = build_plantuml_url(
        "https://plantuml.example/", source, DiagramImageFormat.SVG
    )

    assert url == ("https://plantuml.example/svg/" + encode_plantuml_text(source))


def test_build_kroki_url_includes_diagram_type_and_format() -> None:
    source = "@startuml\nAlice -> Bob\n@enduml"

    url = build_kroki_url("https://kroki.example/", source, DiagramImageFormat.PNG)

    assert url == ("https://kroki.example/plantuml/png/" + encode_kroki_text(source))


def test_build_kroki_url_supports_an_explicit_diagram_type() -> None:
    url = build_kroki_url(
        "https://kroki.example",
        "source",
        DiagramImageFormat.SVG,
        diagram_type="graphviz",
    )

    assert url.startswith("https://kroki.example/graphviz/svg/")

MIN_WHILE_BIT_COUNT = 8
