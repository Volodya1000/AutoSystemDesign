"""Read-only checks for repository whitespace and end-of-file hygiene."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)


async def _list_tracked_files(executable: str) -> bytes:
    """Read paths tracked by Git, including staged additions."""
    process = await asyncio.create_subprocess_exec(
        executable,
        "ls-files",
        "-z",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        message = "Git could not list tracked files"
        raise RuntimeError(message)
    return stdout


def tracked_files() -> list[Path]:
    """Return paths tracked by Git, including staged additions."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError

    output = asyncio.run(_list_tracked_files(git_executable))
    return [
        Path(raw_path.decode("utf-8")) for raw_path in output.split(b"\0") if raw_path
    ]


def _read_file(path: Path) -> tuple[bytes, str] | None:
    """Read a text file, ignoring binary or inaccessible tracked files."""
    try:
        raw_bytes = path.read_bytes()
        return raw_bytes, raw_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _file_failures(path: Path) -> list[str]:
    """Check whitespace and final newlines for one tracked file."""
    file_data = _read_file(path)
    if file_data is None:
        return []

    raw_bytes, decoded_text = file_data
    failures: list[str] = []
    if raw_bytes and not raw_bytes.endswith(b"\n"):
        failures.append(f"{path}: missing newline at end of file")
    elif raw_bytes.endswith(b"\n\n"):
        failures.append(f"{path}: extra blank lines at end of file")

    for line_number, line in enumerate(decoded_text.splitlines(), start=1):
        if line.endswith((" ", "\t")):
            failures.append(f"{path}:{line_number}: trailing whitespace")
    return failures


def main() -> int:
    """Check tracked UTF-8 files without modifying them."""
    failures = [
        failure
        for path in tracked_files()
        for failure in _file_failures(path)
    ]
    if failures:
        _logger.error("%s", "\n".join(failures))
        return 1

    _logger.info("Whitespace and EOF checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
