"""Wire formats of remote PlantUML-compatible diagram servers.

Two URL formats are implemented, both computed offline with the
standard library only:
- PlantUML servers (<server>/<format>/<token>): raw DEFLATE stream
  encoded with the PlantUML 6-bit alphabet;
- Kroki gateways (<server>/plantuml/<format>/<token>): zlib stream
  encoded as URL-safe base64.
"""

import base64
import zlib
from typing import Final

from infrastructure.visualisation.plantuml.models import DiagramImageFormat

_PLANTUML_ALPHABET: Final[str] = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
)
_SIX_BIT_MASK: Final[int] = 0b111111


def encode_plantuml_text(text: str) -> str:
    """Encode diagram source into the PlantUML server URL token.

    The zlib container is stripped of its 2-byte header and 4-byte
    Adler-32 checksum: the server expects a raw DEFLATE stream.
    """
    deflate_stream: bytes = zlib.compress(text.encode("utf-8"), 9)[2:-4]
    return _encode_six_bit_groups(deflate_stream)


def encode_kroki_text(text: str) -> str:
    """Encode diagram source into the Kroki server URL token."""
    compressed: bytes = zlib.compress(text.encode("utf-8"), 9)
    return base64.urlsafe_b64encode(compressed).decode("ascii")


def build_plantuml_url(
    server_url: str,
    source: str,
    image_format: DiagramImageFormat,
) -> str:
    """Return the GET URL that renders `source` on a PlantUML server."""
    server: str = server_url.rstrip("/")
    return f"{server}/{image_format.value}/{encode_plantuml_text(source)}"


def build_kroki_url(
    server_url: str,
    source: str,
    image_format: DiagramImageFormat,
    diagram_type: str = "plantuml",
) -> str:
    """Return the GET URL that renders `source` on a Kroki gateway."""
    server: str = server_url.rstrip("/")
    token: str = encode_kroki_text(source)
    return f"{server}/{diagram_type}/{image_format.value}/{token}"


def _encode_six_bit_groups(data: bytes) -> str:
    """Packs the byte stream into 6-bit groups mapped onto the alphabet.

    Full 3-byte groups behave exactly like standard base64; the trailing
    partial group is zero-padded, which the PlantUML decoder accepts.
    """
    characters: list[str] = []
    bit_buffer: int = 0
    bit_count: int = 0
    byte: int
    for byte in data:
        bit_buffer = (bit_buffer << 8) | byte
        bit_count += 8
        while bit_count >= MIN_WHILE_BIT_COUNT:
            bit_count -= 6
            characters.append(
                _PLANTUML_ALPHABET[(bit_buffer >> bit_count) & _SIX_BIT_MASK]
            )
    if bit_count > 0:
        characters.append(
            _PLANTUML_ALPHABET[(bit_buffer << (6 - bit_count)) & _SIX_BIT_MASK]
        )
    return "".join(characters)

MIN_WHILE_BIT_COUNT = 6
