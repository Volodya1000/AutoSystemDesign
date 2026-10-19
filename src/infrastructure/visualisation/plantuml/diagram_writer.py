"""Persistence of diagram artifacts to the local filesystem."""

import re
from pathlib import Path
from typing import Final

from infrastructure.visualisation.plantuml.models import DiagramArtifacts

_UNSAFE_FILENAME_CHARACTERS: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]")


class DiagramSavingError(Exception):
    """Raised when diagram artifacts cannot be written to disk."""

    def __init__(self, output_dir: Path, cause: OSError) -> None:
        super().__init__(f"Cannot write diagram files to {output_dir}: {cause}")


class DiagramFileWriter:
    """Write diagram artifacts as a .puml file plus the rendered image.

    Keeping persistence out of the DTO keeps the model pure (SRP) and
    lets channels that never touch disk (HTTP APIs, UIs) skip it.
    """

    def write(
        self, artifacts: DiagramArtifacts, output_dir: Path, base_name: str
    ) -> list[Path]:
        """Write the artifacts; returns the list of created file paths.

        `base_name` is sanitised into a file-name-safe form, so scenario
        identifiers containing path separators cannot escape the output
        directory. Raises DiagramSavingError on filesystem failures.
        """
        safe_name: str = _UNSAFE_FILENAME_CHARACTERS.sub("_", base_name)
        if not safe_name:
            safe_name = "diagram"
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            source_path: Path = output_dir / f"{safe_name}.puml"
            source_path.write_text(artifacts.source, encoding="utf-8")
            written: list[Path] = [source_path]
            if artifacts.image_bytes is not None:
                image_path: Path = output_dir / (
                    f"{safe_name}.{artifacts.image_format.value}"
                )
                image_path.write_bytes(artifacts.image_bytes)
                written.append(image_path)
        except OSError as error:
            raise DiagramSavingError(output_dir, error) from error
        return written
